from typing import Annotated

import numpy as np

from xenoform import compile


# this isn't actually a template specialisation it uses py::bytes rather than std::vector<unsigned char>
# pybind11 expects inputs to functions accepting std::vector to be numpy arrays. bytes is not supported
@compile()
def len_bytes(a: bytes) -> Annotated[int, "std::size_t"]:  # ty: ignore[empty-body]
    """
    py::buffer_info info(py::buffer(a).request());
    return static_cast<std::size_t>(info.size);
    """


def test_bytes() -> None:
    assert len_bytes("°C".encode()) == 3
    assert len_bytes(b"abc") == 3


@compile()
def len_byteseq(a: Annotated[bytes | bytearray, "py::buffer"]) -> Annotated[int, "std::size_t"]:  # ty: ignore[empty-body]
    """
    return static_cast<std::size_t>(a.request().size);
    """


def test_byteseq() -> None:
    assert len_byteseq(b"123") == 3
    assert len_byteseq(bytearray([1, 2, 3])) == 3
    # also works with numpy arrays as they support the buffer protocol
    assert len_byteseq(np.array([1, 2, 3])) == 3  # ty: ignore[invalid-argument-type]
