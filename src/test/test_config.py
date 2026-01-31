import os
from pathlib import Path

from xenoform.config import get_config


def test_config() -> None:
    config = get_config()
    assert config.disable_ft is os.getenv("XENOFORM_DISABLE_FT")
    assert config.extmodule_root == Path("./ext")
    assert config.cpp_format == "file"


if __name__ == "__main__":
    config = get_config()

    print(config)
    print(f"{os.getenv("XENOFORM_CPP_FORMAT")=}")
    print(f"{os.getenv("XENOFORM_DISABLE_FT")=}")
    print(f"{os.getenv("XENOFORM_EXTMODULE_ROOT")=}")
