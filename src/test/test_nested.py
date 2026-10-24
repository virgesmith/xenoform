import sys

import pytest

from xenoform import compile
from xenoform.utils import get_function_scope


def outer(x: float) -> float:
    @compile()
    def inner(x: float, i: int) -> float:  # ty: ignore[empty-body]
        """
        return x * i;
        """

    return inner(x, 5)


def test_nested() -> None:
    assert outer(3.1) == 15.5

    # built modules are loaded by path, not importable by name, so look it up where it was registered
    assert sys.modules["test_nested_ext.test_nested"]._outer_inner(2.7, 3) == pytest.approx(8.1)


class Outer:
    class Inner:
        def method(self) -> None:
            pass


def test_get_function_scope() -> None:
    assert get_function_scope(test_nested) == ()
    assert get_function_scope(Outer.Inner.method) == ("Outer", "Inner")


if __name__ == "__main__":
    test_nested()
