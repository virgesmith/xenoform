from typing import Annotated

import numpy.typing as npt
import pytest

from xenoform import compile
from xenoform.errors import CppTypeError
from xenoform.extension_types import CppQualifier, PyTypeTree, header_requirements, parse_annotation, translate_type
from xenoform.utils import _deduplicate


def test_basic_types() -> None:
    cpptype = translate_type(int)
    assert str(cpptype) == "int"
    assert not cpptype.headers(header_requirements)

    cpptype = translate_type(float)
    assert str(cpptype) == "double"
    assert not cpptype.headers(header_requirements)

    cpptype = translate_type(bool)
    assert str(cpptype) == "bool"
    assert not cpptype.headers(header_requirements)

    cpptype = translate_type(str)
    assert str(cpptype) == "std::string"
    assert cpptype.headers(header_requirements) == ["<string>"]

    cpptype = translate_type(bytes)
    assert str(cpptype) == "py::bytes"
    assert not cpptype.headers(header_requirements)


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
        PyTypeTree(Annotated[int, "foo"])  # type: ignore[arg-type]


def test_specialised_types() -> None:
    cpptype = translate_type(list[int])
    assert str(cpptype) == "std::vector<int>"
    assert cpptype.headers(header_requirements) == ["<pybind11/stl.h>"]

    cpptype = translate_type(list[float])
    assert str(cpptype) == "std::vector<double>"
    assert cpptype.headers(header_requirements) == ["<pybind11/stl.h>"]

    cpptype = translate_type(set[str])
    assert str(cpptype) == "std::unordered_set<std::string>"
    assert cpptype.headers(header_requirements) == ["<pybind11/stl.h>", "<string>"]

    cpptype = translate_type(dict[str, list[bool]])
    assert str(cpptype) == "std::unordered_map<std::string, std::vector<bool>>"
    # pybind11/stl.h gets pulled in twice
    assert _deduplicate(cpptype.headers(header_requirements)) == ["<pybind11/stl.h>", "<string>"]


def test_numpy_types() -> None:
    cpptype = translate_type(npt.NDArray[int])
    assert str(cpptype) == "py::array_t<int>"
    assert cpptype.headers(header_requirements) == ["<pybind11/numpy.h>"]

    cpptype = translate_type(npt.NDArray[float])
    assert str(cpptype) == "py::array_t<double>"
    assert cpptype.headers(header_requirements) == ["<pybind11/numpy.h>"]


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

    t, q = parse_annotation(Annotated[int, CppQualifier.CRef])  # type: ignore[arg-type]
    assert t is int
    assert q == {"qualifier": CppQualifier.CRef}

    t, q = parse_annotation(Annotated[int, "uint32_t"])  # type: ignore[arg-type]
    assert t is int
    assert q == {"override": "uint32_t"}

    with pytest.raises(TypeError):
        parse_annotation(Annotated[int, 42])  # type: ignore[arg-type]


def test_qualified_annotated_types() -> None:
    cpptype = translate_type(Annotated[int, CppQualifier.CRef])  # type: ignore[arg-type]
    assert str(cpptype) == "const int&"

    cpptype = translate_type(Annotated[list[float], CppQualifier.CPtrC])  # type: ignore[arg-type]
    assert str(cpptype) == "const std::vector<double>* const"


def test_overridden_annotated_types() -> None:
    cpptype = translate_type(Annotated[int, "uint32_t"])  # type: ignore[arg-type]
    assert str(cpptype) == "uint32_t"

    cpptype = translate_type(Annotated[list[int], "py::list"])  # type: ignore[arg-type]
    assert str(cpptype) == "py::list"


@compile(extra_includes=["<functional>"])
def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:  # type: ignore[empty-body]
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
