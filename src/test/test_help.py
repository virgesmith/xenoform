from xenoform import compile
from xenoform.compile import _get_function

docstr = """This is a test function
used to test the help system
It is otherwise useless
"""


@compile(help=docstr, verbose=True)
def documented_function(n: int, *, x: float = 3.1) -> float:  # ty: ignore[empty-body]
    """
    return n + x;
    """


def test_documented_function() -> None:
    assert documented_function.__doc__ == docstr
    # access pybind11 module directly
    # seems to be a bug in mypy: it says var-annotated is needed but when you add it, then says it not needed
    # when you remove it, the error goes away. If you delete .mypy_cache it returns
    ext_func = _get_function("test_help", "_documented_function")
    assert docstr in (ext_func.__doc__ or "")


if __name__ == "__main__":
    test_documented_function()
