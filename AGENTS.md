# Agent Guidelines for `xenoform`

This file instructs AI agents acting as developer, reviewer, and QA for this repository.

This project is the C++ sibling of [`xenoform-rs`](https://github.com/virgesmith/xenoform-rs)
and the two are deliberately kept in lock-step **where appropriate**. The policy sections here
(collaboration, journal, design reviews, workflow) mirror that repo and should not drift; the
technical sections do not — pybind11/setuptools and pyo3/cargo differ enough that a change in one
is not automatically a change in the other. When porting work across, say explicitly why it does
or does not apply.

## Collaboration & Ownership

The maintainer must retain **ownership** of this codebase — meaning they understand
every change well enough to explain, defend, and modify it without the agent. The
agent's speed serves that understanding; it does not replace it. Follow these rules
of engagement:

1. **Plan before code, and wait for approval.** For any non-trivial change, present
   a plan first — approach, files touched, trade-offs — and do not write code until
   the maintainer has understood and signed off. If a decision in the plan can't be
   evaluated yet, stop and explain it.
2. **Small, reviewable diffs — never a big-bang drop.** Break large work into
   increments that can be read in one sitting and reviewed one at a time.
3. **Leave the load-bearing parts to the maintainer when asked.** Offer to hand off
   the core algorithm or tricky module rather than always doing everything; default
   to boilerplate, tests, plumbing, and review.
4. **Explain-it-back gate.** Before proposing a merge, make sure the maintainer can
   explain *why* the change works and what the alternatives were. Offer a
   walk-through; act as tutor, not just producer.
5. **Justify trade-offs, not just conclusions.** State *why* this data structure,
   error type, or approach — and why not the obvious alternative. The reasoning is
   the transferable knowledge.
6. **Prefer idioms the maintainer can learn from**, especially in C++. Flag new or
   unusual patterns and point to where to read more, rather than using them silently.
7. **Tests are the readable spec.** Keep them clear enough that reading the tests
   conveys the contract even when the implementation is dense.

## Task & Design Summaries

**Every task/PR must be recorded** as a new entry at the top of [JOURNAL.md](JOURNAL.md).
Each entry records:

- **Why** — the motivation for the change and the problem it solves.
- **What** — a short description of the change at a high level.
- **Design decisions** — the choices made, the alternatives considered, and why each
  was accepted or rejected. Capture any non-obvious trade-offs or constraints here
  rather than only in code comments.
- **Follow-ups** — anything deferred, and known limitations.

Write the entry as part of the change, not after the fact — the journal is the durable
record of intent that keeps the maintainer in control of the codebase's direction.

## Design Reviews

Decisions in this repo are made under the constraints of the moment — including what LLMs and
agent tooling could do at the time. Those capabilities evolve fast, so a decision that was right
six months ago may be a needless constraint today. **Periodically step back and review the overall
design, not just the next diff.**

- **Cadence.** Hold a design review roughly every 10 merged PRs or every few months, whichever
  comes first — or whenever a change feels like it's fighting the architecture. Either the
  maintainer or the agent may call one.
- **Input.** The design-decision entries in [JOURNAL.md](JOURNAL.md) are the agenda: walk the
  recorded decisions and their rejected alternatives and ask whether the reasoning still holds.
- **Questions to ask.** Have the original constraints (library capabilities, compiler/toolchain
  support, model/agent limitations) shifted? Are there recurring follow-ups or workarounds that
  point at a structural problem? Would a rejected alternative now be the better choice? Is
  complexity earning its keep?
- **Output.** Record the review as a JOURNAL.md entry of its own: what was reconsidered, what was
  reaffirmed (and why), and what should change. Reaffirmations matter as much as changes — they
  stop the same ground being re-litigated every review. Concrete changes become planned tasks via
  the normal [workflow](#workflow); never fold a redesign into an unrelated PR.

## Project Overview

`xenoform` lets you write type-annotated Python function/method *signatures* and supply the **C++**
implementation in the docstring. The `@xenoform.compile()` decorator generates a
[pybind11](https://pybind11.readthedocs.io/) extension module from those signatures, compiles it on
first use (or after a change), and transparently redirects the Python callable to the compiled C++
implementation.

```py
import xenoform

@xenoform.compile(vectorise=True)
def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i > j ? i : j;"
```

Key behaviours:

- **Deferred compilation** — registration happens at decoration time; the module is generated, built
  and imported lazily on first call (and cached). Keep this in mind: an error in code generation
  surfaces at call time, a long way from the decorator.
- **Change detection** — each generated module embeds a SHA-256 checksum of its source/config. On
  import the checksum is compared (in a subprocess, to avoid polluting `sys.modules`) and the module
  is rebuilt only if it has changed.
- **Type translation** — Python type annotations are recursively mapped to C++ types, and the
  required headers are `#include`d automatically.

The library source lives in [src/xenoform/](src/xenoform/):

| File | Role |
|------|------|
| [compile.py](src/xenoform/compile.py) | `@compile` decorator factory; deferred build/import/redirect machinery |
| [cppmodule.py](src/xenoform/cppmodule.py) | `FunctionSpec`/`ModuleSpec`, source templates, `ReturnValuePolicy`, checksum |
| [extension_types.py](src/xenoform/extension_types.py) | Python → C++ type mapping, header requirements, type-tree translation |
| [utils.py](src/xenoform/utils.py) | Signature translation, header grouping, `clang-format`, free-threading detection |
| [config.py](src/xenoform/config.py) | `pydantic-settings` config (`XENOFORM_*` env vars) |
| [errors.py](src/xenoform/errors.py) | `AnnotationError`, `CompilationError`, `CppTypeError` |
| [logger.py](src/xenoform/logger.py) | Lightweight stdout logger (stdlib `logging` breaks under `redirect_stdout`) |
| [__init__.py](src/xenoform/__init__.py) | Public API: `compile`, `ReturnValuePolicy`, errors, `Platform`, `platform_specific` |

Tests are in [src/test/](src/test/). Examples are in [examples/](examples/).

## How It Fits Together

1. `compile.compile()` returns `register_function`, which:
   - validates that every parameter and the return value are annotated (`_check_annotations`);
   - translates the signature to C++ via `utils.translate_function_signature` (which uses
     `extension_types.translate_type`), collecting required headers;
   - builds a `FunctionSpec` and registers it on the module's `ModuleSpec` in `_module_registry`;
   - wraps the original function so the first call triggers `_get_function` → `_get_module` →
     `_check_build_fetch_module_impl`.
2. `cppmodule.ModuleSpec.make_source()` renders `module.cpp` from the templates, runs it through
   `clang-format`, and returns the code plus its checksum.
3. `_check_build_fetch_module_impl` builds the extension with `Pybind11Extension` + `build_ext`,
   then imports it.

Generated artifacts (binaries, `module.cpp`, `build.log`) are written to an `ext/` subdirectory by
default and are git-ignored. The location is configurable via `XENOFORM_EXTMODULE_ROOT`.

## Type Mapping (`extension_types.py`)

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

When you add or change a mapping, also update `HEADER_REQUIREMENTS` (so the right pybind11/STL header
is pulled in), the table in [README.md](README.md), and the type tests under [src/test/](src/test/).
This table is duplicated in the README by design (that one is for users, this one for agents) — they
must be changed together.

## Configuration (env vars, `XENOFORM_` prefix)

- `XENOFORM_EXTMODULE_ROOT` — where generated modules live (default `./ext`). Avoid path characters
  (space, hyphen) that are invalid in a Python module name.
- `XENOFORM_DISABLE_FT` — if set, build with the GIL even on a free-threaded interpreter.
- `XENOFORM_CPP_FORMAT` — clang-format style (default `file`, i.e. honour a `.clang-format` in the
  project root).

## Toolchain

| Tool | Command |
|------|---------|
| Package manager | `uv` |
| Linter / formatter | `ruff` (`uv run ruff check`, `uv run ruff format`) |
| Type checker | `ty` (`uv run ty check`) |
| Tests | `uv run pytest -sv` |
| Install dev deps | `uv sync --dev --all-extras` |

**A C++20-capable compiler is required** and does not ship with the project (`clang-format` does,
as a dependency). Tests compile real C++ at runtime. The `build_libs` fixture in
[src/test/conftest.py](src/test/conftest.py) additionally shells out to `g++` and `ar` to build a
static and a shared library for the external-linkage tests.

Pre-commit hooks (`uv-lock`, `ruff-check --fix`, `ruff-format`) are configured in
[.pre-commit-config.yaml](.pre-commit-config.yaml); run `uv run pre-commit install` once, or
`uv run pre-commit run --all-files` on demand.

**The `examples` extra must be installed for `ty` to pass.** `ty` type-checks the whole project,
including [examples/](examples/), which imports `pandas` (declared in the `examples` optional
extra). Without it, `ty` reports `unresolved-import` and treats the necessary `# ty: ignore`
directives as unused. Install it with `uv sync --dev --all-extras`.

## Quality Gates

All of the following must pass before any change is considered complete:

```sh
uv run ruff check          # zero lint errors
uv run ruff format --check # zero formatting issues
uv run ty check            # zero type errors (whole project, incl. examples/)
uv run pytest -sv          # all tests pass, coverage >= threshold
uv run examples/loop.py           # examples still work
uv run examples/distance_matrix.py
```

`pytest` runs with `--cov=src/xenoform --cov-fail-under=97 --doctest-modules`, so **keep coverage at
or above 97%** and make sure docstring examples still pass. Tests compile and execute real C++, so
they are inherently integration-level — every code path should be exercised.

## Developer Rules

- **Runtime dependencies are intentional.** `pybind11`, `numpy`, `setuptools`, `clang-format`,
  `itrx`, and `pydantic-settings` are runtime deps. New runtime deps need a strong justification;
  dev-only tools go in `[dependency-groups.dev]` in [pyproject.toml](pyproject.toml).
- **Type translation is the critical path.** Changes to
  [extension_types.py](src/xenoform/extension_types.py) affect every user and must be accompanied
  by tests covering the affected type mappings.
- **Generated C++ must compile.** When modifying code generation in
  [cppmodule.py](src/xenoform/cppmodule.py) or signature translation in
  [utils.py](src/xenoform/utils.py), verify the output is valid C++ — run the full test suite,
  which will catch this. A translation that merely *looks* right in the Python string is not
  evidence; the compiler is.
- **Headers must follow the type.** Any new type mapping that needs an include must be registered
  in `HEADER_REQUIREMENTS`, or user code will fail to compile with a confusing error. Note
  `group_headers` orders them deliberately — `pybind11/pybind11.h` must come last.
- **The `Annotated` override mechanism is the escape hatch.** Do not special-case types in the core
  translation logic when an `Annotated[T, "cpp_type"]` override can solve the problem instead.
- **Free-threaded support must be preserved.** The library builds GIL-free extension modules
  (`py::mod_gil_not_used()`) when running under free-threaded Python (`3.14t`), unless
  `XENOFORM_DISABLE_FT` is set. Changes affecting the module template or build flags must not
  regress free-threaded behaviour.
- **The checksum is the rebuild trigger.** `ModuleSpec.make_source` hashes the *formatted* generated
  source, and the hash is embedded in the built module as `__checksum__`. Anything that should force
  a rebuild must therefore be visible in the generated source — compiler flags, macros and the
  free-threading flag are emitted into the header comment for exactly this reason. Conversely,
  things that should *not* force a rebuild must be kept out of it: function definitions are sorted
  for this reason, so that ordering alone never triggers one.
- **The Python ABI deliberately does not enter the checksum.** setuptools already names both the
  binary and the build tree by `EXT_SUFFIX` (`mod.cpython-314t-x86_64-linux-gnu.so`,
  `build/temp.linux-x86_64-cpython-314t/`), and `_get_module_checksum` reads `__checksum__` back
  through a `sys.executable` subprocess, which can only ever import the ABI-matching binary. This
  repo is ABI-partitioned by construction. `xenoform-rs` had to build that partitioning by hand
  (`CARGO_TARGET_DIR`) and its #19/#20 are **not** to be ported here.
- **Type annotations required.** All function signatures need full annotations. `ty` will catch
  missing or incorrect ones.
- **Line length is 120** (configured in [pyproject.toml](pyproject.toml) under `[tool.ruff]`).
- **No comments explaining what the code does.** Only add a comment when the *why* is non-obvious
  (hidden constraint, workaround, subtle invariant).

## Conventions & Gotchas

- Decorated stubs have an empty body, so add `# ty: ignore[empty-body]` to silence the type checker,
  and expect to disable some pydocstyle rules where the docstring contains C++.
- Don't hand-edit anything under `ext/` — it is regenerated. To force a rebuild, change the inline
  code or delete the module; note that edits to `#include`-d files do **not** trigger a rebuild.
- Functions with conflicting compiler/linker settings (including a different `cxx_std`) must live in
  separate modules — `ModuleSpec.add_function` raises `ValueError` on a `cxx_std` mismatch.
- Compiled Python lambdas and top-level recursion are unsupported; nested functions are supported but
  cannot capture enclosing scope.
- For methods, annotate the receiver (`self: Self` / `cls: type`); static methods are not handled by
  `get_function_scope`.
- `build.log` capture relies on stdout redirection and **won't appear when running under pytest** —
  don't rely on it when diagnosing a failing test; reproduce outside pytest.

## Reviewer Checklist

When reviewing a PR or diff, check:

1. **Correctness** — does the type translation produce valid C++? Edge cases: nested generics,
   `Optional`/unions (`std::optional` vs `std::variant`), `Annotated` overrides, `*args`/`**kwargs`,
   callable types, numpy arrays, default argument values.
2. **C++ output validity** — mentally trace the generated `module.cpp` for any new type mapping; the
   test suite will catch compilation failures but reasoning first saves time.
3. **Headers** — does every new type mapping have its `HEADER_REQUIREMENTS` entry, and does
   `group_headers` still order them correctly?
4. **Change detection** — does the checksum still change when it should, and *not* change when only
   irrelevant things differ?
5. **Free-threaded correctness** — anything touching the module template or build must work
   under `3.14t`.
6. **Test coverage** — each new type, decorator parameter, or error path needs a test in
   [src/test/](src/test/); coverage must stay at or above the configured threshold.
7. **API consistency** — new `@compile` parameters must follow existing naming conventions and be
   documented in [README.md](README.md).
8. **Types** — return types and generics should be precise. Avoid `Any` unless unavoidable.
9. **Ruff rules** — no rule in the `select` list should be suppressed without justification. Active
   rules: `ARG, B, C, D103, E, F, I, N, PERF, PTH, RET, RUF, SIM, UP, W` (E501 ignored; D103 also
   ignored in test files).
10. **README / examples** — if the public API or type table changes, update [README.md](README.md)
    and verify the examples still run.

## QA Rules

- Run the full gate suite (`ruff check`, `ruff format --check`, `ty check`, `pytest`, both examples)
  before declaring any task done.
- CI runs the matrix: Python 3.12, 3.13, 3.14, 3.14t × ubuntu, macos, windows. Flag anything that
  might be platform- or version-specific — especially compiler differences (gcc/clang/MSVC),
  path handling (`PTH` rules), platform-specific compile/link flags (`platform_specific`), and
  free-threaded behaviour. Compiler and header behaviour genuinely differ between platforms.
- The free-threaded build (`3.14t`) is in the CI matrix. Do not assume it behaves identically to
  the standard build.
- If a test is skipped or marked `xfail`, leave a comment explaining why and when it can be removed.

## Repository Layout

```
src/
  xenoform/               # the package
    __init__.py           # public API: compile, ReturnValuePolicy, errors, Platform, platform_specific
    compile.py            # @compile decorator factory; deferred build/import/redirect machinery
    cppmodule.py          # FunctionSpec / ModuleSpec, source templates, ReturnValuePolicy
    extension_types.py    # Python -> C++ type mapping, header requirements, type-tree translation
    utils.py              # signature translation, header grouping, clang-format, free-threading
    config.py             # pydantic-settings config (XENOFORM_* env vars)
    errors.py             # AnnotationError, CompilationError, CppTypeError
    logger.py             # lightweight stdout logger (verbose mode)
    py.typed              # PEP 561 marker
  test/                   # pytest suite (one test_*.py per feature area)
    conftest.py           # build_libs fixture (compiles static/shared libs for external-linking tests)
    test_lib.{h,cpp}      # C++ sources for external-source/static/shared linking tests
    other_module.py       # auxiliary Python module used by tests
    xenoform-test-ext/    # a prebuilt pybind11 extension (uv workspace member) for cross-module tests
examples/                 # loop.py, distance_matrix.py (performance demos; need the `examples` extra)
.github/workflows/
  lint-test.yml           # CI: lint + type check + test matrix
  publish.yml             # CI: PyPI publish on v* tags
README.md
JOURNAL.md
pyproject.toml
.pre-commit-config.yaml
```

## Branch and Release Policy

- **`main` is branch-protected.** Direct pushes are blocked. All changes must go through a pull
  request.
- **Releases are triggered by a `v*` tag** (e.g. `v0.1.9`). Pushing such a tag runs
  [publish.yml](.github/workflows/publish.yml), which builds a wheel and publishes to PyPI via
  trusted publishing (OIDC — no API token needed). Do not push a `v*` tag unless the release is
  fully ready and the version in [pyproject.toml](pyproject.toml) matches the tag.
- Version bumps go in `pyproject.toml` (`version = "x.y.z"`).

## Workflow

1. Agree the plan with the maintainer before writing code (see
   [Collaboration & Ownership](#collaboration--ownership)).
2. Create a feature branch off `main` — never commit directly to `main`.
3. Make changes under [src/xenoform/](src/xenoform/).
4. Add or update tests in [src/test/](src/test/) — each new type mapping, parameter, or error path
   needs coverage.
5. Add a task/design entry to [JOURNAL.md](JOURNAL.md) (see
   [Task & Design Summaries](#task--design-summaries)).
6. Run the full gate suite locally (including the examples).
7. If the public API or type translation table changed, update [README.md](README.md) — and the
   table above.
8. Commit — pre-commit hooks will auto-fix formatting and re-lock `uv.lock`.
9. Open a PR targeting `main`; CI must pass (all OS × Python version combinations) before merging.
10. To release: bump the version in [pyproject.toml](pyproject.toml), merge to `main`, then push a
    `vX.Y.Z` tag — PyPI publish triggers automatically.

## See also

- [README.md](README.md) — full feature list, usage, performance benchmarks, and troubleshooting.
- [pybind11 docs](https://pybind11.readthedocs.io/en/stable/).
- [`xenoform-rs`](https://github.com/virgesmith/xenoform-rs) — the sibling project; see its
  `JOURNAL.md` for design decisions that may or may not transfer here.
