from typing import Annotated

from xenoform import compile


@compile()
def vector_sum_using_py(v: Annotated[list[int], "py::list"]) -> int:  # type: ignore[empty-body]
    """
    int sum = 0;
    for (py::handle item: v) {
      sum += item.cast<int>(); // needs type checking
    }
    return sum;
    """


# # TODO why doesnt this work now?
# @compile(extra_includes=["<numeric>"])
# def vector_sum_using_cptrc(v: Annotated[list[int], "const std::vector<int>* const"]) -> int:  # type: ignore[empty-body]
#     """
#     return std::accumulate(v->begin(), v->end(), 0);
#     """


# # TODO why doesnt this work now?
# @compile(extra_includes=["<numeric>"])
# def vector_sum_using_cref(v: Annotated[list[int], "const std::vector<int>&"]) -> int:  # type: ignore[empty-body]
#     """
#     return std::accumulate(v.begin(), v.end(), 0);
#     """


# # TODO why doesnt this work now?
# @compile(extra_includes=["<numeric>"])
# def vector_sum_using_rref(v: Annotated[list[int], "std::vector<int>&&"]) -> int:  # type: ignore[empty-body]
#     """
#     return std::accumulate(v.begin(), v.end(), 0);
#     """


def test_overrides() -> None:
    # use an override type
    assert vector_sum_using_py([1, 2, 3, 4]) == 10
    assert vector_sum_using_py(list(range(5))) == 10
    # use a const pointer to const
    # assert vector_sum_using_cptrc([1, 2, 3, 4]) == 10
    # assert vector_sum_using_cptrc(range(5)) == 10  # type: ignore[arg-type]
    # use a const reference
    # assert vector_sum_using_cref([1, 2, 3, 4]) == 10
    # assert vector_sum_using_cref(range(5)) == 10  # type: ignore[arg-type]
    # use an rvalue reference
    # assert vector_sum_using_rref([1, 2, 3, 4]) == 10
    # assert vector_sum_using_rref(range(5)) == 10  # type: ignore[arg-type]


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


# TODO:
# check bytearray, set, dict all mutable by value
# @compile()
# def bytearray_mutate(b: bytearray) -> None:
#     """
#     for (py::handle item: v) {
#       item += 1;
#     }
#     """


def test_mutable_types() -> None:
    x: list[int] = []
    list_append_byval(x)
    assert len(x) == 1
    assert x[-1] == 0
    list_append_byref(x)
    assert len(x) == 2
    assert x[-1] == 42
    list_append_byptr(x)
    assert len(x) == 3
    assert x[-1] == 43


if __name__ == "__main__":
    test_mutable_types()
    test_overrides()
