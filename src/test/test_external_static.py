import platform
from typing import Annotated

import pytest

from xenoform import compile

if platform.system() != "Linux":
    pytest.skip("skipping linux-only tests", allow_module_level=True)


# test can call a function defined in a header
@compile(extra_includes=['"test_lib.h"'], extra_include_paths=["../../src/test"])
def fibonacci10() -> int:  # ty: ignore[empty-body]
    """
    return fibonacci_template<10>();
    """


def test_local_header() -> None:
    assert fibonacci10() == 55


# test can link to local (static) library
@compile(
    extra_includes=[
        '"test_lib.h"',
    ],
    extra_include_paths=["../../src/test"],
    extra_link_args=["-L../../src/test", "-lstatic"],
)
def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:  # ty: ignore[empty-body]
    """
    return fibonacci(n);
    """


def test_local_static_library(build_libs: None) -> None:  # noqa: ARG001
    assert fibonacci(10) == 55
    assert fibonacci(20) == fibonacci(18) + fibonacci(19) == 6765
