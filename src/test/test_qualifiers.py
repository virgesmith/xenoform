from typing import Annotated

from xenoform import compile
from xenoform.extension_types import CppQualifier


@compile()
def vector_sum_using_py(v: Annotated[list[int], "py::list"]) -> int:  # type: ignore[empty-body]
    """
    int sum = 0;
    for (py::handle item: v) {
      sum += item.cast<int>(); // needs type checking
    }
    return sum;
    """


@compile(extra_includes=["<numeric>"])
def vector_sum_using_cptrc(v: Annotated[list[int], CppQualifier.CPtrC]) -> int:  # type: ignore[empty-body]
    """
    return std::accumulate(v->begin(), v->end(), 0);
    """


@compile(extra_includes=["<numeric>"])
def vector_sum_using_cref(v: Annotated[list[int], CppQualifier.CRef]) -> int:  # type: ignore[empty-body]
    """
    return std::accumulate(v.begin(), v.end(), 0);
    """


@compile(extra_includes=["<numeric>"])
def vector_sum_using_rref(v: Annotated[list[int], CppQualifier.RRef]) -> int:  # type: ignore[empty-body]
    """
    return std::accumulate(v.begin(), v.end(), 0);
    """


def test_qualifiers() -> None:
    # use an override type
    assert vector_sum_using_py([1, 2, 3, 4]) == 10
    assert vector_sum_using_py(list(range(5))) == 10
    # use a const pointer to const
    assert vector_sum_using_cptrc([1, 2, 3, 4]) == 10
    assert vector_sum_using_cptrc(range(5)) == 10  # type: ignore[arg-type]
    # use a const reference
    assert vector_sum_using_cref([1, 2, 3, 4]) == 10
    assert vector_sum_using_cref(range(5)) == 10  # type: ignore[arg-type]
    # use an rvalue reference
    assert vector_sum_using_rref([1, 2, 3, 4]) == 10
    assert vector_sum_using_rref(range(5)) == 10  # type: ignore[arg-type]


if __name__ == "__main__":
    test_qualifiers()
