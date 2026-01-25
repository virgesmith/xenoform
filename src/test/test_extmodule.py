from typing import Annotated

import xenoform_test_ext

from xenoform import compile
from xenoform.extension_types import DEFAULT_TYPE_MAPPING, CppQualifier


# TODO add functionality to register bound types
def register_type(pytype: type, cpptype: str) -> None:
    DEFAULT_TYPE_MAPPING[pytype] = cpptype


register_type(xenoform_test_ext.ExtClass, "ext_ns::ExtClass")
register_type(xenoform_test_ext.vec_uint64_t, "std::vector<uint64_t>")


@compile(extra_include_paths=["../../src/test/xenoform-test-ext/include"], extra_includes=['"module.h"'])
def make_object(n: int) -> xenoform_test_ext.ExtClass:
    """
    return ext_ns::ExtClass(n);
    """


@compile(extra_include_paths=["../../src/test/xenoform-test-ext/include"], extra_includes=['"module.h"'])
def mutate_object(obj: Annotated[xenoform_test_ext.ExtClass, CppQualifier.Ref], n: int) -> None:
    """
    obj.set(n);
    """


@compile(extra_include_paths=["src/test/xenoform_test_ext/include"], extra_includes=['"module.h"'])
def mutate_vector_ref(vec: Annotated[xenoform_test_ext.vec_uint64_t, CppQualifier.Ref], n: int) -> None:
    """
    for (auto& i: vec) i += n;
    """


@compile(extra_include_paths=["src/test/xenoform_test_ext/include"], extra_includes=['"module.h"'])
def mutate_vector_ptr(vec: Annotated[xenoform_test_ext.vec_uint64_t, CppQualifier.CPtr], n: int) -> None:
    """
    for (auto& i: *vec) i += n;
    """


def test_ext_vector() -> None:
    vec = xenoform_test_ext.vec_uint64_t(range(10))
    assert all(v == i for i, v in enumerate(vec))
    xenoform_test_ext.mutate(vec)  # increments each element
    assert all(v == i for i, v in enumerate(vec, start=1))
    mutate_vector_ref(vec, 2)
    print(vec)
    assert all(v == i for i, v in enumerate(vec, start=3))
    mutate_vector_ptr(vec, 2)
    print(vec)


def test_ext_object() -> None:
    obj = xenoform_test_ext.ExtClass(42)
    obj2 = make_object(42)
    assert obj.get() == obj2.get() == 42
    mutate_object(obj, 0)
    assert obj.get() == 0


#     v = vec_double_t([float(i) for i in range(10)])
#     assert stl_binding_by_value(v) == len(v)

#     stl_binding_by_ref(v)
#     print(v)
#     # # assert v[-1] == 10

#     c = make_collatz(10)
#     print(id(c))
#     mutate_collatz(c)
#     print(Itr(c).collect())  # should start with 5

#     cv = make_collatz_vec(10)
#     print([next(c) for c in cv])
#     print(id(cv))
#     mutate_collatz_vec(cv)
#     print([next(c) for c in cv])


if __name__ == "__main__":
    test_ext_vector()
    test_ext_object()
