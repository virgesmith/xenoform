import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from xenoform.config import XenoformConfig
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.logger import Logger

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")


@compile_module.compile()
def f() -> int:  # ty: ignore[empty-body]
    """
    return 42;
    """


@compile_module.compile()
def g() -> str:  # ty: ignore[empty-body]
    """
    return "hello";
    """


def test_cacheing(monkeypatch) -> None:
    mock_logger = MagicMock(spec=Logger)

    # 2. Monkeypatch the specific logger instance in the 'processor' module
    # The path is 'module_name.variable_name'
    monkeypatch.setattr(compile_module, "logger", mock_logger)

    f(), g(), f(), g()

    actual_logs = tuple(args[0][0] for args in mock_logger.call_args_list)

    # each of these should appear only once:
    for expected_log in (
        "imported compiled module test_caching_ext.test_caching",
        "redirected test_caching.f to compiled function test_caching_ext.test_caching._f",
        "redirected test_caching.g to compiled function test_caching_ext.test_caching._g",
    ):
        assert sum(expected_log == log for log in actual_logs) == 1


def _spec(body: str) -> ModuleSpec:
    spec = ModuleSpec()
    spec.add_function(
        FunctionSpec(
            name="answer",
            body=body,
            arg_annotations="",
            scope=(),
            return_value_policy=ReturnValuePolicy.Automatic,
        )
    )
    return spec


def test_rebuild_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Drives the not-found -> up-to-date -> outdated decisions of _check_build_fetch_module_impl directly (they sit
    # behind the cache on _get_module, so a normal @compile call only ever takes one of them per process). _build is
    # faked to leave the files a real build would, so no compiler runs: the real thing is tested in test_checksum.py
    monkeypatch.setattr(compile_module, "get_config", lambda: XenoformConfig(extmodule_root=tmp_path))
    monkeypatch.setattr(compile_module, "_load_module", MagicMock())
    built: list[str] = []

    def fake_build(module_dir: Path, module_name: str, _spec: ModuleSpec, _code: str, hashval: str) -> list:
        built.append(hashval)
        compile_module._get_binary_path(module_dir, module_name).touch()
        compile_module._get_checksum_path(module_dir, module_name).write_text(hashval)
        return []

    monkeypatch.setattr(compile_module, "_build", fake_build)

    # 1. nothing built yet -> build
    compile_module._check_build_fetch_module_impl("lifecycle", _spec("[]() { return 42; }"))
    assert len(built) == 1

    # 2. same source -> checksum matches -> no rebuild
    compile_module._check_build_fetch_module_impl("lifecycle", _spec("[]() { return 42; }"))
    assert len(built) == 1

    # 3. changed source -> checksum differs -> rebuild
    compile_module._check_build_fetch_module_impl("lifecycle", _spec("[]() { return 43; }"))
    assert len(built) == 2
    assert built[0] != built[1]
