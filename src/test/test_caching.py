import importlib
from unittest.mock import MagicMock

from xenoform.logger import Logger

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")


@compile_module.compile(verbose=True)  # type: ignore[untyped-decorator]
def f() -> int:  # type: ignore[empty-body]
    """
    return 42;
    """


@compile_module.compile(verbose=True)  # type: ignore[untyped-decorator]
def g() -> str:  # type: ignore[empty-body]
    """
    return "hello";
    """


def test_cacheing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
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
