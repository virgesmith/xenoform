import inspect
from typing import Annotated

import pytest

from xenoform.compile import _check_annotations, compile
from xenoform.errors import AnnotationError


@compile()
def f(i: int, x: float, *, b: bool) -> str:  # ty: ignore[empty-body]
    """
    return "hello";
    """


def test_typing() -> None:
    # check the compile machinery doesn't lose any type information
    def wrap_f(i: Annotated[int, "size_t"], x: float, *, b: bool) -> str:
        # the real test here is the linters (mypy ruff etc) not pytest. there should be no errors about the types
        # differing between wrap_f and f
        return f(i, x, b=b)

    assert wrap_f(42, 1.0, b=True) == "hello"
    sig = inspect.signature(f)
    assert sig.return_annotation is str
    assert "i" in sig.parameters and sig.parameters["i"].annotation is int
    assert "x" in sig.parameters and sig.parameters["x"].annotation is float
    assert "b" in sig.parameters and sig.parameters["b"].annotation is bool


def untyped(x, y: Annotated[int, "blah"]):
    pass


def untyped_return(x: int, y: Annotated[int, "blah"]):
    pass


def typed_noargs() -> None:
    pass


def test_untyped() -> None:
    with pytest.raises(AnnotationError):
        _check_annotations(untyped)
    with pytest.raises(AnnotationError):
        _check_annotations(untyped_return)
    _check_annotations(typed_noargs)


if __name__ == "__main__":
    test_untyped()
