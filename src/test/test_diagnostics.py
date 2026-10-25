import importlib
from pathlib import Path

import pytest

from xenoform import CompilationError, CppDiagnostic
from xenoform.config import XenoformConfig
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.diagnostics import brief, parse_diagnostics

# need to import this way to disambiguate compile the module from compile the decorator
compile_module = importlib.import_module("xenoform.compile")

# Trimmed from real gcc 15 build logs (paths shortened; gcc uses typographic quotes in a UTF-8 locale, ASCII in C)
GCC_UNDECLARED = """\
running build_ext
building 'undeclared' extension
c++ -pthread -O3 -Wall -fPIC -I/include -c module.cpp -o build/temp/module.o -std=c++20
module.cpp: In lambda function:
module.cpp:23:9: error: 'ARSE' was not declared in this scope
   23 |         ARSE return current_value * rate;
      |         ^~~~
module.cpp:22:16: warning: unused variable 'x' [-Wunused-variable]
   22 |         double x = 1.0;
      |                ^
error: Command '['c++', '-pthread', '-c', 'module.cpp']' failed with exit code 1
"""

GCC_TEMPLATE = """\
In file included from /include/python3.14/Python.h:14,
                 from /include/pybind11/pybind11.h:12,
                 from module.cpp:10:
/include/python3.14/pyconfig.h:2031:9: warning: '_POSIX_C_SOURCE' redefined
 2031 | #define _POSIX_C_SOURCE 200809L
      |         ^~~~~~~~~~~~~~~
In file included from /usr/include/c++/15/algorithm:62,
                 from module.cpp:9:
/usr/include/features.h:319:10: note: this is the location of the previous definition
  319 | # define _POSIX_C_SOURCE        202405L
      |          ^~~~~~~~~~~~~~~
In file included from /usr/include/c++/15/bits/stl_algobase.h:71:
/usr/include/c++/15/bits/predefined_ops.h: In instantiation of 'constexpr bool _Iter_comp_iter<_Compare>::operator()':
/usr/include/c++/15/bits/stl_algo.h:1778:14:   required from 'constexpr void std::__insertion_sort()'
 1778 |           if (__comp(__i, __first))
      |               ~~~~~~^~~~~~~~~~~~~~
/usr/include/c++/15/bits/stl_algo.h:4874:18:   required from 'constexpr void std::sort()'
 4874 |       std::__sort(__first, __last, __gnu_cxx::__ops::__iter_comp_iter(__comp));
      |       ~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
module.cpp:25:18:   required from here
   25 |         std::sort(v.begin(), v.end(), 42);
      |         ~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~
/usr/include/c++/15/bits/predefined_ops.h:158:30: error: expression cannot be used as a function
  158 |         { return bool(_M_comp(*__it1, *__it2)); }
      |                       ~~~~~~~^~~~~~~~~~~~~~~~
error: Command '['c++', '-c', 'module.cpp']' failed with exit code 1
"""

GCC_FATAL = """\
module.cpp:9:10: fatal error: no_such_header.h: No such file or directory
    9 | #include "no_such_header.h"
      |          ^~~~~~~~~~~~~~~~~~
compilation terminated.
error: Command '['c++', '-c', 'module.cpp']' failed with exit code 1
"""

# Not captured: written from clang's documented output format, as no clang is available locally. The integration test
# below runs against the real compiler on each CI platform (clang on macOS)
CLANG = """\
module.cpp:23:9: error: use of undeclared identifier 'ARSE'
   23 |         ARSE
      |         ^
In file included from module.cpp:9:
In file included from /usr/include/c++/v1/algorithm:1:
/usr/include/c++/v1/__algorithm/sort.h:10:5: error: called object type 'int' is not a function or function pointer
   10 |     __comp(*__i, *__j);
      |     ^~~~~~
/usr/include/c++/v1/__algorithm/sort.h:20:3: note: in instantiation of function template specialization 'std::__sort<int>' requested here
   20 |   __sort(__first, __last, __comp);
      |   ^
module.cpp:25:9: note: in instantiation of function template specialization 'std::sort<int>' requested here
   25 |         std::sort(v.begin(), v.end(), 42);
      |              ^
2 errors generated.
error: command '/usr/bin/clang++' failed with exit code 1
"""

