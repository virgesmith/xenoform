# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

`xenoform` lets you write type-annotated Python function/method *signatures* and supply the **C++**
implementation in the docstring. The `@xenoform.compile()` decorator generates a [pybind11](https://pybind11.readthedocs.io/)
extension module from those signatures, compiles it on first use (or after a change), and transparently
redirects the Python callable to the compiled C++ implementation.

```py
import xenoform

@xenoform.compile(vectorise=True)
def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i > j ? i : j;"
```

Key behaviours:

- **Deferred compilation** — registration happens at decoration time; the module is generated, built and
  imported lazily on first call (and cached).
- **Change detection** — each generated module embeds a SHA-256 checksum of its source/config. On import the
  checksum is compared (in a subprocess, to avoid polluting `sys.modules`) and the module is rebuilt only if
  it has changed.
- **Type translation** — Python type annotations are recursively mapped to C++ types, and the required headers
  are `#include`d automatically.

## Repository layout

```
src/xenoform/             # the package
  __init__.py             # public API: compile, ReturnValuePolicy, errors, Platform, platform_specific
  compile.py              # @compile decorator factory; deferred build/import/redirect machinery
  cppmodule.py            # FunctionSpec / ModuleSpec dataclasses, source templates, ReturnValuePolicy
  extension_types.py      # Python -> C++ type mapping, header requirements, type-tree translation
  utils.py                # signature translation, header grouping, clang-format, free-threading detection
  config.py               # pydantic-settings config (XENOFORM_* env vars)
  errors.py               # AnnotationError, CompilationError, CppTypeError
  logger.py               # lightweight stdout logger (verbose mode)
src/test/                 # pytest suite (one test_*.py per feature area)
  conftest.py             # build_libs fixture (compiles static/shared libs for external-linking tests)
  test_lib.{h,cpp}        # C++ sources for external-source/static/shared linking tests
  xenoform-test-ext/      # a prebuilt pybind11 extension (uv workspace member) for cross-module tests
examples/                 # loop.py, distance_matrix.py (performance demos; need the `examples` extra)
```

Generated artifacts (binaries, `module.cpp`, `build.log`) are written to an `ext/` subdirectory by default and
are git-ignored. The location is configurable via `XENOFORM_EXTMODULE_ROOT`.

## How it fits together

1. `compile.compile()` returns `register_function`, which:
   - validates that every parameter and the return value are annotated (`_check_annotations`);
   - translates the signature to C++ via `utils.translate_function_signature` (which uses
     `extension_types.translate_type`), collecting required headers;
   - builds a `FunctionSpec` and registers it on the module's `ModuleSpec` in `_module_registry`;
   - wraps the original function so the first call triggers `_get_function` → `_get_module` →
     `_check_build_fetch_module_impl`.
2. `cppmodule.ModuleSpec.make_source()` renders `module.cpp` from the templates, runs it through `clang-format`,
   and returns the code plus its checksum.
3. `_check_build_fetch_module_impl` builds the extension with `Pybind11Extension` + `build_ext`, then imports it.

## Type mapping (`extension_types.py`)

Defaults (override per-arg with `typing.Annotated[T, "cpp_type"]`):

| Python | C++ |
|--------|-----|
| `None` | `void` |
| `int` | `int` |
| `np.int32` / `np.int64` | `int32_t` / `int64_t` |
| `bool` | `bool` |
| `float`, `np.float64` | `double` |
| `np.float32` | `float` |
| `complex`, `np.complex128` | `std::complex<double>` |
| `np.complex64` | `std::complex<float>` |
| `str` | `std::string` |
| `bytes` / `bytearray` | `py::bytes` / `py::bytearray` |
| `np.ndarray` | `py::array_t` |
| `list` | `std::vector` |
| `set` / `frozenset` | `std::unordered_set` / `const std::unordered_set` |
| `dict` | `std::unordered_map` |
| `tuple` | `std::tuple` |
| `slice` | `py::slice` |
| `Any` / `Self` | `py::object` |
| `type` | `py::type` |
| `T \| None` | `std::optional<T>` |
| `T \| U` | `std::variant<T, U>` |
| `Callable` | `std::function` |
| `...` (`EllipsisType`) | `py::ellipsis` |
| `*args` / `**kwargs` | `py::args` / `const py::kwargs&` |

When you add or change a mapping, also update `HEADER_REQUIREMENTS` (so the right pybind11/STL header is pulled
in), the table in `README.md`, and the type tests under `src/test/`.

## Configuration (env vars, `XENOFORM_` prefix)

- `XENOFORM_EXTMODULE_ROOT` — where generated modules live (default `./ext`). Avoid path characters (space,
  hyphen) that are invalid in a Python module name.
- `XENOFORM_DISABLE_FT` — if set, build with the GIL even on a free-threaded interpreter.
- `XENOFORM_CPP_FORMAT` — clang-format style (default `file`, i.e. honour a `.clang-format` in the project root).

## Development workflow

This project uses [`uv`](https://docs.astral.sh/uv/). A C++20-capable compiler and `clang-format` are required
(`clang-format` ships as a dependency; the compiler does not).

```sh
uv sync --dev --all-extras   # install everything (dev group + examples extra + workspace members)
uv run ruff check            # lint
uv run ruff format           # format Python
uv run ty check              # type-check
uv run pytest -sv            # run the test suite
```

- Pre-commit hooks (`uv-lock`, `ruff-check --fix`, `ruff-format`) are configured in `.pre-commit-config.yaml`;
  run `uv run pre-commit install` once, or `uv run pre-commit run --all-files` on demand.
- `pytest` runs with `--cov=src/xenoform --cov-fail-under=97 --doctest-modules`, so **keep coverage at or above
  97%** and make sure docstring examples still pass.
- Ruff is configured with `line-length = 120` and a broad rule set (see `pyproject.toml`); `D103` is ignored in
  tests.

## Conventions & gotchas

- Decorated stubs have an empty body, so add `# ty: ignore[empty-body]` to silence the type checker, and expect
  to disable some pydocstyle rules where the docstring contains C++.
- Don't hand-edit anything under `ext/` — it is regenerated. To force a rebuild, change the inline code or delete
  the module; note that edits to `#include`-d files do **not** trigger a rebuild.
- Functions with conflicting compiler/linker settings (including a different `cxx_std`) must live in separate
  modules — `ModuleSpec.add_function` raises `ValueError` on a `cxx_std` mismatch.
- Compiled Python lambdas and top-level recursion are unsupported; nested functions are supported but cannot
  capture enclosing scope.
- For methods, annotate the receiver (`self: Self` / `cls: type`); static methods are not handled by
  `get_function_scope`.
- `build.log` capture relies on stdout redirection and won't appear when running under pytest.

## CI

`.github/workflows/lint-test.yml` runs lint (`ruff check`, `ty check`) and `pytest -sv` across the matrix
Python `3.12 / 3.13 / 3.14 / 3.14t` × `ubuntu / windows / macos`. `publish.yml` builds and publishes the wheel
to PyPI on `v*` tags. Keep changes green on all platforms — compiler/header behaviour can differ between them.

## See also

- `README.md` — full feature list, usage, performance benchmarks, and troubleshooting.
- [pybind11 docs](https://pybind11.readthedocs.io/en/stable/).
</content>
</invoke>
