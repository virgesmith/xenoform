import math
from typing import Annotated

from xenoform import compile
from xenoform.utils import translate_function_signature


@compile(extra_includes=["<algorithm>"])
def clamp(x: float, lo: float = -math.inf, hi: float = math.inf) -> float:  # ty: ignore[empty-body]
    "return std::clamp(x, lo, hi);"


@compile(extra_includes=["<cmath>"])
def is_nan(x: float = math.nan) -> bool:  # ty: ignore[empty-body]
    "return std::isnan(x);"


@compile()
def single(x: Annotated[float, "float"] = math.inf) -> Annotated[float, "float"]:  # ty: ignore[empty-body]
    "return x;"


@compile()
def maybe(x: float | None = math.inf) -> float:  # ty: ignore[empty-body]
    "return x.value_or(0.0);"


def test_infinite_defaults() -> None:
    assert clamp(1e300) == 1e300
    assert clamp(-1e300) == -1e300
    assert clamp(5.0, hi=2.0) == 2.0


def test_nan_default() -> None:
    assert is_nan()
    assert not is_nan(1.0)


def test_non_finite_default_converts_to_other_types() -> None:
    # the default is a double, converted to float and to std::optional<double>
    assert single() == math.inf
    assert maybe() == math.inf
    assert maybe(None) == 0.0


def test_non_finite_default_includes_limits() -> None:
    def f(x: float = math.inf) -> None: ...

    _, _, headers = translate_function_signature(f)
    assert "<limits>" in headers

    def g(x: float = 1.0) -> None: ...

    _, _, headers = translate_function_signature(g)
    assert "<limits>" not in headers
