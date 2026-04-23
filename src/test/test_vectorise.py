import numpy as np
import pytest

from xenoform import compile


@compile(vectorise=True)
def maxv(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i < j ? j : i;"


def test_vectorised_max() -> None:
    assert all(maxv(range(5), range(4, -1, -1)) == [4, 3, 2, 3, 4])  # ty: ignore[invalid-argument-type,, comparison-overlap]


def test_vectorised_max_scalar() -> None:
    assert maxv(0, 1) == 1


def test_vectorised_max_incompatible() -> None:
    with pytest.raises(RuntimeError):
        maxv(range(5), range(6))  # ty: ignore[invalid-argument-type]


def test_vectorised_max_mixed_1d() -> None:
    assert all(maxv(range(5), 3) == [3, 3, 3, 3, 4])  # ty: ignore[invalid-argument-type,, comparison-overlap]


def test_vectorised_max_mixed_2d() -> None:
    a = np.ones((3, 3))
    b = np.array([0, 1, 2])
    assert (maxv(a, b) == np.array([[1, 1, 2]] * 3)).all()  # ty: ignore[invalid-argument-type,, attr-defined]
