import importlib
import warnings
from pathlib import Path

import pytest

from xenoform import CppDiagnostic, CppWarning
from xenoform.config import XenoformConfig
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")

# an uninitialised unused local warns on every compiler at its default level: gcc and clang -Wunused-variable
# (-Wall), MSVC C4101 (/W3). An initialised one is only level 4 on MSVC
WARNS = "[]() { int unused; return 2; }"
CLEAN = "[]() { return 2; }"


def _spec(body: str) -> ModuleSpec:
    return ModuleSpec().add_function(
        FunctionSpec(name="f", body=body, arg_annotations="", scope=(), return_value_policy=ReturnValuePolicy.Automatic)
    )


@pytest.fixture
def ext_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(compile_module, "get_config", lambda: XenoformConfig(extmodule_root=tmp_path))
    return tmp_path


@pytest.mark.usefixtures("ext_root")
def test_warning_is_issued() -> None:
    with pytest.warns(CppWarning) as record:
        module = compile_module._check_build_fetch_module_impl("warns", _spec(WARNS))
    assert module._f() == 2

    # the unused variable's warning: a compiler may add others of its own
    (warning,) = [w for w in record if issubclass(w.category, CppWarning) and "unused" in str(w.message)]
    assert str(warning.message).startswith("compiler warning in module 'warns_ext.warns':\n")
    # the parsed diagnostic is attached
    diagnostic = warning.message.diagnostic  # ty: ignore[unresolved-attribute]
    assert isinstance(diagnostic, CppDiagnostic)
    assert diagnostic.level == "warning"
    assert diagnostic.file.replace("\\", "/").endswith("module.cpp")
    assert "unused" in diagnostic.rendered
    # attributed to the first frame outside xenoform: here, this test
    assert warning.filename == __file__


@pytest.mark.usefixtures("ext_root")
def test_up_to_date_module_doesnt_repeat_warnings() -> None:
    with pytest.warns(CppWarning):
        compile_module._check_build_fetch_module_impl("warns_once", _spec(WARNS))
    with warnings.catch_warnings():
        warnings.simplefilter("error", CppWarning)
        compile_module._check_build_fetch_module_impl("warns_once", _spec(WARNS))


@pytest.mark.usefixtures("ext_root")
def test_clean_build_issues_no_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", CppWarning)
        compile_module._check_build_fetch_module_impl("clean", _spec(CLEAN))


def test_filter_on_message_escalates(ext_root: Path) -> None:
    # the same filter as PYTHONWARNINGS="error:compiler warning", which can't name the category
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="compiler warning")
        with pytest.raises(CppWarning):
            compile_module._check_build_fetch_module_impl("escalated", _spec(WARNS))
    # the build itself succeeded and was recorded, so it isn't redone
    assert compile_module._is_current(ext_root / "escalated_ext", "escalated", _spec(WARNS).make_source("escalated")[1])


def _diagnostic(file: str, level: str = "warning") -> CppDiagnostic:
    return CppDiagnostic(level=level, file=file, line=1, column=1, code=None, message="m", rendered=f"{file}:1:1: m")


def test_only_user_code_warns(tmp_path: Path) -> None:
    module_dir = tmp_path / "ext" / "m_ext"
    diagnostics = [
        _diagnostic("module.cpp"),
        _diagnostic(str(module_dir / "module.cpp")),  # MSVC reports full paths
        _diagnostic("../../inc/mine.h"),  # in the user's include path
        _diagnostic("/usr/include/c++/15/bits/std_function.h"),
        _diagnostic("/usr/include/python3.14/pyconfig.h"),
        _diagnostic("module.cpp", level="error"),
    ]
    kept = compile_module._user_warnings(diagnostics, module_dir, ["../../inc"])
    assert [d.file for d in kept] == ["module.cpp", str(module_dir / "module.cpp"), "../../inc/mine.h"]


def test_duplicate_warnings_are_issued_once(tmp_path: Path) -> None:
    # e.g. a universal2 build compiles for each architecture, reporting each warning twice
    module_dir = tmp_path / "m_ext"
    first, other = _diagnostic("module.cpp"), _diagnostic("other.h")
    assert compile_module._user_warnings([first, other, _diagnostic("module.cpp")], module_dir, []) == [first, other]
