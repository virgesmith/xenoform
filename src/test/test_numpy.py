from typing import Annotated

import numpy as np
import numpy.typing as npt

from xenoform.compile import compile
from xenoform.extension_types import CppQualifier


@compile()
def by_ref(a: Annotated[npt.NDArray[np.float64], CppQualifier.Ref]) -> None:
    """
    auto r = a.mutable_unchecked<2>();
    r(0, 0) = 1.0;
    """


def test_numpy_byref() -> None:
    a = np.zeros((2, 2))
    by_ref(a)

    assert a[0, 0] == 1.0


@compile()
def by_val(a: npt.NDArray[np.float64]) -> None:
    """
    auto r = a.mutable_unchecked<2>();
    r(0, 0) = 1.0;
    """


def test_numpy_byval() -> None:
    a = np.zeros((2, 2))
    by_val(a)

    # a is shallow-copied
    assert a[0, 0] == 1.0


@compile()
def specify_int_bits(a: npt.NDArray[np.int32]) -> np.int64:  # type: ignore[empty-body]
    """
    return a.ndim();
    """


def test_int_bits() -> None:
    a = np.zeros((2, 2), dtype=np.int32)

    assert specify_int_bits(a) == 2
