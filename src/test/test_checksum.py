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

# rebuilding a module that this process has loaded fails on Windows: the loaded .pyd is locked
skip_rebuild_on_windows = pytest.mark.skipif(sys.platform == "win32", reason="a loaded .pyd can't be overwritten")


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


def test_build_writes_checksum(ext_root: Path, logs: MagicMock) -> None:
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
    assert (module_dir / "module.cpp").read_text() == compile_module.format_cpp(code.replace("__HASH__", hashval))


def test_up_to_date_check_runs_no_subprocess(ext_root: Path, logs: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    compile_module._check_build_fetch_module_impl("checksum_reuse", _spec("[]() { return 42; }"))
    module_cpp = ext_root / "checksum_reuse_ext" / "module.cpp"
    mtime = module_cpp.stat().st_mtime_ns

    # neither clang-format nor a build (both subprocesses) may run
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("up-to-date check must not run a subprocess or a build")

    monkeypatch.setattr(subprocess, "run", forbidden)
    logs.reset_mock()

    module = compile_module._check_build_fetch_module_impl("checksum_reuse", _spec("[]() { return 42; }"))
    assert module._answer() == 42
    assert _logged(logs, "up-to-date")
    assert module_cpp.stat().st_mtime_ns == mtime


@skip_rebuild_on_windows
def test_missing_stale_or_other_abi_checksum_rebuilds(ext_root: Path, logs: MagicMock) -> None:
    spec = _spec("[]() { return 42; }")
    compile_module._check_build_fetch_module_impl("checksum_rebuild", spec)
    module_dir = ext_root / "checksum_rebuild_ext"
    checksum_path = compile_module._get_checksum_path(module_dir, "checksum_rebuild")
    good_hash = checksum_path.read_text()

    # stale
    checksum_path.write_text("0" * 64)
    logs.reset_mock()
    compile_module._check_build_fetch_module_impl("checksum_rebuild", spec)
    assert _logged(logs, "outdated")
    assert checksum_path.read_text() == good_hash

    # missing, but another ABI's checksum holds the right hash: it must not vouch for this ABI's binary
    checksum_path.unlink()
    (module_dir / "checksum_rebuild.other-abi.checksum").write_text(good_hash)
    logs.reset_mock()
    compile_module._check_build_fetch_module_impl("checksum_rebuild", spec)
    assert _logged(logs, "not found")
    assert _logged(logs, "(re)building")

    # a checksum without its binary isn't trusted
    compile_module._get_binary_path(module_dir, "checksum_rebuild").unlink()
    logs.reset_mock()
    compile_module._check_build_fetch_module_impl("checksum_rebuild", spec)
    assert _logged(logs, "not found")
    assert _logged(logs, "(re)building")


@skip_rebuild_on_windows
def test_failed_build_leaves_no_checksum(ext_root: Path, logs: MagicMock) -> None:
    good, broken = _spec("[]() { return 42; }"), _spec("[]() { return undefined_name; }")
    compile_module._check_build_fetch_module_impl("checksum_failure", good)
    checksum_path = compile_module._get_checksum_path(ext_root / "checksum_failure_ext", "checksum_failure")

    with pytest.raises(CompilationError):
        compile_module._check_build_fetch_module_impl("checksum_failure", broken)
    assert not checksum_path.exists()

    # the old binary is still there, but nothing vouches for it, so the good source is rebuilt
    logs.reset_mock()
    compile_module._check_build_fetch_module_impl("checksum_failure", good)
    assert _logged(logs, "not found")
    assert checksum_path.exists()


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
