import subprocess
from pathlib import Path

import pytest

get_executable = pytest.importorskip("clang_format").get_executable


def main(cppfile: Path) -> None:
    executable = get_executable("clang-format")

    result = subprocess.run([executable, cppfile], stdout=subprocess.PIPE)

    if result.returncode == 0:
        with cppfile.open("w") as fd:
            fd.write(result.stdout.decode())


if __name__ == "__main__":
    main(Path("ext/loop_ext/module.cpp"))
