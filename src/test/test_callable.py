# can we return a C++ lambda?

from collections.abc import Callable
from typing import Annotated

import pytest

from xenoform import compile


@compile()
def round_sign() -> Callable[[float, bool], int]:  # ty: ignore[empty-body]
    """
    return [](double x, bool s) -> int { return int(s ? -x : x); };
    """


# this is the actual function, not one that returns it
def round_sign_py(x: float, s: bool) -> int:
    return int(-x if s else x)


@compile()
def modulo(n: int) -> Callable[[int], int]:  # ty: ignore[empty-body]
    """
    return [n](int i) { return i % n; };
    """


@compile()
def modulo_override(n: int) -> Annotated[Callable[[int], int], "py::cpp_function"]:  # ty: ignore[empty-body]
    """
    // explicit construction of py::cpp_function is not necessary
    return py::cpp_function([n](int i) { return i % n; });
    """


def modulo_py(n: int) -> Callable[[int], int]:
    return lambda i: i % n


@compile()
def use_modulo(f: Callable[[int], int], i: int) -> int:  # ty: ignore[empty-body]
    """
    return f(i);
    """


@compile()
def use_modulo_override(f: Annotated[Callable[[int], int], "py::function"], i: int) -> int:  # ty: ignore[empty-body]
    """
    // py::function returns a py::object so cast is required
    return f(i).cast<int>();
    """


def use_modulo_py(f: Callable[[int], int], i: int) -> int:
    return f(i)


@compile()
def use_round_sign(f: Callable[[float, bool], int], x: float) -> int:  # ty: ignore[empty-body]
    """
    return f(x, true);
    """


def use_round_sign_py(f: Callable[[float, bool], int], x: float) -> int:
    return f(x, True)


def test_modulo() -> None:
    f = modulo(3)
    g = modulo_override(7)

    assert f(0) == 0
    assert f(2) == 2
    assert f(10) == 1

    assert g(0) == 0
    assert g(2) == 2
    assert g(10) == 3

    with pytest.raises(TypeError):
        modulo("x")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        f("x")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        f()  # ty: ignore[missing-argument]
    with pytest.raises(TypeError):
        f(2, 3)  # ty: ignore[too-many-positional-arguments]

    assert modulo(2)(2) == modulo_py(2)(2) == 0
    assert modulo(3)(3) == modulo_py(3)(3) == 0
    assert modulo(5)(5) == modulo_py(5)(5) == 0
    assert modulo(5)(6) == modulo_py(5)(6) == 1


def test_use_modulo() -> None:
    assert use_modulo(modulo(5), 7) == 2
    assert use_modulo(modulo_py(5), 7) == 2
    assert use_modulo(lambda n: n % 5, 7) == 2
    assert use_modulo(modulo_override(5), 7) == 2

    assert use_modulo_override(modulo(7), 11) == 4
    assert use_modulo_override(modulo_py(7), 11) == 4
    assert use_modulo_override(lambda n: n % 7, 11) == 4
    assert use_modulo_override(modulo_override(7), 11) == 4


def test_all_combinations() -> None:
    round_sign_lambda: Callable[[float, bool], int] = lambda x, s: int(-x if s else x)  # noqa: E731

    round_sign_cpp = round_sign()

    assert round_sign_py(3.14, False) == round_sign_lambda(3.14, False) == round_sign_cpp(3.14, False) == 3

    assert (
        use_round_sign_py(round_sign_py, 2.72)
        == use_round_sign_py(round_sign_lambda, 2.72)
        == use_round_sign_py(round_sign_cpp, 2.72)
        == -2
    )
    assert (
        use_round_sign(round_sign_py, 2.72)
        == use_round_sign(round_sign_lambda, 2.72)
        == use_round_sign(round_sign_cpp, 2.72)
        == -2
    )


def test_function_type_errors() -> None:
    with pytest.raises(TypeError):
        use_round_sign(modulo, 1.0)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_round_sign_py(modulo, 1.0)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_round_sign(modulo_py, 1.0)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_round_sign(modulo_override, 1.0)  # ty: ignore[invalid-argument-type]

    with pytest.raises(TypeError):
        use_modulo(round_sign, 1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_modulo_py(round_sign, 1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_modulo(round_sign_py, 1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_modulo_override(round_sign, 1)  # ty: ignore[invalid-argument-type]


if __name__ == "__main__":
    # test_all_combinations()
    # test_function_type_errors()
    test_use_modulo()
