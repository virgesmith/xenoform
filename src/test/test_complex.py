from math import exp, pi

import numpy as np
import pytest

from xenoform import compile


@compile()
def complex_float_func(z: np.complex64) -> np.complex64:  # type: ignore[empty-body]
    """
    return std::pow(z, z);
    """


@compile()
def complex_double_func(z: complex) -> complex:  # type: ignore[empty-body]
    """
    return std::pow(z, z);
    """


def test_complex_double() -> None:
    assert complex_double_func(1j) == pytest.approx(exp(-pi / 2))
    assert complex_double_func(np.complex128(0, 1)) == pytest.approx(exp(-pi / 2))
    assert complex_double_func(np.complex64(0, 1)) == pytest.approx(exp(-pi / 2))  # type: ignore[arg-type]
    assert complex_double_func(1j) == pytest.approx(exp(-pi / 2))
    assert complex_double_func(2) == 4


def test_complex_float() -> None:
    assert complex_float_func(1j) == pytest.approx(exp(-pi / 2))  # type: ignore[arg-type]
    assert complex_float_func(np.complex128(0, 1)) == pytest.approx(exp(-pi / 2))  # type: ignore[arg-type]
    assert complex_float_func(np.complex64(0, 1)) == pytest.approx(exp(-pi / 2))
    assert complex_float_func(1j) == pytest.approx(exp(-pi / 2))  # type: ignore[arg-type]
    assert complex_float_func(2) == 4  # type: ignore[arg-type]


if __name__ == "__main__":
    test_complex_float()
    test_complex_double()
