import importlib
import shutil
from unittest.mock import MagicMock

from xenoform.config import get_config
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


def test_rebuild_lifecycle(monkeypatch) -> None:
    # Drives the not-found -> up-to-date -> outdated branches of _check_build_fetch_module_impl
    # directly (they sit behind the @cache on _get_module, so a normal @compile call only ever
    # exercises one of them per process). Uses a dedicated module name and a clean ext dir so the
    # sequence is deterministic regardless of any pre-existing build artifacts.
    mock_logger = MagicMock(spec=Logger)
    monkeypatch.setattr(compile_module, "logger", mock_logger)

    module_name = "caching_lifecycle"
    ext_dir = get_config().extmodule_root / f"{module_name}_ext"
    shutil.rmtree(ext_dir, ignore_errors=True)

    def logs() -> list[str]:
        return [call.args[0] for call in mock_logger.call_args_list]

    # 1. nothing built yet -> "not found" -> build
    module = compile_module._check_build_fetch_module_impl(module_name, _spec("[]() { return 42; }"))
    assert module._answer() == 42
    assert any("not found" in log for log in logs())
    assert any("(re)building" in log for log in logs())

    # 2. same source -> checksum matches -> "up-to-date", no rebuild
    mock_logger.reset_mock()
    compile_module._check_build_fetch_module_impl(module_name, _spec("[]() { return 42; }"))
    assert any("up-to-date" in log for log in logs())
    assert not any("(re)building" in log for log in logs())

    # 3. changed source -> checksum differs -> "outdated" -> rebuild
    # (the in-process module object is not reloaded by design, so we assert on the logs, not the value)
    mock_logger.reset_mock()
    compile_module._check_build_fetch_module_impl(module_name, _spec("[]() { return 43; }"))
    assert any("outdated" in log for log in logs())
    assert any("(re)building" in log for log in logs())

    shutil.rmtree(ext_dir, ignore_errors=True)
