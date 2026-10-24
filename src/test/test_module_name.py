import sys

import pytest

from xenoform import compile

from .module_name_helper import triple


@compile(module_name="renamed_module")
def renamed(i: int) -> int:  # ty: ignore[empty-body]
    "return i + 1;"


@compile(module_name="shared_module")
def double(i: int) -> int:  # ty: ignore[empty-body]
    "return 2 * i;"


def test_module_name_override() -> None:
    assert renamed(1) == 2
    # built into the named module, not one named after this file
    assert hasattr(sys.modules["renamed_module_ext.renamed_module"], "_renamed")
    assert "test_module_name_ext.test_module_name" not in sys.modules


def test_functions_from_two_files_share_a_module() -> None:
    assert double(2) == 4
    assert triple(2) == 6
    shared = sys.modules["shared_module_ext.shared_module"]
    assert hasattr(shared, "_double")
    assert hasattr(shared, "_triple")


@pytest.mark.parametrize(
    "name",
    [
        "",
        "1module",  # starts with a digit
        "my-module",  # hyphen
        "my.module",  # dotted
        "class",  # keyword
        "café",  # valid python, but CPython would look for a punycoded PyInitU_ symbol
    ],
)
def test_invalid_module_name(name: str) -> None:
    with pytest.raises(ValueError, match="module_name"):
        compile(module_name=name)
