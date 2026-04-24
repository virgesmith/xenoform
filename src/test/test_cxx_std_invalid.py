import platform

import pytest

from xenoform import CompilationError, compile


@pytest.mark.skipif(platform.system() == "Windows", reason="cl.exe only warns")
def test_cxx_std_invalid() -> None:
    with pytest.raises(CompilationError):

        @compile(cxx_std=24)
        def f(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 2;"

        f(3)


if __name__ == "__main__":
    test_cxx_std_invalid()
