import numpy as np
import pytest

from xenoform import compile

# Each function returns its argument plus one, in its own type: overflowing at the type's maximum shows the C++
# type really has that width and signedness (C++20 defines the narrowing conversion as modular)


@compile()
def inc_i8(a: np.int8) -> np.int8:  # ty: ignore[empty-body]
    "return a + 1;"


@compile()
def inc_i16(a: np.int16) -> np.int16:  # ty: ignore[empty-body]
    "return a + 1;"


@compile()
def inc_u8(a: np.uint8) -> np.uint8:  # ty: ignore[empty-body]
    "return a + 1;"


@compile()
def inc_u16(a: np.uint16) -> np.uint16:  # ty: ignore[empty-body]
    "return a + 1;"


@compile()
def inc_u32(a: np.uint32) -> np.uint32:  # ty: ignore[empty-body]
    "return a + 1;"


@compile()
def inc_u64(a: np.uint64) -> np.uint64:  # ty: ignore[empty-body]
    "return a + 1;"


@pytest.mark.parametrize(
    ("f", "dtype"),
    [
        (inc_i8, np.int8),
        (inc_i16, np.int16),
        (inc_u8, np.uint8),
        (inc_u16, np.uint16),
        (inc_u32, np.uint32),
        (inc_u64, np.uint64),
    ],
)
def test_int_widths(f, dtype: type[np.integer]) -> None:
    info = np.iinfo(dtype)
    assert f(info.max - 1) == info.max
    # wraps to the minimum
    assert f(info.max) == info.min
    # pybind11 rejects a value out of the type's range
    with pytest.raises(TypeError):
        f(info.max + 1)
