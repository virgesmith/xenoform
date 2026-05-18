from subprocess import Popen

import pytest


@pytest.fixture(scope="session")
def build_libs() -> None:
    cmds = [
        ["g++", "-fPIC", "-c", "test_lib.cpp", "-o", "test_lib.o"],
        ["ar", "rcs", "libstatic.a", "test_lib.o"],
        ["g++", "-shared", "test_lib.o", "-o", "libshared.so"],
    ]

    for cmd in cmds:
        p = Popen(cmd, cwd="src/test")
        p.communicate(timeout=30)
        assert p.returncode == 0
