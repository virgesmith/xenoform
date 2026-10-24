import importlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock

import pytest

from xenoform.config import XenoformConfig
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.logger import Logger

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")

N = 4


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


def _count_logged(mock_logger: MagicMock, text: str) -> int:
    return sum(text in call.args[0] for call in mock_logger.call_args_list)


_PROBE = """
import xenoform

@xenoform.compile()
def add(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i + j;"

assert add(1, 2) == 3
"""


def test_processes_building_the_same_module(tmp_path: Path) -> None:
    # all start at once and find nothing built: one builds, the rest wait for its lock and then find it current
    script = tmp_path / "concurrency_probe.py"
    script.write_text(_PROBE)
    env = os.environ | {"XENOFORM_EXTMODULE_ROOT": str(tmp_path / "ext"), "XENOFORM_VERBOSE": "1"}

    procs = [
        subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.PIPE, text=True) for _ in range(N)
    ]
    outputs = [p.communicate(timeout=300)[0] for p in procs]

    assert all(p.returncode == 0 for p in procs)
    assert sum("(re)building" in out for out in outputs) == 1


@pytest.mark.usefixtures("ext_root")
def test_threads_building_the_same_module(logs: MagicMock) -> None:
    barrier = Barrier(N)

    def build(_: int) -> int:
        barrier.wait()
        module = compile_module._check_build_fetch_module_impl("concurrency_same", _spec("[]() { return 42; }"))
        return module._answer()

    with ThreadPoolExecutor(N) as pool:
        assert list(pool.map(build, range(N))) == [42] * N
    assert _count_logged(logs, "(re)building") == 1


def test_recheck_under_the_lock(ext_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # stale when first checked, current once the lock is held: someone else built it while we waited
    monkeypatch.setattr(compile_module, "_is_current", MagicMock(side_effect=[False, True]))
    build = MagicMock()
    monkeypatch.setattr(compile_module, "_build", build)
    monkeypatch.setattr(compile_module, "_load_module", MagicMock())

    compile_module._check_build_fetch_module_impl("concurrency_recheck", _spec("[]() { return 42; }"))

    build.assert_not_called()
    assert (ext_root / "concurrency_recheck_ext" / ".build.lock").exists()


def test_up_to_date_path_takes_no_lock(ext_root: Path) -> None:
    spec = _spec("[]() { return 42; }")
    compile_module._check_build_fetch_module_impl("concurrency_nolock", spec)
    lock_path = ext_root / "concurrency_nolock_ext" / ".build.lock"
    lock_path.unlink(missing_ok=True)

    compile_module._check_build_fetch_module_impl("concurrency_nolock", spec)
    assert not lock_path.exists()


def test_threads_loading_the_same_module(ext_root: Path) -> None:
    # a smoke test: the race it guards against is down to timing, so it can't reliably fail without the lock
    module_dir = ext_root / "concurrency_load_ext"
    module_dir.mkdir(parents=True)
    spec = _spec("[]() { return 42; }")
    code, hashval = spec.make_source("concurrency_load")
    compile_module._build(module_dir, "concurrency_load", spec, code, hashval)

    barrier = Barrier(N)
    binary_path = compile_module._get_binary_path(module_dir, "concurrency_load")

    def load(_: int) -> object:
        barrier.wait()
        return compile_module._load_module("concurrency_load_ext.concurrency_load", binary_path)

    with ThreadPoolExecutor(N) as pool:
        modules = list(pool.map(load, range(N)))
    assert all(m is modules[0] for m in modules)


def test_threads_building_different_modules(ext_root: Path) -> None:
    # builds share no process state (cwd, stdout), so threads can build different modules at once
    barrier = Barrier(N)

    def build(i: int) -> int:
        barrier.wait()
        module = compile_module._check_build_fetch_module_impl(f"concurrency_{i}", _spec(f"[]() {{ return {i}; }}"))
        return module._answer()

    with ThreadPoolExecutor(N) as pool:
        assert list(pool.map(build, range(N))) == list(range(N))

    for i in range(N):
        log = (ext_root / f"concurrency_{i}_ext" / "build.log").read_text(errors="replace")
        assert f"concurrency_{i}" in log
        assert not any(f"concurrency_{j}" in log for j in range(N) if j != i)
