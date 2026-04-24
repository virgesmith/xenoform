import platform
from typing import Annotated

import pytest

from xenoform import compile

if platform.system() != "Linux":
    pytest.skip("skipping linux-only tests", allow_module_level=True)


# test can link to local shared library
@compile(
    extra_includes=[
        '"test_lib.h"',
    ],
    extra_include_paths=["../../src/test"],
    extra_link_args=["-L../../src/test", "-lshared", "-Wl,-rpath=src/test"],
)
def lucas(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:  # ty: ignore[empty-body]
    """
    return lucas(n);
    """


def test_local_shared_library(build_libs: None) -> None:  # noqa: ARG001
    # 2, 1, 3, 4, 7, 11, 18, 29, 47, 76, 123
    assert lucas(10) == 123
