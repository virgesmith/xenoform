import inspect
import platform
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from operator import add
from typing import Any, Literal, cast

import clang_format
from itrx import Itr

from xenoform.config import get_config
from xenoform.extension_types import HEADER_REQUIREMENTS, translate_type

Platform = Literal["Linux", "Darwin", "Windows"]
Platforms = list[Platform] | None


def platform_specific(settings: dict[Platform, list[str]]) -> list[str] | None:
    """
    Given a dict of possible platform-specific settings, return the appropriate values, if set
    """
    return settings.get(cast(Platform, platform.system()))


_CPP_STRING_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _cpp_string_literal(value: str) -> str:
    """Render a Python str as an escaped C++ string literal."""
    chars = []
    for ch in value:
        if ch in _CPP_STRING_ESCAPES:
            chars.append(_CPP_STRING_ESCAPES[ch])
        elif ch.isascii() and ch.isprintable():
            chars.append(ch)
        else:
            chars.extend(f"\\{byte:03o}" for byte in ch.encode("utf-8"))
    return '"' + "".join(chars) + '"'


def _translate_value(value: Any, cpptype: str) -> str:
    """Translate a Python default argument value to its C++ literal representation.

    Translation is by type, not by stringified value: bools become ``true``/``false``,
    ``None`` becomes ``std::nullopt``, strings are quoted and escaped, and empty
    containers become a value-initialised instance of their C++ type. Values that
    cannot be represented unambiguously in C++ raise ``TypeError`` at decoration time
    rather than deferring an invalid-C++ compile error to first call.
    """
    # bool is a subclass of int, so it must be checked first
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "std::nullopt"
    if isinstance(value, str):
        return _cpp_string_literal(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (tuple, list, set, dict)):
        if not value:
            return f"{cpptype}{{}}"
        raise TypeError(
            f"cannot translate non-empty container default {value!r} to C++; "
            "implement the default in the C++ code instead"
        )
    raise TypeError(f"cannot translate default value {value!r} of type {type(value).__name__} to C++")


def _splitargs(signature: str) -> tuple[str, ...]:
    """
    Need to deal with commas in types, e.g. dict[str, int]. Replace the non-nested commas ONLY with $ then split
    """
    # extract the part in between ()
    base = Itr(signature).skip_while(lambda c: c != "(").skip(1).take_while(lambda c: c != ")")
    # mark the level of [] nesting
    mark = base.copy().map_dict(defaultdict(int, {"[": 1, "]": -1})).accumulate(add)
    # combine, replace level-0 commas with $, split and strip
    return (
        Itr(base.zip(mark).map(lambda cn: "$" if cn == (",", 0) else cn[0]).fold("", add).split("$"))
        .map(str.strip)
        .collect()
    )


def translate_function_signature(func: Callable[..., Any]) -> tuple[str, list[str], list[str]]:
    "map python signature to C++ equivalent"
    arg_spec = inspect.getfullargspec(func)

    headers = []
    arg_defs = []
    arg_annotations = []

    # parse signature - get defaults and positions of pos-only and kw-only
    sig = inspect.signature(func)
    raw_sig = _splitargs(str(sig))
    pos_only = raw_sig.index("/") if "/" in raw_sig else None
    kw_only = raw_sig.index("*") if "*" in raw_sig else None
    defaults = {k: v.default for k, v in sig.parameters.items() if v.default is not inspect.Parameter.empty}

    ret: str | None = None
    for var_name, type_ in arg_spec.annotations.items():
        cpptype = translate_type(type_)
        headers.extend(cpptype.headers(HEADER_REQUIREMENTS))
        if var_name == "return":
            ret = str(cpptype)
        else:
            if arg_spec.varargs == var_name:
                arg_def = f"py::args {var_name}"
            elif arg_spec.varkw == var_name:
                arg_def = f"const py::kwargs& {var_name}"
            else:
                arg_def = f"{cpptype} {var_name}"
            arg_annotation = f'py::arg("{var_name}")'
            if var_name in defaults:
                translated = _translate_value(defaults[var_name], f"{cpptype}")
                arg_def += f"={translated}"
                arg_annotation += f"={translated}"
            arg_defs.append(arg_def)
            # dont create an annotation for var(kw)args
            if arg_spec.varargs != var_name and arg_spec.varkw != var_name:
                arg_annotations.append(arg_annotation)
    if pos_only is not None:
        arg_annotations.insert(pos_only, "py::pos_only()")
    if kw_only is not None:
        arg_annotations.insert(kw_only, "py::kw_only()")

    return f"[]({', '.join(arg_defs)})" + (f" -> {ret}" if ret else ""), arg_annotations, headers


def get_function_scope(func: Callable[..., Any]) -> tuple[str, ...]:
    """
    Returns the name of the class for class and instance methods
    NB Does not work for static methods
    """
    return tuple(s for s in func.__qualname__.split(".")[:-1] if s != "<locals>")  # ty: ignore[unresolved-attribute]


def deduplicate(params: Iterable[str]) -> list[str]:
    """Remove duplicates from an iterator while preserving order."""
    return list(dict.fromkeys(params))


def group_headers(headers: list[str]) -> list[list[str]]:
    """
    Group the headers in a rudimentary order like so:
    1. (anything that doesnt fit the patterns below)
    2. "local.h" // library code
    3. <thirdparty.hpp> // third-party library code
    4. <stdlib> // C and C++ standard library headers
    """
    local_pattern = re.compile(r'^".*\.(h|hpp)"$')
    thirdparty_pattern = re.compile(r"^<.*\.(h|hpp)>$")
    stdlib_pattern = re.compile(r"^<[^.]+>$")

    stripped = Itr(headers).map(str.strip)
    local_headers, other_headers = stripped.partition(local_pattern.match)  # ty: ignore[invalid-argument-type]
    thirdparty_headers, other_headers = other_headers.partition(thirdparty_pattern.match)  # ty: ignore[invalid-argument-type]
    # if pybind11/pybind11.h comes before pybind11/stl.h it can cause problems so ensure its included last
    thirdparty_headers = thirdparty_headers.filter(lambda h: h != "<pybind11/pybind11.h>").chain(
        ["<pybind11/pybind11.h>"]
    )

    stdlib_headers, other_headers = other_headers.partition(stdlib_pattern.match)  # ty: ignore[invalid-argument-type]

    return [
        deduplicate(other_headers),
        deduplicate(local_headers),
        deduplicate(thirdparty_headers),
        deduplicate(stdlib_headers),
    ]


def build_freethreaded() -> bool:
    """Return whether interpreter is free-threaded AND free-threading hasn't been manually overridden"""
    if not hasattr(sys, "_is_gil_enabled"):
        return False
    return not (sys._is_gil_enabled() or get_config().disable_ft is not None)


def format_cpp(code: str) -> str:
    """Use clang-format to prettify code"""
    cmd = [clang_format.get_executable("clang-format"), f"--style={get_config().cpp_format}"]
    try:
        result = subprocess.run(cmd, input=code, capture_output=True, text=True, check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"clang-format failed: {e}. module.cpp will be unformatted")
    else:
        code = result.stdout
    return code
