# Development Journal

A running log of every task/PR: *why* it was done and the *design decisions* made.
Newest entries at the top. This is the durable record of intent that keeps the
maintainer in control of the codebase's direction — see the
[Task & Design Summaries](AGENTS.md#task--design-summaries) policy in `AGENTS.md`.

Entry template:

```markdown
## YYYY-MM-DD — <title> (#PR)

**Why** — the motivation and the problem this solves.

**What** — high-level description of the change.

**Design decisions**
- <decision> — alternatives considered, why this was chosen.

**Follow-ups** — anything deferred, known limitations.
```

---

## 2026-10-24 — Small type-translation fixes: overrides, numpy int widths, non-finite defaults

**Why** — Three small gaps found while comparing with `xenoform-rs` (see `PARITY_PLAN.md`, PR 3):
- **Overrides still translated their type parameters** (rs #38). `CppTypeTree.__init__` recursed into the Python
  type's parameters even when an `Annotated` override replaced the whole type. Any parameter without a default
  mapping raised, e.g. `Annotated[npt.NDArray[np.datetime64], "py::array"]` failed on `np.datetime64`, although the
  override never reads it. A top-level unmapped type (`Annotated[X, "..."]`) was already fine, so nesting changed the
  behaviour of the escape hatch.
- **Missing numpy int widths** (rs 2026-10-12). Only `np.int32`/`np.int64` had mappings. `np.int8`, `np.int16` and
  every unsigned width needed an override.
- **Non-finite defaults gave invalid C++** (rs #31). `_translate_value` rendered floats with `repr()`, so
  `x: float = math.inf` emitted `inf`, which isn't a C++ literal, and the build failed on first call.

**What**
- An overridden `CppTypeTree` has no subtypes, and the `T | None` → `std::optional` rewrite skips overridden types.
  The `subtype.override = None` line in that rewrite only existed to strip an override that can no longer reach it,
  so it's gone.
- `np.int8`/`np.int16` → `int8_t`/`int16_t` and `np.uint8`…`np.uint64` → `uint8_t`…`uint64_t`. README and AGENTS.md
  type tables updated.
- `inf`, `-inf` and `nan` defaults are rendered as `std::numeric_limits<double>::infinity()` (negated for `-inf`) and
  `std::numeric_limits<double>::quiet_NaN()`, and `<limits>` is added to the module's headers when one is used.
- Tests:
  - `test_types.py`: overrides over unmapped type parameters, including a numpy dtype and an optional union; that an
    unmapped parameter without an override still raises; the int widths, bare and as array dtypes.
  - `test_utils.py`: the non-finite values.
  - New `test_int_widths.py`: compiled round-trips that overflow each width by one, so the C++ type is shown to have
    that width and signedness, and that pybind11 rejects out-of-range input.
  - New `test_non_finite_defaults.py`: compiled functions with `±inf`/`nan` defaults on `double`, `float` and
    `std::optional<double>` parameters, and the `<limits>` header.
- The override test was checked against `main`'s `extension_types.py`, where it fails with `CppTypeError`.

**Design decisions**
- *Fix the escape hatch rather than map `np.datetime64`.* A mapping would fix one type, not the cause, and AGENTS.md
  says not to special-case types when an override should work. It's safe because nothing reads an overridden type's
  subtypes: `__repr__` and `headers()` both return early on an override.
- *Non-finite defaults are always `double`*, not the parameter's C++ type as `PARITY_PLAN.md` first proposed. The
  parameter type can be `std::optional<double>` or an arbitrary override, which `std::numeric_limits` can't take, and
  a Python float is a double anyway. It converts implicitly to `float` or `std::optional<double>`, which the compiled
  tests check.
- *`<limits>` is included explicitly* when needed, rather than relying on pybind11 to include it transitively, so the
  header follows the value (AGENTS.md: headers must follow the type).
- *No header requirement for the fixed-width ints*, as for the existing `int32_t`/`int64_t`, which have always relied
  on pybind11 including `<cstdint>` and compile across the CI matrix, MSVC included. A `<cstdint>` entry for every
  width would add an include to almost every module for no benefit.
- *numpy scalar defaults are still unsupported.* `np.float32(math.inf)` isn't a `float` and raises `TypeError` at
  decoration, as before. A C++ `float` parameter with a non-finite default is written `Annotated[float, "float"]`.

**Follow-ups** — none.

---

## 2026-10-24 — `module_name` override for `@compile`

**Why** — A function's module was always the stem of its defining file, with no way to change it. So functions from
several files couldn't share one module, and code in a notebook cell got whatever name ipykernel gives the cell's
temporary file (numeric, e.g. `PyInit_123456`). That happens to work, because C and importlib don't mind, but it's
fragile. `xenoform-rs` has had `module_name=` for a long time.

**What**
- `@compile(module_name: str | None = None)`. If it's not given, the file stem is used as before. Functions with the same
  `module_name` are registered on the same `ModuleSpec`, so they build into one module, wherever they're defined.
- An explicit name must be an ASCII identifier and not a keyword, or `compile()` raises `ValueError`.
- README parameter table and AGENTS.md updated. New `test_module_name.py` (+ `module_name_helper.py`): an override
  builds into the named module and not the file's; two files share a module; invalid names raise.

**Design decisions**
- *Validated when `compile()` is called*, not on first call. A bad name then fails at the decorator line, not deep in
  a build, which matters because compilation is deferred.
- *ASCII only.* `str.isidentifier()` accepts `café`, but CPython looks for a non-ASCII extension module's init function
  as `PyInitU_` plus the punycoded name, and pybind11 only generates `PyInit_<name>`. Such a module would build and
  then fail to import.
- *Only explicit names are validated.* Checking the default stem too would break notebooks and any file whose stem
  isn't an identifier, which work today. That's left for the notebooks investigation (see `PARITY_PLAN.md`).
- *`ValueError`*, as for the existing `cxx_std` mismatch, rather than a new error type.
- *Same semantics as `xenoform-rs`*: a shared name means a shared module, and the existing checks for conflicting
  settings (e.g. `cxx_std`) apply across files.

**Follow-ups**
- Two functions with the same name (and scope) sharing a module give the same C++ name. pybind11 then registers them
  as overloads rather than raising, so each python stub dispatches to both. Checked: with `f(int)` in one file and
  `f(str)` in another, the first file's `f("y")` runs the second's implementation. This was already possible
  within one file. Not handled here. A duplicate-name check in `ModuleSpec.add_function` would catch it.
- The README, AGENTS.md and the docstring say to set `module_name` in notebooks, where the default comes from the
  kernel's temporary file for the cell and isn't deterministic. Fuller notebook guidance (e.g. kernel restarts)
  belongs to the notebooks item.

---

## 2026-10-24 — Checksum file per ABI; load modules by path

**Why** — To decide whether a module was up to date, `_get_module_checksum` started a Python subprocess that imported
the module and printed `__checksum__`. It had to be a subprocess, because a loaded extension can't be unloaded or
reloaded. That had two problems:
- **A bug:** the subprocess imported `{extmodule_root.name}.{ext_name}.{module_name}`, which only resolves when the cwd
  is the parent of the extmodule root, and only when the root's name is a valid module name. With an absolute
  `XENOFORM_EXTMODULE_ROOT` elsewhere, a run from another directory, or a root such as `ext-build`, every new process
  found nothing and rebuilt the module (reproduced: a few seconds per run instead of a load).
- **Cost:** even when it worked, the first call per module per process paid for an interpreter start-up and a
  clang-format run: ~27 ms measured on Linux, more on macOS/Windows.

Ported from `xenoform-rs` #35 (see `PARITY_PLAN.md`, PR 2).

**What**
- After a successful build, the hash is written to a checksum file beside the binary, named after it:
  `ext/foo_ext/foo.cpython-314t-x86_64-linux-gnu.checksum` (`_get_checksum_path`). A module is up to date when its
  binary (`_get_binary_path`, named by `EXT_SUFFIX` as setuptools does) exists and the checksum file holds the current
  hash. `_get_module_checksum` and its subprocess are gone.
- A rebuild deletes the checksum file first and writes it only once the build has succeeded.
- `make_source` hashes the *unformatted* source. clang-format runs only when `module.cpp` is written, so an up-to-date
  check runs no subprocesses at all.
- Modules are loaded by path (`_load_module`, via `importlib.util.spec_from_file_location`) and registered in
  `sys.modules` as `<name>_ext.<name>`, as before. The extmodule root is no longer appended to `sys.path`.
- The module folder is only created when building, so a check has no side effects.
- Measured (Linux, 3.14, warm `ext/`): the first call to a compiled function went from ~27 ms to ~0.5 ms.
- New `test_checksum.py`: a build writes the checksum and formatted source; an up-to-date check runs no subprocess and
  no build; a stale, missing or other-ABI checksum rebuilds, and so does a checksum without its binary; a failed build
  leaves no checksum; an absolute root used from another cwd is reused across processes (the regression).
- README and AGENTS.md describe the checksum files. The caveat against spaces and hyphens in
  `XENOFORM_EXTMODULE_ROOT` is removed: the root's name no longer appears in an import name. Checked on Linux with
  `my build-dir/ext`.

**Design decisions**
- *Keeps the AGENTS.md ABI rule, with a new mechanism.* The ABI still doesn't enter the hash. Before, the subprocess
  used `sys.executable`, so it could only import the matching binary. Now the checksum file is named after the
  binary, so it can only vouch for that binary. A single `.checksum` per module was rejected: 3.14 and 3.14t share the
  module folder and its source, so a switch between them would find a matching hash and load the wrong binary, or
  none.
- *Invalidate, build, then stamp.* If the old checksum survived a failed or interrupted rebuild, it could vouch for a
  binary that wasn't built from the source it names. Deleting it first means a checksum only exists for a completed
  build.
- *No check that the binary exists after `setup()` returns.* If setuptools succeeded without producing it, the next
  check finds no binary and rebuilds. It isn't worth an extra error path.
- *Unformatted hash.* Formatting doesn't change what's built. Hashing formatted code would keep a clang-format
  subprocess in every up-to-date check, and a clang-format upgrade would rebuild every module. The maintainer first
  preferred the formatted hash, as upgrades are rare, then chose this for the subprocess-free check.
- *No fallback to the subprocess check.* Existing `ext/` folders have no checksum files, so each module rebuilds once
  after upgrading. That's cheaper than keeping the slow path, and its tests, around.
- *Load by path rather than keep `sys.path`.* With the root on `sys.path`, every `<name>_ext` folder was importable as a
  namespace package, which could shadow a real package. It also tied the import to the root's location and name. The
  `sys.modules` key stays `<name>_ext.<name>`, so it still can't collide with the user's Python module (the bug
  `xenoform-rs` #30 fixed doesn't arise here). pybind11 finds `PyInit_<name>` from the last part of the name, so the
  generated code is unchanged.
- *An already-loaded module is returned as is,* as `import_module` did, since it can't be reloaded after a rebuild.
- *Rejected: reading the hash from the loaded module.* That needs the module loaded, which is what the subprocess
  avoided. `__checksum__` stays in the module for inspection only.

**Follow-ups**
- Built modules are no longer importable by name (`from foo_ext.foo import _f`), since `ext/` isn't on `sys.path`.
  `test_nested.py` did this and now uses `sys.modules`. The functions were always private (`_`-prefixed), but this is a
  visible change.
- A binary rebuilt outside xenoform keeps the old checksum. Delete the checksum file or the module folder to force a
  rebuild.
- `test_checksum.py`'s rebuild tests are skipped on Windows (a loaded `.pyd` can't be overwritten), as is the rebuild
  step of `test_rebuild_lifecycle`. The up-to-date, build and cross-process tests run everywhere.
- Paths with spaces were only checked on Linux.

---

## 2026-10-24 — Support Python 3.13–3.15; bump CI actions and dev tooling; numpy 2.5 `NDArray`

**Why** — Python 3.15 has been released, and the project supports only the three latest minor versions, so 3.15
comes in and 3.12 goes out. The CI actions and pre-commit tools were behind `xenoform-rs`. Refreshing the lock then
pulled in numpy 2.5, which breaks the default `npt.NDArray[...]` mapping. Ported from `xenoform-rs` #28 and its
0.1.6 release prep (see `PARITY_PLAN.md`, PR 1).

**What**
- `requires-python = ">=3.13"`; classifiers and CI matrix are 3.13, 3.14, 3.14t, 3.15.
- `actions/checkout` v6 → v7, `astral-sh/setup-uv` v7/v8.1.0 → v10.3.0 in both workflows.
- Pre-commit: uv 0.13.5, ruff v0.17.2, ty v0.0.91. The dev dependency floors (`ruff>=0.17.2`, `ty>=0.0.91`) match
  the hooks, so the hook and CI's `uv run ty check` use the same versions. Relocked: numpy 2.4.5 → 2.5.4, pybind11
  3.1.0.
- New `all-checks` CI job: the single required status check.
- `compile.py` uses PEP 695 type parameters throughout. The module-level `P = ParamSpec("P")` / `R = TypeVar("R")`
  are gone.
- Removed the 3.12-only `sys._is_gil_enabled` guard in `build_freethreaded` and its `# pragma: no cover`.
- `npt.NDArray` is a `DEFAULT_TYPE_MAPPING` key alongside `np.ndarray`, with tests for both annotation styles.
- AGENTS.md states the three-version policy and the `all-checks` required check.
- ruff 0.17 formats Python code blocks in Markdown, which changed blank lines in the README and AGENTS.md and
  collapsed one `...` body onto its `def` line.
- New ty diagnostics fixed: `examples/loop.py` iterates with `enumerate(data)` instead of `data.items()`, and the two
  `translate_type(npt.NDArray[...])` calls in `test_types.py` also ignore `invalid-argument-type`.

**Design decisions**
- *Why `NDArray` broke* — numpy 2.5 redefines `NDArray` as a PEP 695 alias (`type NDArray[ScalarT] = ...`).
  `get_origin(NDArray[T])` is then the alias object, not `np.ndarray`, so the `np.ndarray` key no longer matched and
  translation raised `CppTypeError`. Users already on numpy 2.5 were hitting this before the lock moved.
- *Both keys, not `numpy>=2.5`.* Raising the floor drops users, and `np.ndarray` is still needed for numpy < 2.5's
  `NDArray` and for explicit `np.ndarray[shape, dtype[T]]` annotations on every version. The two keys reach
  `py::array_t<T>` by different routes: `np.ndarray[...]` takes the special case that digs `T` out of the dtype,
  and the one-parameter alias `NDArray[T]` takes the generic branch.
- *Not generic PEP 695 alias expansion* (substituting the arguments into the alias's `__value__`). It would also
  support user-defined `type X = ...` aliases, but it touches the core translation path, so it's kept for later.
- *`enumerate(data)` in `loop.py`, not a `# ty: ignore`.* The loop writes into a numpy array by position, so a
  positional index is what the code means. `data.items()` only worked because the example's index is a
  `RangeIndex`. The benchmark loop is otherwise unchanged.
- *A single `all-checks` required check*, as in `xenoform-rs`. A ruleset that lists matrix jobs by name needs editing
  on every version bump, and jobs removed from the matrix block the PR as "expected" checks that never report. The
  job runs with `if: always()`, because GitHub counts a skipped required check as passing.
- *setup-uv is pinned to an exact version.* From v8, setup-uv no longer publishes major/minor tags (a supply-chain
  guard), so `@v10` doesn't exist. checkout still publishes `@v7`. None of the actions' breaking changes apply: the
  workflows trigger only on `push`, `pull_request` and tags, and pass only `python-version` to setup-uv.
- *No 3.15t in CI* — free-threading stays covered by 3.14t, which keeps the matrix size unchanged.
- pybind11 3.1.0 works on 3.15: the full suite passed locally on 3.14 (100% coverage from a clean `ext/`), 3.14t and
  3.15 (Linux).

**Follow-ups**
- **Maintainer action:** change the `main` ruleset to require only `all-checks`. If it currently lists matrix jobs
  by name, any 3.12 jobs among them will never report and will block this PR.
- The numpy < 2.5 path is no longer exercised in CI (only the locked numpy is). A lowest-direct-deps job would cover
  it.
- Generic PEP 695 alias expansion (see above).

---

## 2026-07-18 — Preload compiled functions before benchmarking in examples

**Why** — The README claimed the smallest-array `cpp` timing was dominated by "compiling and
importing the extension module on the first call", producing a misleading `-99%` speedup at the
smallest N. That explanation was wrong: the extension is not (re)compiled on a warm run. The real
first-call cost comes from `_get_function` → `_get_module` → `_check_build_fetch_module_impl`, which
spawns a subprocess to verify the module checksum, imports the module, and diverts the Python stub to
the C++ implementation. That load/check/redirect cost was landing on the first timed `cpp` call.

**What** —
- `examples/loop.py` and `examples/distance_matrix.py` now call the compiled function once (a tiny
  warm-up input) before the timing loop, so the module is built-if-needed, loaded, and redirected
  before the clock starts.
- README prose in both benchmark sections rewritten to describe the real cost accurately; both
  tables refreshed with measured numbers. The smallest N now shows a genuine speedup instead of
  `-99%`. Corrected the Python version reference 3.13 → 3.14.

**Design decisions**
- Warm-up describes the first-call cost as "compile if missing/out of date, otherwise load, check,
  redirect" rather than asserting the extension is already compiled — the warm-up genuinely triggers
  compilation on a cold checkout, and only load/check/redirect on a warm one.
- Do **not** time or report the warm-up. Considered printing a "preload: N ms" line, but the figure
  conflates two very different regimes (fresh compile vs. warm load) and isn't a stable, meaningful
  number, so it would mislead more than inform. The warm-up's only job is to keep the one-off cost
  out of the per-call timings.

**Follow-ups** — The `cpp_time == 0` guard at the smallest N is retained: preloading removes the
first-call cost but coarse-timer platforms can still measure a sub-tick `cpp` time.

## 2026-07-18 — Enforce 100% coverage + examples in CI, tidy pre-commit (#30)

**Why** — Two gaps versus `xenoform-rs`, ported as issues #23 and #24. The `ty` type-check gate was
documented but not enforced by a pre-commit hook (the hook repo didn't exist when the config was
written), the pins lagged, and `.pre-commit-config.yaml` had a duplicated `repos:` key. Separately,
coverage and the examples were only local gates: an example could rot and a coverage regression
could land unnoticed on a branch.

**What** —
- **#23** — Dropped the stray duplicate `repos:`, bumped `uv-pre-commit` → 0.11.28 and
  `ruff-pre-commit` → v0.15.20, and added the `ty` hook (v0.0.56). The hook pins a newer `ty` than
  the dev dependency resolved (0.0.37), so I bumped `ty>=0.0.56` to keep the hook and CI's
  `uv run ty check` on the same version; the newer `ty` no longer needs a `# ty: ignore` directive
  in `extension_types.py`, so that was removed.
- **#24** — CI now enforces coverage on exactly one matrix job (`3.14 / ubuntu-latest`) via
  `--cov-fail-under=100`; the other jobs run `pytest --no-cov`. Every example runs as a CI gate.
  Raised the bar 97 → 100 with new tests for the previously-uncovered paths (build/caching
  lifecycle, an over-annotated type, the verbose logger, the clang-format failure fallback) and two
  `# pragma: no cover` exclusions for genuinely unreachable branches.

**Design decisions**
- *Coverage threshold is enforced in CI only, not in local `addopts`.* A pre-existing `ext/` changes
  which build/caching branches run (a warm build skips the "not found → build" path; a clean build
  skips "up-to-date"/"outdated"), so a local run legitimately reads below 100%. Enforcing locally
  would produce false failures; CI enforces on a clean checkout (`ext/` is gitignored) where the
  number is deterministic. Local runs still report coverage.
- *100% over a documented 97%.* Read the report first (per the issue). Most of the missing 3% was
  real, testable paths, not platform noise — the caching lifecycle test alone recovered several
  branches deterministically by driving `_check_build_fetch_module_impl` directly (it sits behind
  the `@cache` on `_get_module`, so a normal `@compile` call only ever hits one branch per process).
  Only two branches are genuinely unreachable on the coverage job and got pragmas: the 3.12-only
  free-threading `hasattr` guard, and a defensive `get_origin`/`get_args` inconsistency check.
- *Enforce coverage on one job, not twelve.* Matches `xenoform-rs`; the platform-conditional lines
  mean the 100% target is only meaningful on the reference platform anyway.

**Follow-ups**
- Running the examples across the full matrix surfaced two portability gaps (both pre-existing, but
  never exercised in CI before). Fixed in this PR: `distance_matrix.py` hard-coded `-fopenmp`, which
  Apple clang and MSVC reject — it now derives the flag via `platform_specific({"Linux": [...]})`,
  so OpenMP is used on Linux and the `#pragma omp` directives are harmlessly ignored (serial) on
  macOS/Windows.
- The "outdated → rebuild" step of the caching lifecycle test is skipped on Windows, where a loaded
  `.pyd` is locked and cannot be overwritten in-process. The branch is still covered by the
  ubuntu-latest coverage gate.
- The two pragma'd branches are the only intentionally-unmeasured code.

---

## 2026-07-18 — Replace `@compile(verbose=...)` with the `XENOFORM_VERBOSE` env flag (#29)

**Why** — `@compile(verbose=...)` mutated global logger state at *decoration (import) time*.
`get_logger()` is `@cache`d, so there is one `Logger` per process, and `verbose=False` (the default)
actively called `logger.disable()`. The consequence: any plain `@compile()` evaluated *after* an
`@compile(verbose=True)` silenced the logging the first function had asked for — last decorator wins,
process-wide, including from third-party code that merely uses xenoform. Closes #22.

**What** — Removed the `verbose` decorator argument entirely and moved verbosity to a single
global setting: `XENOFORM_VERBOSE`. `get_logger()` derives its enabled state from the config; the
now-dead `Logger.enable()`/`disable()` mutators were deleted. README and tests updated; migration is
`@compile(verbose=True)` → set `XENOFORM_VERBOSE` in the environment.

**Design decisions**
- *Removed the flag rather than scoping it per-module or making it enable-only* — the two options
  the issue floated. The maintainer's call: verbosity is a whole-process debugging aid, and a
  per-decorator knob was the entire source of the bug. A global env flag is unaffected by import
  order, which is the property that was actually wanted; everything else about compilation is
  already deferred to first call, so a decoration-time knob was doubly surprising.
- *Presence-based `str | None`, modelled on `XENOFORM_DISABLE_FT`, not a `bool`.* A `bool` field
  makes `XENOFORM_VERBOSE=` (present but empty) raise pydantic `bool_parsing`, so
  `XENOFORM_VERBOSE= uv run python examples/loop.py` would fail. An intermediate version fixed that
  with a `field_validator` coercing empty→`True`; rejected as needless once the field simply mirrors
  `disable_ft` — presence (`verbose is not None`) is the whole semantics, value is irrelevant, and
  the convention already exists in this file.
- *Deleted `Logger.enable()`/`disable()`.* They existed only to serve the decorator's removed
  mutation; the logger's enabled state is now set once at construction from config. Leaving them
  would be dead code and would re-invite exactly the runtime global-toggling this change removes.

**Follow-ups** — none. Verbosity is now process-global by construction; if per-module debug output
is ever wanted it would need the `ModuleSpec`-scoped approach the issue described, but nobody has
asked for it.

## 2026-07-18 — Defer the import-time `sys.path.append` out of module scope (#28)

**Why** — [compile.py](src/xenoform/compile.py) mutated `sys.path` as a side effect of *importing*
`xenoform`: merely importing the library — even to read `__version__` or use `platform_specific` —
appended `extmodule_root` to the host application's `sys.path`, with no duplicate guard, so
re-imports in one process (test suites, reloads) could append the same entry repeatedly. Import
should not have global side effects. Closes #21; ported from `xenoform-rs`#9.

**What** — Moved the `sys.path.append` into `_check_build_fetch_module_impl` (first use) behind an
`if root not in sys.path` guard, and dropped the module-level `extmodule_root` global in favour of
reading `get_config().extmodule_root` at the use sites.

**Design decisions**
- *Moved, not removed — unlike `xenoform-rs`#9.* There the append turned out to be vestigial
  because modules load by explicit path via `ExtensionFileLoader`. Here the build path ends in
  `importlib.import_module(f"{ext_name}.{module_name}")` and `_get_module_checksum` imports by dotted
  name in a subprocess, so `extmodule_root` genuinely has to be importable. The defect (import-time,
  unguarded) is the same; the fix is deferral plus a guard, not deletion.
- *Read `extmodule_root` through `get_config()` at use sites rather than snapshotting a module
  global.* Makes the config the single source of truth, so a change to `XENOFORM_EXTMODULE_ROOT` is
  no longer silently ignored after `import xenoform`. Folds in the smaller item tracked as
  `xenoform-rs`#13; `get_config()` is `@cache`d so this is belt-and-braces, not a hot path.

**Follow-ups** — none.

## 2026-07-17 — Adopt the `xenoform-rs` agent guidelines and journal

**Why** — `xenoform` and [`xenoform-rs`](https://github.com/virgesmith/xenoform-rs) are siblings
solving the same problem for different compiled languages, and are maintained by the same person
with the same concern: the maintainer must retain ownership of the codebase rather than being
outpaced by the agent. `xenoform-rs` grew explicit rules of engagement and a durable per-change
record (its #10, #17). This repo gained an `AGENTS.md` in #19, but a purely technical one — an
orientation doc, with no plan-first gate, no design history, and no stated collaboration policy.

**What** — Merged the `xenoform-rs` policy layer into the existing `AGENTS.md` from #19 and added
this `JOURNAL.md`. Also reviewed the `xenoform-rs` commit history from v0.1.3 onwards and raised
issues here for the parts that transfer (see below).

**Design decisions**
- *Merged with #19's `AGENTS.md` rather than replacing it.* The two documents turned out to be
  complementary rather than competing: #19's is an orientation doc (call-flow walkthrough, type
  table, gotchas), the `xenoform-rs` one is a policy doc (collaboration, journal, reviewer
  checklist, workflow). Replacing #19's would have discarded content that was independently correct
  and, in several cases, recorded nowhere else — that edits to `#include`-d files don't trigger a
  rebuild, that `get_function_scope` doesn't handle static methods, that compiled lambdas and
  top-level recursion are unsupported. All of it is preserved.
- *Kept the type-mapping table despite it duplicating the README's.* It is a real drift risk, and
  the honest alternative was a pointer to the README. Kept because it saves an agent a file read on
  the most frequently changed part of the codebase; the duplication is now called out both in the
  table's preamble and in the workflow step, so the obligation to change both is written down.
- *Fixed a defect in #19's file*: it ended with stray `</content>` and `</invoke>` tags — tool-call
  XML leaked into the file by the agent that authored it. Harmless to a human reader, but this is a
  file whose entire audience is LLMs, and dangling tags there are worse than noise. Folded into the
  merge rather than raised separately, since the merge rewrites the file anyway.
- *Policy sections mirrored verbatim; technical sections written from this codebase.* The
  collaboration, journal, design-review and workflow sections are maintainer policy and should not
  drift between the two repos, so they are kept word-for-word. Everything technical was derived by
  reading this source, not translated from the Rust text: the toolchains genuinely differ
  (pybind11/setuptools vs pyo3/cargo, `clang-format` vs `rustfmt`, deferred-to-first-call vs
  import-hook compilation), and a copied-then-edited technical doc would assert things about this
  repo that were never checked.
- *`AGENTS.md` states the lock-step relationship explicitly, including that it is conditional.* The
  two repos are kept in step "where appropriate"; without saying so, a future agent would be left to
  guess whether an `xenoform-rs` change is a mandate here. The rule is now: port the intent, state
  why it does or does not apply.
- *Single append-only `JOURNAL.md` at the repo root* — same choice as `xenoform-rs`, for the same
  reasons: one file is lower-friction than per-task files under `docs/`, reads top-to-bottom as a
  history, and avoids proliferating small files. Trade-off: it grows over time, but old entries can
  be archived if it gets unwieldy.
- *Added the checksum's two standing rules to the developer rules*, since neither is inferable from
  the code and both are easy to break: anything that *should* force a rebuild must be visible in the
  generated source (hence flags and macros in the header comment), and anything that should *not*
  must be kept out of it (hence sorted function definitions). The ABI rule below is the same
  reasoning applied in reverse.

**Follow-ups** — The `xenoform-rs` items that transfer are raised as issues rather than fixed here:
#20 (non-bool default argument values generate invalid C++ — the only confirmed defect of the six),
#21 (import-time `sys.path.append`), #22 (`@compile(verbose=...)` mutates global logger state),
#23 (`ty` pre-commit hook), #24 (coverage enforcement and examples in CI), #25 (further performance
examples). Also synced `.claude/` into `.gitignore`, per `xenoform-rs`'s v0.1.4.

Two `xenoform-rs` changes deliberately have **no** counterpart here, both from the same saga:
folding the Python ABI into the module checksum (its #19) and then removing it again (its #20).
setuptools already names both the binary and the build tree by `EXT_SUFFIX`
(`test_basic.cpython-314t-x86_64-linux-gnu.so`, `build/temp.linux-x86_64-cpython-314t/`), and
`_get_module_checksum` reads `__checksum__` back through a `sys.executable` subprocess, which can
only ever import the ABI-matching binary. This repo is therefore ABI-partitioned by construction —
which is precisely the conclusion `xenoform-rs` reached the long way round, having had to build the
partitioning by hand with `CARGO_TARGET_DIR` because cargo has no fingerprint input that changes
when only the interpreter behind a stable venv path changes. Nothing to port; worth recording so the
question isn't reopened. The one residual difference is churn, not correctness: `module.cpp` embeds
the `py::mod_gil_not_used()` flag, so it is genuinely ABI-dependent and gets rewritten on every
GIL↔free-threaded switch. Each switch rebuilds — correctly, just not for free. Unlike rs, that
cannot be fixed by making the source ABI-independent, because here the source really does differ.

Separately noted while surveying, outside the scope of this sync: `pyproject.toml` lists a
`[tool.uv.workspace]` member `src/test/extmodule` that does not exist on disk.
