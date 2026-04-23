import platform

import pytest

from xenoform import compile

if platform.system() != "Linux":
    pytest.skip("skipping linux-only tests", allow_module_level=True)


# function implementation is in a separate file
@compile(extra_includes=['"test_external_source.cpp"'], extra_include_paths=["../../src/test"])
def external_source(n: int) -> int:  # ty: ignore[empty-body]
    """
    return external_impl(n);
    """


def test_external_source() -> None:
    assert external_source(5) == 20


if __name__ == "__main__":
    test_external_source()
