from collections import defaultdict
import inspect
import os
import platform
import re
import sys
from collections.abc import Callable
from operator import add
from typing import Any, Literal, cast

from itrx import Itr

from xenoform.extension_types import header_requirements, translate_type

Platform = Literal["Linux", "Darwin", "Windows"]
Platforms = list[Platform] | None


def platform_specific(settings: dict[Platform, list[str]]) -> list[str] | None:
    """
    Given a dict of possible platform-specific settings, return the appropriate values, if set
    """
    return settings.get(cast(Platform, platform.system()))


def _translate_value(value: Any) -> str:
    translations = {"False": "false", "True": "true"}
    return translations.get(str(value), str(value))


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
        headers.extend(cpptype.headers(header_requirements))
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
                arg_def += f"={_translate_value(defaults[var_name])}"
                arg_annotation += f"={_translate_value(defaults[var_name])}"
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
    return tuple(s for s in func.__qualname__.split(".")[:-1] if s != "<locals>")


def deduplicate(params: list[str]) -> list[str]:
    """Remove duplicates from a list while preserving order."""
    return list(dict.fromkeys(params))


def group_headers(headers: list[str]) -> list[list[str]]:
    """
    Group the headers in a rudimentary order like so:
    1. (anything that doesnt fit the patterns below)
    2. "local.h" // library code
    3. <thirdparty.hpp> // third-party library code
    4. <stdlib> // C and C++ standard library headers
    """
    local_pattern = re.compile(r'^".*\.h|hpp"$')
    thirdparty_pattern = re.compile(r"^<.*\.h|hpp>$")
    stdlib_pattern = re.compile(r"^<[^.]+>$")

    # strip any leading/trailing whitespace
    stripped = [h.strip() for h in headers]

    local_headers = deduplicate([h for h in stripped if local_pattern.match(h)])
    # if pybind11/pybind11.h comes before pybind11/stl.h it can cause problems so ensure its included last
    thirdparty_headers = [*deduplicate([h for h in stripped if thirdparty_pattern.match(h)]), "<pybind11/pybind11.h>"]
    stdlib_headers = deduplicate([h for h in stripped if stdlib_pattern.match(h)])
    other_headers = deduplicate([h for h in stripped if h not in local_headers + thirdparty_headers + stdlib_headers])

    return [other_headers, local_headers, thirdparty_headers, stdlib_headers]


def build_freethreaded() -> bool:
    """Return whether interpreter is free-threaded AND free-threading hasn't been manually overridden"""
    if sys.version_info[1] < 13:
        return False
    return not (sys._is_gil_enabled() or "XENOFORM_DISABLE_FT" in os.environ)
