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
