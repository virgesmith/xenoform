from typing import Any

import pytest

from xenoform import compile


@compile()
def f_cpp(n: int, /, x: float, y: float = 2.7, *, b: bool = False) -> str:  # ty: ignore[empty-body]
    # arg optional positional keyword
    #   n    N         Y         N
    #   x    N         Y         Y
    #   y    Y         Y         Y
    #   b    Y         N         Y
    """
    return "n=" + std::to_string(n) + " x=" + std::to_string(x) + " y=" + std::to_string(y) + " b=" + std::to_string(b);
    """


def test_pos_kwargs() -> None:
    with pytest.raises(TypeError):
        f_cpp(1)  # ty: ignore[call-arg]
    assert f_cpp(1, 3.1) == "n=1 x=3.100000 y=2.700000 b=0"
    assert f_cpp(1, 3.1, 3.1) == "n=1 x=3.100000 y=3.100000 b=0"
    assert f_cpp(1, x=3.1) == "n=1 x=3.100000 y=2.700000 b=0"
    assert f_cpp(1, x=3.1, y=3.1) == "n=1 x=3.100000 y=3.100000 b=0"
    with pytest.raises(TypeError):
        f_cpp(n=1, x=3.1)  # ty: ignore[call-arg]
    assert f_cpp(1, 3.1, b=True) == "n=1 x=3.100000 y=2.700000 b=1"
    assert f_cpp(1, b=True, x=2.7) == "n=1 x=2.700000 y=2.700000 b=1"
    with pytest.raises(TypeError):
        f_cpp(1, 3.1, 2.7, True)  # ty: ignore[misc]


@compile()
def varargs(*args: Any) -> int:  # ty: ignore[empty-body]
    """
    return args.size();
    """


def test_varargs() -> None:
    assert varargs() == 0
    assert varargs(5) == 1
    assert varargs(5, 3) == 2
    with pytest.raises(TypeError):
        varargs(x=5)  # ty: ignore[call-arg]


@compile()
def varkwargs(**args: Any) -> int:  # ty: ignore[empty-body]
    """
    return args.size();
    """


def test_varkwargs() -> None:
    assert varkwargs() == 0
    assert varkwargs(x=1) == 1
    assert varkwargs(x=1, y=2) == 2
    with pytest.raises(TypeError):
        varkwargs(5)  # ty: ignore[call-arg]


@compile()
def varposkwargs(n: int, *args: Any, m: int, **kwargs: Any) -> int:  # ty: ignore[empty-body]
    """
    return args.size() + 10 * kwargs.size() + 100 * n + 1000 * m;
    """


def test_varposkwargs() -> None:
    with pytest.raises(TypeError):
        assert varposkwargs(1, 1)  # ty: ignore[call-arg]
    assert varposkwargs(1, m=1) == 1100
    assert varposkwargs(n=1, m=1) == 1100
    assert varposkwargs(1, 1, m=1, y=2) == 1111
    assert varposkwargs(1, m=1, y=2) == 1110
    assert varposkwargs(1, 1, m=1) == 1101


if __name__ == "__main__":
    # test_pos_kwargs()
    test_varargs()
    test_varkwargs()
    test_varposkwargs()