# Not captured: written from MSVC's documented output format (one line per diagnostic, notes after the error)
MSVC = r"""module.cpp
C:\work\ext\m_ext\module.cpp(23,9): error C2065: 'ARSE': undeclared identifier
C:\Program Files\MSVC\include\algorithm(7380): error C2064: term does not evaluate to a function taking 2 arguments
C:\Program Files\MSVC\include\algorithm(7380): note: see reference to function template instantiation 'void std::sort<int>(int)' being compiled
C:\work\ext\m_ext\module.cpp(25): note: see reference to function template instantiation 'void std::sort<int>(int)' being compiled
C:\work\ext\m_ext\module.cpp(22): warning C4189: 'x': local variable is initialized but not referenced
error: command 'C:\\Program Files\\MSVC\\bin\\cl.exe' failed with exit code 2
"""


def _summary(diagnostics: list[CppDiagnostic]) -> list[tuple[str, str, int, int | None]]:
    return [(d.level, d.file.replace("\\", "/").rsplit("/", 1)[-1], d.line, d.column) for d in diagnostics]


def test_gcc() -> None:
    diagnostics = parse_diagnostics(GCC_UNDECLARED)
    assert _summary(diagnostics) == [("error", "module.cpp", 23, 9), ("warning", "module.cpp", 22, 16)]
    error, warning = diagnostics
    assert error.is_error
    assert not warning.is_error
    assert error.message == "'ARSE' was not declared in this scope"
    assert error.code is None
    # the group: its context, its own line and its snippet, but not the next diagnostic or setuptools' summary
    assert error.rendered.splitlines() == [
        "module.cpp: In lambda function:",
        "module.cpp:23:9: error: 'ARSE' was not declared in this scope",
        "   23 |         ARSE return current_value * rate;",
        "      |         ^~~~",
    ]
    assert warning.rendered.splitlines()[-1] == "      |                ^"
    # the context points at the generated source, so it's kept
    assert brief(error) == error.rendered


def test_gcc_notes_and_their_context_stay_with_their_diagnostic() -> None:
    warning, error = parse_diagnostics(GCC_TEMPLATE)
    assert _summary([warning, error]) == [("warning", "pyconfig.h", 2031, 9), ("error", "predefined_ops.h", 158, 30)]
    # the include chain before the note qualifies the note, not the error that follows
    assert warning.rendered.splitlines()[-3].endswith("note: this is the location of the previous definition")
    assert error.rendered.startswith("In file included from /usr/include/c++/15/bits/stl_algobase.h:71:")


def test_brief_keeps_only_the_user_code_from_a_template_chain() -> None:
    error = parse_diagnostics(GCC_TEMPLATE)[1]
    assert brief(error).splitlines() == [
        "module.cpp:25:18:   required from here",
        "   25 |         std::sort(v.begin(), v.end(), 42);",
        "      |         ~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~",
        "/usr/include/c++/15/bits/predefined_ops.h:158:30: error: expression cannot be used as a function",
        "  158 |         { return bool(_M_comp(*__it1, *__it2)); }",
        "      |                       ~~~~~~~^~~~~~~~~~~~~~~~",
    ]


def test_gcc_fatal_error() -> None:
    (error,) = parse_diagnostics(GCC_FATAL)
    assert error.level == "fatal error"
    assert error.is_error
    assert "compilation terminated." not in error.rendered


def test_clang() -> None:
    diagnostics = parse_diagnostics(CLANG)
    assert _summary(diagnostics) == [("error", "module.cpp", 23, 9), ("error", "sort.h", 10, 5)]
    # clang's instantiation chain is notes after the error, which are all kept
    brief_lines = brief(diagnostics[1]).splitlines()
    assert brief_lines[0].startswith("/usr/include/c++/v1/__algorithm/sort.h:10:5: error:")
    assert brief_lines[-3].startswith("module.cpp:25:9: note: in instantiation")
    assert "2 errors generated." not in diagnostics[1].rendered


