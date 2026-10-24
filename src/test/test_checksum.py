import importlib
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from xenoform.config import XenoformConfig
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.errors import CompilationError
from xenoform.logger import Logger

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")


def _spec(body: str) -> ModuleSpec:
    return ModuleSpec().add_function(
        FunctionSpec(
            name="answer", body=body, arg_annotations="", scope=(), return_value_policy=ReturnValuePolicy.Automatic
        )
    )


@pytest.fixture
def ext_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh, empty extmodule root for each test"""
    root = tmp_path / "ext"
    monkeypatch.setattr(compile_module, "get_config", lambda: XenoformConfig(extmodule_root=root))
    return root


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_logger = MagicMock(spec=Logger)
    monkeypatch.setattr(compile_module, "logger", mock_logger)
    return mock_logger


def _logged(mock_logger: MagicMock, text: str) -> bool:
    return any(text in call.args[0] for call in mock_logger.call_args_list)


def test_checksum_is_named_after_the_binary() -> None:
    # the binary's name carries the ABI (e.g. cpython-314t-x86_64-linux-gnu), so the checksum's does too
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    module_dir = Path("ext/m_ext")
    assert compile_module._get_binary_path(module_dir, "m") == module_dir / f"m{ext_suffix}"
    assert compile_module._get_checksum_path(module_dir, "m") == module_dir / f"m{Path(ext_suffix).stem}.checksum"


def test_read_checksum_when_absent(tmp_path: Path) -> None:
    assert compile_module._read_checksum(tmp_path / "missing_ext", "m") is None


def _fake_module(module_dir: Path, module_name: str, *, checksum: str | None, binary: bool = True) -> None:
    """The files a build leaves, without running one: the check only looks at whether they exist and what they hold"""
    module_dir.mkdir(parents=True, exist_ok=True)
    if binary:
        compile_module._get_binary_path(module_dir, module_name).touch()
    if checksum is not None:
        compile_module._get_checksum_path(module_dir, module_name).write_text(checksum)


HASH = "a" * 64


def test_build_writes_checksum_then_reuses_it(ext_root: Path, logs: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    # the one real build here: everything else about the check is decided by the files it leaves
    spec = _spec("[]() { return 42; }")
    module = compile_module._check_build_fetch_module_impl("checksum_build", spec)
    assert module._answer() == 42
    assert _logged(logs, "not found")

    module_dir = ext_root / "checksum_build_ext"
    checksum = compile_module._read_checksum(module_dir, "checksum_build")
    assert checksum is not None
    assert checksum == module.__checksum__
    # the hash is of the unformatted source; the source on disk is formatted, with the hash embedded
    code, hashval = spec.make_source("checksum_build")
    assert checksum == hashval
    module_cpp = module_dir / "module.cpp"
    assert module_cpp.read_text() == compile_module.format_cpp(code.replace("__HASH__", hashval))

    # neither clang-format nor a build (both subprocesses) may run on the up-to-date path
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("up-to-date check must not run a subprocess or a build")

    monkeypatch.setattr(subprocess, "run", forbidden)
    mtime = module_cpp.stat().st_mtime_ns
    logs.reset_mock()

    module = compile_module._check_build_fetch_module_impl("checksum_build", spec)
    assert module._answer() == 42
    assert _logged(logs, "up-to-date")
    assert module_cpp.stat().st_mtime_ns == mtime


@pytest.mark.parametrize(
    ("binary", "checksum", "current", "log"),
    [
        (True, HASH, True, "up-to-date"),
        (True, "0" * 64, False, "outdated"),
        (True, None, False, "not found"),
        # a checksum without its binary isn't trusted
        (False, HASH, False, "not found"),
    ],
    ids=["matching", "stale", "missing", "no-binary"],
)
def test_is_current(
    tmp_path: Path, logs: MagicMock, binary: bool, checksum: str | None, current: bool, log: str
) -> None:
    _fake_module(tmp_path, "m", checksum=checksum, binary=binary)
    assert compile_module._is_current(tmp_path, "m", HASH) is current
    assert _logged(logs, log)


def test_other_abis_checksum_is_ignored(tmp_path: Path, logs: MagicMock) -> None:
    # another ABI's checksum holds the right hash, but it must not vouch for this ABI's binary
    _fake_module(tmp_path, "m", checksum=None)
    (tmp_path / "m.other-abi.checksum").write_text(HASH)
    assert not compile_module._is_current(tmp_path, "m", HASH)
    assert _logged(logs, "not found")


@pytest.mark.usefixtures("logs")
def test_failed_build_leaves_no_checksum(ext_root: Path) -> None:
    # an earlier build's binary and checksum, now outdated
    module_dir = ext_root / "checksum_failure_ext"
    _fake_module(module_dir, "checksum_failure", checksum="0" * 64)

    with pytest.raises(CompilationError):
        compile_module._check_build_fetch_module_impl("checksum_failure", _spec("[]() { return undefined_name; }"))
    # so nothing vouches for the old binary
    assert not compile_module._get_checksum_path(module_dir, "checksum_failure").exists()


_PROBE = """
import xenoform

@xenoform.compile()
def add(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i + j;"

assert add(1, 2) == 3
"""


def test_absolute_root_reused_from_another_cwd(tmp_path: Path) -> None:
    # regression: the old check imported the module by a name relative to the cwd, so with the root elsewhere
    # every new process found nothing and rebuilt
    (tmp_path / "src").mkdir()
    (tmp_path / "cwd").mkdir()
    script = tmp_path / "src" / "checksum_probe.py"
    script.write_text(_PROBE)
    env = os.environ | {"XENOFORM_EXTMODULE_ROOT": str(tmp_path / "build" / "ext"), "XENOFORM_VERBOSE": "1"}

    def run() -> str:
        p = subprocess.run(
            [sys.executable, str(script)], cwd=tmp_path / "cwd", env=env, capture_output=True, text=True, check=True
        )
        return p.stdout

    assert "not found" in run()
    second = run()
    assert "up-to-date" in second
    assert "(re)building" not in second
