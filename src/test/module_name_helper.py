"""A second file contributing a function to the module shared with test_module_name.py"""

from xenoform import compile


@compile(module_name="shared_module")
def triple(i: int) -> int:  # ty: ignore[empty-body]
    "return 3 * i;"