def test_msvc() -> None:
    diagnostics = parse_diagnostics(MSVC)
    assert _summary(diagnostics) == [
        ("error", "module.cpp", 23, 9),
        ("error", "algorithm", 7380, None),
        ("warning", "module.cpp", 22, None),
    ]
    assert [d.code for d in diagnostics] == ["C2065", "C2064", "C4189"]
    assert diagnostics[0].message == "'ARSE': undeclared identifier"
    # both notes belong to the error before them
    assert len(diagnostics[1].rendered.splitlines()) == 3


def test_colour_codes_are_ignored() -> None:
    coloured = "\x1b[01m\x1b[Kmodule.cpp:23:9:\x1b[m\x1b[K \x1b[01;31m\x1b[Kerror: \x1b[m\x1b[K'ARSE' was not declared"
    (error,) = parse_diagnostics(coloured)
    assert (error.file, error.line, error.level) == ("module.cpp", 23, "error")


def test_no_diagnostics() -> None:
    # e.g. a linker failure
    assert parse_diagnostics("/usr/bin/ld: cannot find -lnope\ncollect2: error: ld returned 1 exit status\n") == []


def test_brief_is_capped() -> None:
    notes = "".join(f"module.cpp:{i}:1: note: candidate {i}\n" for i in range(40))
    (error,) = parse_diagnostics("module.cpp:1:1: error: no matching function\n" + notes)
    lines = brief(error).splitlines()
    assert len(lines) == 31
    assert lines[-1] == "... (11 more lines)"


def test_failure_message() -> None:
    message = compile_module._failure_message(
        "m_ext.m", Path("ext/m_ext"), GCC_TEMPLATE, parse_diagnostics(GCC_TEMPLATE)
    )
    assert message.startswith(f"building m_ext.m failed (line numbers refer to {Path('ext/m_ext/module.cpp')}):\n")
    assert message.endswith(f"(1 warning, full log: {Path('ext/m_ext/build.log')})")
    # the brief form: the include chain and the rest of the instantiation chain are dropped
    assert "In file included from" not in message
    assert "required from here" in message

    # one more error and warning: singular and plural
    log = GCC_UNDECLARED + "module.cpp:30:1: error: two\nmodule.cpp:31:1: warning: w\n"
    message = compile_module._failure_message("m_ext.m", Path("ext/m_ext"), log, parse_diagnostics(log))
    assert message.endswith(f"(1 more error, 2 warnings, full log: {Path('ext/m_ext/build.log')})")


def test_failure_message_falls_back_to_the_log() -> None:
    log = "".join(f"line {i}\n" for i in range(40)) + "collect2: error: ld returned 1 exit status\n"
    message = compile_module._failure_message("m_ext.m", Path("ext/m_ext"), log, parse_diagnostics(log))
    assert message.startswith(f"building m_ext.m failed, see {Path('ext/m_ext/build.log')}:\n")
    assert "line 10" not in message
    assert message.endswith("collect2: error: ld returned 1 exit status")


def test_compilation_error_from_the_real_compiler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # runs on every CI platform, so against gcc, clang and MSVC
    monkeypatch.setattr(compile_module, "get_config", lambda: XenoformConfig(extmodule_root=tmp_path))
    spec = ModuleSpec().add_function(
        FunctionSpec(
            name="undeclared",
            body="[]() { return xenoform_undeclared_name; }",
            arg_annotations="",
            scope=(),
            return_value_policy=ReturnValuePolicy.Automatic,
        )
    )
    with pytest.raises(CompilationError) as e:
        compile_module._check_build_fetch_module_impl("diagnostics_real", spec)

    assert "xenoform_undeclared_name" in str(e.value)
    assert "line numbers refer to" in str(e.value)
    first = next(d for d in e.value.diagnostics if d.is_error)
    assert first.file.replace("\\", "/").endswith("module.cpp")
    assert "xenoform_undeclared_name" in first.message
