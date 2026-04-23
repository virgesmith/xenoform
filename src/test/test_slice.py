from types import EllipsisType

import numpy as np
import numpy.typing as npt
import pytest

from xenoform import compile


@compile()
def parse_slice(length: int, s: slice) -> list[int]:  # ty: ignore[empty-body]
    """
    py::ssize_t start = 0, stop = 0, step = 0, slice_length = 0;
    if (!s.compute(10, &start, &stop, &step, &slice_length)) {
        throw py::error_already_set();
    }
    std::vector<int> indices;
    indices.reserve(slice_length);
    for (py::ssize_t i = 0; i < slice_length; ++i) {
        indices.push_back(start + i * step);
    }
    return indices;
    """


@compile()
def slice_shape(a: npt.NDArray[np.float64], *indices: int | slice | EllipsisType) -> list[int]:  # ty: ignore[empty-body]
    """
    py::array slice = a[indices];
    return std::vector<int>(slice.shape(), slice.shape() + slice.ndim());
    """


@compile()
def explicit_ellipsis(a: int | slice | EllipsisType) -> str:  # ty: ignore[empty-body]
    """
    if (std::get_if<int>(&a)) {
        return "int";
    } else if (std::get_if<py::slice>(&a)) {
        return "slice";
    } else if (std::get_if<py::ellipsis>(&a)) {
        return "ellipsis";
    }
    throw py::type_error("invalid arg type");
    """


def test_slice() -> None:
    assert parse_slice(10, slice(1, None, 2)) == [1, 3, 5, 7, 9]
    assert parse_slice(10, slice(None, None, -2)) == [9, 7, 5, 3, 1]
    assert parse_slice(10, slice(5, 1, -1)) == [5, 4, 3, 2]
    assert parse_slice(10, slice(None, 2, -2)) == [9, 7, 5, 3]


def test_ellipsis() -> None:
    assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., 2) == [3, 5]
    assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., slice(2, 3)) == [3, 5, 1]
    assert slice_shape(np.ones((2, 3, 5, 7)), ..., 1, slice(2, 4)) == [2, 3, 2]
    assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, ...) == [5, 7]
    assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, 3, slice(4, None, 2)) == [2]

    assert explicit_ellipsis(1) == "int"
    assert explicit_ellipsis(slice(1)) == "slice"
    assert explicit_ellipsis(...) == "ellipsis"
    with pytest.raises(TypeError):
        explicit_ellipsis("abc")  # ty: ignore[invalid-argument-type]


if __name__ == "__main__":
    test_ellipsis()
