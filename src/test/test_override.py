from typing import Annotated

from xenoform import compile


@compile()
def vector_sum_using_py(v: Annotated[list[int], "py::list"]) -> int:  # ty: ignore[empty-body]
    """
    int sum = 0;
    for (py::handle item: v) {
      sum += item.cast<int>(); // needs type checking
    }
    return sum;
    """


@compile(extra_includes=["<numeric>", "<pybind11/stl.h>"])
def vector_sum_using_cptrc(v: Annotated[list[int], "const std::vector<int>* const"]) -> int:  # ty: ignore[empty-body]
    """
    return std::accumulate(v->begin(), v->end(), 0);
    """


@compile(extra_includes=["<numeric>", "<pybind11/stl.h>"])
def vector_sum_using_cref(v: Annotated[list[int], "const std::vector<int>&"]) -> int:  # ty: ignore[empty-body]
    """
    return std::accumulate(v.begin(), v.end(), 0);
    """


@compile(extra_includes=["<numeric>", "<pybind11/stl.h>"])
def vector_sum_using_rref(v: Annotated[list[int], "std::vector<int>&&"]) -> int:  # ty: ignore[empty-body]
    """
    return std::accumulate(v.begin(), v.end(), 0);
    """


def test_overrides() -> None:
    # use an override type
    assert vector_sum_using_py([1, 2, 3, 4]) == 10
    assert vector_sum_using_py(list(range(5))) == 10
    # use a const pointer to const
    assert vector_sum_using_cptrc([1, 2, 3, 4]) == 10
    assert vector_sum_using_cptrc(range(5)) == 10  # ty: ignore[invalid-argument-type]
    # use a const reference
    assert vector_sum_using_cref([1, 2, 3, 4]) == 10
    assert vector_sum_using_cref(range(5)) == 10  # ty: ignore[invalid-argument-type]
    # use an rvalue reference
    assert vector_sum_using_rref([1, 2, 3, 4]) == 10
    assert vector_sum_using_rref(range(5)) == 10  # ty: ignore[invalid-argument-type]


@compile()
def list_append_byref(v: Annotated[list[int], "py::list&"]) -> None:
    """
    v.append(42);
    """


@compile()
def list_append_byptr(v: Annotated[list[int], "py::list* const"]) -> None:
    """
    v->append(43);
    """


@compile()
def list_append_byval(v: Annotated[list[int], "py::list"]) -> None:
    """
    v.append(0);
    """


@compile()
def dict_modify_byval(d: Annotated[dict[str, int], "py::dict"], value: int) -> None:
    """
    d["key"] = value;
    """


@compile()
def set_modify_byval(s: Annotated[set[int], "py::set"], value: int) -> None:
    """
    s.add(value);
    """


# pybind11's bytearray type doesnt seem to support modification (see pytypes.h)


def test_mutable_types() -> None:
    a: list[int] = []
    list_append_byval(a)
    assert len(a) == 1
    assert a[-1] == 0
    list_append_byref(a)
    assert len(a) == 2
    assert a[-1] == 42
    list_append_byptr(a)
    assert len(a) == 3
    assert a[-1] == 43

    d: dict[str, int] = {}
    dict_modify_byval(d, 1)
    assert len(d) == 1
    assert d["key"] == 1
    dict_modify_byval(d, 10)
    assert len(d) == 1
    assert d["key"] == 10

    s: set[int] = set()
    set_modify_byval(s, 1)
    assert len(s) == 1
    assert s == {1}
    set_modify_byval(s, 1)
    assert len(s) == 1
    assert s == {1}
    set_modify_byval(s, 2)
    assert len(s) == 2
    assert s == {1, 2}


if __name__ == "__main__":
    test_mutable_types()
    test_overrides()
