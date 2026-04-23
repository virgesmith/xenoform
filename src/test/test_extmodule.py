from typing import Annotated

import xenoform_test_ext

from xenoform import compile


@compile(extra_include_paths=["../../src/test/xenoform-test-ext/include"], extra_includes=['"module.h"'])
def make_object(n: int) -> Annotated[xenoform_test_ext.ExtClass, "ext_ns::ExtClass"]:  # ty: ignore[empty-body]
    """
    return  ext_ns::ExtClass(n);
    """


@compile(extra_include_paths=["../../src/test/xenoform-test-ext/include"], extra_includes=['"module.h"'])
def mutate_object(obj: Annotated[xenoform_test_ext.ExtClass, "ext_ns::ExtClass&"], n: int) -> None:
    """
    obj.set(n);
    """


@compile()
def mutate_vector_val(vec: Annotated[xenoform_test_ext.vec_uint64_t, "std::vector<uint64_t>"], n: int) -> None:
    """
    for (auto& i: vec) i += n;
    """


@compile()
def mutate_vector_ref(vec: Annotated[xenoform_test_ext.vec_uint64_t, "std::vector<uint64_t>&"], n: int) -> None:
    """
    for (auto& i: vec) i += n;
    """


@compile()
def mutate_vector_ptr(vec: Annotated[xenoform_test_ext.vec_uint64_t, "std::vector<uint64_t>*"], n: int) -> None:
    """
    for (auto& i: *vec) i += n;
    """


def test_ext_vector() -> None:
    vec = xenoform_test_ext.vec_uint64_t(range(10))
    assert all(v == i for i, v in enumerate(vec))  # ty: ignore[invalid-argument-type,, var-annotated]

    # function in other module works as expected
    xenoform_test_ext.mutate(vec)  # increments each element
    assert all(v == i for i, v in enumerate(vec, start=1))  # ty: ignore[invalid-argument-type,, var-annotated]

    # can mutate by ref
    mutate_vector_ref(vec, 2)
    assert all(v == i for i, v in enumerate(vec, start=3))  # ty: ignore[invalid-argument-type,, var-annotated]
    # can mutate by ptr
    mutate_vector_ptr(vec, 3)
    assert all(v == i for i, v in enumerate(vec, start=6))  # ty: ignore[invalid-argument-type,, var-annotated]
    # can't mutate by val
    mutate_vector_val(vec, 4)
    assert all(v == i for i, v in enumerate(vec, start=6))  # ty: ignore[invalid-argument-type,, var-annotated]


def test_ext_object() -> None:
    obj = xenoform_test_ext.ExtClass(42)
    obj2 = make_object(42)
    assert obj.get() == obj2.get() == 42
    mutate_object(obj, 0)
    assert obj.get() == 0


if __name__ == "__main__":
    test_ext_vector()
    test_ext_object()
