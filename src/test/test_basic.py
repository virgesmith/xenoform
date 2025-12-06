import platform
from collections.abc import Callable
from typing import Annotated, Any

import pytest

from xenoform import CompilationError, CppTypeError, Platform, platform_specific
from xenoform.compile import _check_build_fetch_module_impl, _parse_macros, compile
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.extension_types import CppQualifier
from xenoform.utils import translate_function_signature


def test_signature_translation1() -> None:
    def f(_i: int) -> None:
        ""

    assert translate_function_signature(f) == ("[](int _i) -> void", ['py::arg("_i")'], [])

    def f2(a: float, b: str, c: bool) -> int:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f2) == (
        "[](double a, std::string b, bool c) -> int",
        ['py::arg("a")', 'py::arg("b")', 'py::arg("c")'],
        ["<string>"],
    )

    def f3(a: float, b: Annotated[str, CppQualifier.CRef], c: bool) -> int:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f3) == (
        "[](double a, const std::string& b, bool c) -> int",
        ['py::arg("a")', 'py::arg("b")', 'py::arg("c")'],
        ["<string>"],
    )

    def f4(a: float, b: Annotated[str, "const char*"], c: bool) -> int:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f4) == (
        "[](double a, const char* b, bool c) -> int",
        ['py::arg("a")', 'py::arg("b")', 'py::arg("c")'],
        [],
    )

    def f5(a: float, *, b: Annotated[str, "const char*"], c: bool, **kwargs: Any) -> int:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f5) == (
        "[](double a, const char* b, bool c, const py::kwargs& kwargs) -> int",
        ['py::arg("a")', "py::kw_only()", 'py::arg("b")', 'py::arg("c")'],
        [],
    )


def test_signature_translation2() -> None:
    def f6(a: float, /, b: bool, *, c: int) -> None:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f6) == (
        "[](double a, bool b, int c) -> void",
        ['py::arg("a")', "py::pos_only()", 'py::arg("b")', "py::kw_only()", 'py::arg("c")'],
        [],
    )

    def f7(*, c: int) -> None:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f7) == (
        "[](int c) -> void",
        ["py::kw_only()", 'py::arg("c")'],
        [],
    )

    def f8(a: float, c: int, /) -> None:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f8) == (
        "[](double a, int c) -> void",
        ['py::arg("a")', 'py::arg("c")', "py::pos_only()"],
        [],
    )

    def f9(a: float, *, c: bool = True) -> None:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f9) == (
        "[](double a, bool c=true) -> void",
        ['py::arg("a")', "py::kw_only()", 'py::arg("c")=true'],
        [],
    )

    def f10(a: tuple[int, tuple[int, float]], *, value: Callable[[int, float], bool]) -> bool:  # type: ignore[empty-body]
        ""

    assert translate_function_signature(f10) == (
        "[](std::tuple<int, std::tuple<int, double>> a, std::function<bool(int, double)> value) -> bool",
        ['py::arg("a")', "py::kw_only()", 'py::arg("value")'],
        ["<pybind11/stl.h>", "<pybind11/stl.h>", "<pybind11/functional.h>"],
    )


def test_platform_specific() -> None:
    assert platform_specific({}) is None

    settings: dict[Platform, list[str]] = {
        "Linux": ["linux"],
        "Darwin": ["darwin"],
        "Windows": ["windows"],
    }

    assert platform_specific(settings) == [platform.system().lower()]
    del settings["Darwin"]
    assert platform_specific(settings) == ([platform.system().lower()] if platform.system() != "Darwin" else None)


def test_parse_macros() -> None:
    assert _parse_macros([]) == {}
    assert _parse_macros(["NDEBUG"]) == {"NDEBUG": None}
    assert _parse_macros(["VER=3"]) == {"VER": "3"}
    assert _parse_macros(["NDEBUG", "VER=3"]) == {"NDEBUG": None, "VER": "3"}


@compile()
def max(i: int, j: int) -> int:  # type: ignore[empty-body]
    # comments can be added before...
    "return i > j ? i : j;"
    # ...and after the docstr


def test_basic() -> None:
    assert max(2, 3) == 3


@compile()
def incref(i: Annotated[int, CppQualifier.Ref]) -> None:
    """
    ++i;
    """


def test_ref() -> None:
    i = 1
    incref(i)  # i is immutable
    assert i == 1


@compile()
def string(s: str) -> int:  # type: ignore[empty-body]
    """
    return static_cast<int>(s.size());
    """


def test_header_required() -> None:
    assert string("string") == 6


@compile(extra_includes=["<pybind11/stl.h>"], define_macros=["PYBIND11_DETAILED_ERROR_MESSAGES"])
def vec(size: int) -> list[int]:  # type: ignore[empty-body]
    """
    return std::vector<int>(size);
    """


def test_stl() -> None:
    assert len(vec(10)) == 10


@compile()
def throws() -> bool:  # type: ignore[empty-body]
    """
    throw std::runtime_error("oops");
    """


def test_throws() -> None:
    with pytest.raises(RuntimeError):
        throws()


def test_unknown_type() -> None:
    with pytest.raises(CppTypeError):

        class X: ...

        @compile()
        def unknown(x: X) -> bool:  # type: ignore[empty-body]
            "return false;"


def test_compile_error() -> None:
    f = """{
#error
}"""
    spec = ModuleSpec().add_function(
        FunctionSpec(
            name="error", body=f, arg_annotations="", scope=(), return_value_policy=ReturnValuePolicy.Automatic
        )
    )
    with pytest.raises(CompilationError):
        _check_build_fetch_module_impl("broken_module", spec)
