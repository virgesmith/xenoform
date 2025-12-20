import subprocess

import clang_format  # type: ignore[import-untyped]


def test_format() -> None:
    cmd = [clang_format.get_executable("clang-format")]

    result = subprocess.run(cmd, input="int main( ) {}", capture_output=True, text=True, check=True)

    assert result.stdout == "int main() {}"
