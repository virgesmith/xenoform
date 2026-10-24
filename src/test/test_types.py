from typing import Annotated, Any

import numpy as np
import numpy.typing as npt
import pytest

from xenoform import compile
from xenoform.errors import CppTypeError
from xenoform.extension_types import HEADER_REQUIREMENTS, PyTypeTree, parse_annotation, translate_type
from xenoform.utils import deduplicate


def test_basic_types() -> None:
    cpptype = translate_type(int)
    assert str(cpptype) == "int"
    assert not cpptype.headers(HEADER_REQUIREMENTS)

    cpptype = translate_type(float)
    assert str(cpptype) == "double"
    assert not cpptype.headers(HEADER_REQUIREMENTS)

    cpptype = translate_type(bool)
    assert str(cpptype) == "bool"
    assert not cpptype.headers(HEADER_REQUIREMENTS)

    cpptype = translate_type(str)
    assert str(cpptype) == "std::string"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<string>"]

    cpptype = translate_type(bytes)
    assert str(cpptype) == "py::bytes"
    assert not cpptype.headers(HEADER_REQUIREMENTS)


def test_pytypetree_basic_types() -> None:
    tree = PyTypeTree(int)
    assert tree.type is int
    assert tree.subtypes == ()
    assert repr(tree) == "int"

    tree = PyTypeTree(float)
    assert tree.type is float
    assert tree.subtypes == ()
    assert repr(tree) == "float"

    tree = PyTypeTree(str)
    assert tree.type is str
    assert tree.subtypes == ()
    assert repr(tree) == "str"


def test_pytypetree_generic_types() -> None:
    tree = PyTypeTree(list[int])
    assert tree.type is list
    assert len(tree.subtypes) == 1
    assert tree.subtypes[0].type is int
    assert repr(tree) == "list[int]"

    tree = PyTypeTree(dict[str, float])
    assert tree.type is dict
    assert len(tree.subtypes) == 2
    assert tree.subtypes[0].type is str
    assert tree.subtypes[1].type is float
    assert repr(tree) == "dict[str, float]"


def test_pytypetree_tuple_and_ellipsis() -> None:
    tree = PyTypeTree(tuple[int, ...])
    assert tree.type is tuple
    assert len(tree.subtypes) == 2
    assert tree.subtypes[0].type is int
    assert tree.subtypes[1].type is Ellipsis
    assert repr(tree.subtypes[1]) == "..."


def test_pytypetree_raises_on_annotated() -> None:
    with pytest.raises(TypeError):
        PyTypeTree(Annotated[int, "foo"])  # ty: ignore[invalid-argument-type]


def test_specialised_types() -> None:
    cpptype = translate_type(list[int])
    assert str(cpptype) == "std::vector<int>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/stl.h>"]

    cpptype = translate_type(list[float])
    assert str(cpptype) == "std::vector<double>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/stl.h>"]

    cpptype = translate_type(set[str])
    assert str(cpptype) == "std::unordered_set<std::string>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/stl.h>", "<string>"]

    cpptype = translate_type(dict[str, list[bool]])
    assert str(cpptype) == "std::unordered_map<std::string, std::vector<bool>>"
    # pybind11/stl.h gets pulled in twice
    assert deduplicate(cpptype.headers(HEADER_REQUIREMENTS)) == ["<pybind11/stl.h>", "<string>"]


def test_numpy_types() -> None:
    cpptype = translate_type(npt.NDArray[int])  # ty: ignore[invalid-type-arguments, invalid-argument-type]
    assert str(cpptype) == "py::array_t<int>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/numpy.h>"]

    cpptype = translate_type(npt.NDArray[float])  # ty: ignore[invalid-type-arguments, invalid-argument-type]
    assert str(cpptype) == "py::array_t<double>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/numpy.h>"]

    # NDArray (an alias of np.ndarray before numpy 2.5, a PEP 695 alias from 2.5) and an explicit np.ndarray
    # annotation reach py::array_t by different routes, so both must be covered
    cpptype = translate_type(npt.NDArray[np.float64])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "py::array_t<double>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/numpy.h>"]

    cpptype = translate_type(np.ndarray[Any, np.dtype[np.float64]])
    assert str(cpptype) == "py::array_t<double>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == ["<pybind11/numpy.h>"]


