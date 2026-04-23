import pytest

from xenoform import compile


def test_cxx_std() -> None:
    with pytest.raises(ValueError):

        @compile(cxx_std=23)
        def f(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 2;"

        @compile(cxx_std=20)
        def g(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 3 == 0;"

        f(3)
        g(3)


if __name__ == "__main__":
    test_cxx_std()
