import math
from math import pi  # noqa: F401 - linters can't see names used only in constants=, so would remove the import
from typing import Annotated, Self

import numpy as np
import pytest

from xenoform import CompilationError, CppTypeError, compile
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.utils import parse_constant, translate_constant

N = 7
RATE = 0.25
VERBOSE = True
GREETING = "hello"
SMALL = np.int16(-3)
BIG = 2**40
INF = math.inf


@compile(constants=["N", "RATE", "VERBOSE", "GREETING", "SMALL"])
def basics() -> tuple[int, float, bool, str, int]:  # ty: ignore[empty-body]
    "return {N, RATE, VERBOSE, std::string(GREETING), SMALL};"


# the same declaration from another function in the module collapses into one
@compile(constants=["N"])
def n_again() -> int:  # ty: ignore[empty-body]
    "return N;"


@compile(constants=["BIG: uint64_t"])
def big() -> Annotated[int, "uint64_t"]:  # ty: ignore[empty-body]
    "return BIG;"


@compile(constants=["pi"])
def circle_area(r: float) -> float:  # ty: ignore[empty-body]
    "return pi * r * r;"


@compile(constants=["INF"], extra_includes=["<cmath>"])
def is_inf() -> bool:  # ty: ignore[empty-body]
    "return std::isinf(INF);"


class Scaler:
    SCALE = 3

    # looked up in the class body
    @compile(constants=["SCALE"])
    def scale(self: Self, x: int) -> int:  # ty: ignore[empty-body]
        "return SCALE * x;"


def test_module_level_constants() -> None:
    assert basics() == (7, 0.25, True, "hello", -3)
    assert n_again() == 7


def test_explicit_type() -> None:
    assert big() == 2**40


def test_imported_constant() -> None:
    assert circle_area(1.0) == pytest.approx(math.pi)


def test_non_finite_constant() -> None:
    assert is_inf()


def test_class_body_constant() -> None:
    assert Scaler().scale(2) == 6


def test_local_constant_shadows_global() -> None:
    N = 100  # noqa: F841, N806 - used only by name in constants=, and must be named N to shadow the global

    # a separate module, as this N would conflict with the global one
    @compile(constants=["N"], module_name="constants_local")
    def local_n() -> int:  # ty: ignore[empty-body]
        "return N;"

    assert local_n() == 100


def test_conflicting_values_fail_to_compile() -> None:
    value = 1

    @compile(constants=["value"], module_name="constants_conflict")
    def first() -> int:  # ty: ignore[empty-body]
        "return value;"

    value = 2  # noqa: F841 - used only by name in constants=

    @compile(constants=["value"], module_name="constants_conflict")
    def second() -> int:  # ty: ignore[empty-body]
        "return value;"

    # a redefinition, reported by the compiler
    with pytest.raises(CompilationError, match="value"):
        first()


def test_narrowing_is_a_compile_error() -> None:
    # brace initialisation: 2**40 doesn't fit the default int, so this fails rather than truncating
    too_big_value = 2**40  # noqa: F841

    @compile(constants=["too_big_value"], module_name="constants_narrowing")
    def too_big() -> int:  # ty: ignore[empty-body]
        "return too_big_value;"

    with pytest.raises(CompilationError):
        too_big()


def test_errors_at_decoration() -> None:
    with pytest.raises(ValueError, match="not found"):
        compile(constants=["NOT_DEFINED_ANYWHERE"])
    with pytest.raises(ValueError, match="identifier"):
        compile(constants=["1N"])
    scaler = Scaler()  # noqa: F841
    with pytest.raises(CppTypeError):
        compile(constants=["scaler"])  # an instance of a class with no C++ type
    with pytest.raises(TypeError):
        compile(constants=["BIG_LIST"])  # a non-empty container has no C++ literal


BIG_LIST = [1, 2, 3]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("N", ("N", None)),
        ("BIG: uint64_t", ("BIG", "uint64_t")),
        # only the first colon separates the type
        ("S: std::string_view", ("S", "std::string_view")),
        ("  N :  int64_t ", ("N", "int64_t")),
    ],
)
def test_parse_constant(entry: str, expected: tuple[str, str | None]) -> None:
    assert parse_constant(entry) == expected


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        ("", "identifier"),
        ("1N", "identifier"),
        ("my-const", "identifier"),
        ("café", "identifier"),  # valid python, but kept ASCII for C++
        ("int", "C\\+\\+ keyword"),  # a fine python name
        ("N:", "no C\\+\\+ type"),
        ("N:   ", "no C\\+\\+ type"),
    ],
)
def test_parse_constant_errors(entry: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_constant(entry)


@pytest.mark.parametrize(
    ("value", "cpp_type", "declaration", "headers"),
    [
        (7, None, "constexpr int X{7};", []),
        (True, None, "constexpr bool X{true};", []),
        (0.25, None, "constexpr double X{0.25};", []),
        ("hi", None, 'constexpr std::string_view X{"hi"};', ["<string_view>"]),
        (np.int16(-3), None, "constexpr int16_t X{-3};", []),
        (np.float32(1.5), None, "constexpr float X{1.5};", []),
        (math.inf, None, "constexpr double X{std::numeric_limits<double>::infinity()};", ["<limits>"]),
        (2**40, "uint64_t", "constexpr uint64_t X{1099511627776};", []),
    ],
)
def test_translate_constant(value: object, cpp_type: str | None, declaration: str, headers: list[str]) -> None:
    assert translate_constant("X", value, cpp_type) == (declaration, headers)


def _spec(constants: list[str]) -> ModuleSpec:
    function = FunctionSpec(
        name="f", body="[]() {}", arg_annotations="", scope=(), return_value_policy=ReturnValuePolicy.Automatic
    )
    return ModuleSpec().add_function(function, constants=constants)


def test_constants_dont_change_the_hash_by_order() -> None:
    a, b = "constexpr int A{1};", "constexpr int B{2};"
    assert _spec([a, b]).make_source("m") == _spec([b, a]).make_source("m")
    assert _spec([a]).make_source("m") != _spec([a, b]).make_source("m")