def test_user_type() -> None:
    class X: ...

    with pytest.raises(CppTypeError):

        @compile()
        def process_x(x: X) -> None:
            ""

        process_x(X())

    @compile()
    def process_x_annotated(x: Annotated[X, "py::object"]) -> None:
        ""

    process_x_annotated(X())


def test_parse_annotation() -> None:
    t, q = parse_annotation(int)
    assert t is int
    assert q == {}

    t, q = parse_annotation(Annotated[int, "const int&"])  # ty: ignore[invalid-argument-type]
    assert t is int
    assert q == {"override": "const int&"}

    t, q = parse_annotation(Annotated[int, "uint32_t"])  # ty: ignore[invalid-argument-type]
    assert t is int
    assert q == {"override": "uint32_t"}

    with pytest.raises(TypeError):
        parse_annotation(Annotated[int, 42])  # ty: ignore[invalid-argument-type]

    # more than one metadata entry is ambiguous
    with pytest.raises(CppTypeError):
        parse_annotation(Annotated[int, "size_t", "uint32_t"])  # ty: ignore[invalid-argument-type]


def test_overridden_annotated_types() -> None:
    cpptype = translate_type(Annotated[int, "uint32_t"])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "uint32_t"

    cpptype = translate_type(Annotated[list[int], "py::list"])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "py::list"


def test_override_skips_unmapped_type_parameters() -> None:
    # the override is the whole C++ type, so type parameters with no default mapping mustn't raise
    class Unmapped: ...

    cpptype = translate_type(Annotated[list[Unmapped], "std::vector<Foo>"])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "std::vector<Foo>"
    assert cpptype.headers(HEADER_REQUIREMENTS) == []

    # ...including the dtype of a numpy array, which otherwise takes a special path
    cpptype = translate_type(Annotated[npt.NDArray[np.datetime64], "py::array"])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "py::array"

    # and an overridden T | U | None isn't turned into a std::optional
    cpptype = translate_type(Annotated[int | str | None, "py::object"])  # ty: ignore[invalid-argument-type]
    assert str(cpptype) == "py::object"

    # without an override, an unmapped type parameter is still an error
    with pytest.raises(CppTypeError):
        translate_type(list[Unmapped])


@pytest.mark.parametrize(
    ("pytype", "cpptype"),
    [
        (np.int8, "int8_t"),
        (np.int16, "int16_t"),
        (np.int32, "int32_t"),
        (np.int64, "int64_t"),
        (np.uint8, "uint8_t"),
        (np.uint16, "uint16_t"),
        (np.uint32, "uint32_t"),
        (np.uint64, "uint64_t"),
    ],
)
def test_numpy_int_widths(pytype: type, cpptype: str) -> None:
    assert str(translate_type(pytype)) == cpptype
    assert str(translate_type(npt.NDArray[pytype])) == f"py::array_t<{cpptype}>"  # ty: ignore[invalid-argument-type, invalid-type-form]


@compile(extra_includes=["<functional>"])
def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:  # ty: ignore[empty-body]
    """
    // Since this function body is put into an anonymous lambda, it cannot be called recursively.
    // Workaround: put the recursive implementation into a named lambda that captures its scope and call this
    // (NB cannot use auto for type deduction in this case)

    std::function<uint64_t(uint64_t)> impl = [&impl](uint64_t n) -> uint64_t {
        if (n < 2) {
            return n;
        }
        return impl(n - 2) + impl(n - 1);
    };
    return impl(n);
    """


def test_unsigned() -> None:
    assert fibonacci(10) == 55
    with pytest.raises(TypeError):
        fibonacci(-10)
