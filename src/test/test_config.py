import os
from pathlib import Path

import pytest

from xenoform.config import XenoformConfig, get_config
from xenoform.logger import Logger


def test_config() -> None:
    config = get_config()
    assert config.disable_ft is os.getenv("XENOFORM_DISABLE_FT")
    assert config.extmodule_root == Path("./ext")
    assert config.cpp_format == "file"
    assert config.verbose is os.getenv("XENOFORM_VERBOSE")


@pytest.mark.parametrize("value", ["", "  ", "1", "true", "0", "false"])
def test_verbose_env_presence_enables(monkeypatch, value: str) -> None:
    # presence-based flag: any value of XENOFORM_VERBOSE (even empty) enables verbose logging (issue #22)
    monkeypatch.setenv("XENOFORM_VERBOSE", value)
    assert XenoformConfig().verbose is not None


def test_verbose_env_absent_disables(monkeypatch) -> None:
    monkeypatch.delenv("XENOFORM_VERBOSE", raising=False)
    assert XenoformConfig().verbose is None


def test_logger_emits_when_enabled(capsys) -> None:
    Logger(enabled=True)("hello", "world")
    out = capsys.readouterr().out
    assert "hello world" in out


def test_logger_silent_when_disabled(capsys) -> None:
    Logger(enabled=False)("hello")
    assert capsys.readouterr().out == ""


if __name__ == "__main__":
    config = get_config()

    print(config)
    print(f"{os.getenv("XENOFORM_CPP_FORMAT")=}")
    print(f"{os.getenv("XENOFORM_DISABLE_FT")=}")
    print(f"{os.getenv("XENOFORM_EXTMODULE_ROOT")=}")
