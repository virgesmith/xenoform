import subprocess

import clang_format

from xenoform import utils
from xenoform.config import XenoformConfig


def test_format() -> None:
    cmd = [clang_format.get_executable("clang-format")]

    result = subprocess.run(cmd, input="int main( ) {}", capture_output=True, text=True, check=True)

    assert result.stdout == "int main() {}"


def test_format_cpp_failure_returns_unformatted(monkeypatch, capsys) -> None:
    # an invalid --style makes clang-format exit non-zero; format_cpp must swallow the error
    # and return the original (unformatted) source rather than raising
    monkeypatch.setattr(utils, "get_config", lambda: XenoformConfig(cpp_format="notarealstyle"))

    code = "int  main( ){}"
    assert utils.format_cpp(code) == code
    assert "clang-format failed" in capsys.readouterr().out
