---
name: xenoform
description: >
  Use when writing, editing, or debugging @compile-decorated functions/methods in a Python
  project that uses xenoform — inline C++ in a Python docstring, compiled via pybind11.
  Covers the @compile decorator, Python-to-C++ type translation, Annotated overrides, callable
  types, constants, compiler errors and warnings, and the generated ext/ build artifacts.
  Triggers: "xenoform", "@compile" or "@xenoform.compile", inline C++ in a docstring,
  CompilationError, CppWarning, pybind11 build errors under an `ext/` directory.
---

# Developing with xenoform

xenoform lets you write a type-annotated Python function, decorate it with `@compile`, and put the
C++ *body* of that function in its docstring. Importing the module only registers each decorated
function. On the first call to any of them, xenoform translates the Python signatures to C++,
generates one pybind11 extension module for the Python module under `ext/<module>_ext/`, compiles
it, and redirects the Python functions to the compiled ones — so build errors surface at that first
call, not at import. A hash of the generated source is stored next to the binary, so unchanged
modules aren't rebuilt. Each interpreter ABI (Python version, GIL vs free-threaded) has its own
binary and hash, so switching interpreters rebuilds automatically.

xenoform is for C++ written on the fly during development: prototyping, and quick performance wins in
hot Python code. It is **not** for distributing compiled extensions: modules are compiled on the
machine that runs them, so a C++20 compiler is needed wherever the code runs, and the binaries can't
be shipped in a wheel.

This skill is a quick reference. The canonical docs are the project's own `README.md` — read it
for the full walkthrough and worked examples.

## When `@compile` is worth reaching for

The reason to use it is **performance**, not taste. Reach for `@compile` when profiling (or an
obvious algorithmic shape) points at one of these:

- **A sequential loop that can't be vectorised** — each iteration depends on the previous one
  (e.g. a running balance, a recurrence), so numpy has no vectorised form and plain Python pays its
  interpreter overhead on every step. The README's `loop.py` example is ~40x faster at 10M rows
  purely from this.
- **A numeric kernel where even vectorised numpy loses** — e.g. when numpy has to materialise a
  large temporary, or does redundant work. `distance_matrix.py` is ~30x faster than vectorised
  numpy from N=1000 points: it computes only half of the symmetric matrix, needs no N×N×D
  temporary, and parallelises the outer loop with OpenMP.
- **Parallel work without the GIL** — under a free-threaded interpreter, modules are built without
  the GIL, so compiled code can run on several Python threads at once.

It's usually **not** worth it for code already dominated by a vectorised numpy/pandas call, code
that runs rarely or on small inputs (the one-off compile and the call overhead outweigh the win),
or code that must run where no C++ compiler is available. **To ship compiled code** (a wheel, or an
environment without a compiler), write a regular extension package with pybind11 or nanobind, built
with e.g. scikit-build-core, rather than using `@compile`; the generated `ext/<module>_ext/module.cpp`
is a pybind11 module and a starting point. When in doubt, write the plain-Python version first and
profile.

## Minimal example

```py
import xenoform


@xenoform.compile(vectorise=True)
def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i > j ? i : j;"
```

The docstring is the C++ function *body*: it's placed in a lambda with the translated signature,
`[](int i, int j) -> int { ... }`. Type checkers flag the empty Python body, hence the
`# ty: ignore[empty-body]`. Inline C++ also breaks some pydocstyle rules.

Default argument values (translated to C++ literals), positional-only/keyword-only markers
(`/`, `*`), `*args` (`py::args`) and `**kwargs` (`const py::kwargs&`) are supported.

### Methods

Annotate the receiver: `self: Self` (a `py::object`) for instance methods, `cls: type` (a
`py::type`) for class methods. Put `@staticmethod`/`@classmethod` *above* `@compile`:

```py
class Thing:
    @compile()
    def method(self: Self) -> int:  # ty: ignore[empty-body]
        """
        return self.attr("x").cast<int>();
        """

    @staticmethod
    @compile()
    def static_method(i: int) -> int:  # ty: ignore[empty-body]
        """
        return i + 1000;
        """
```

## `@compile` decorator parameters

| name | type | default | description |
|------|------|---------|-------------|
| `vectorise` | `bool` | `False` | Wrap the function with `py::vectorize`, so a scalar function accepts numpy arrays elementwise (with broadcasting). Slow when called with all-scalar arguments. |
| `define_macros` | `list[str] \| None` | `None` | `-D` definitions, e.g. `["NDEBUG", "N=3"]`. |
| `extra_includes` | `list[str] \| None` | `None` | Extra headers, e.g. `["<algorithm>", '"mine.h"']`. |
| `extra_include_paths` | `list[str] \| None` | `None` | Extra header search paths. Relative paths are relative to the module's `ext/<module>_ext/` folder. |
| `extra_compile_args` | `list[str] \| None` | `None` | Extra compiler arguments. Use `platform_specific({...})` for per-OS flags. |
| `extra_link_args` | `list[str] \| None` | `None` | Extra linker arguments, e.g. to link a prebuilt library. |
| `return_value_policy` | `ReturnValuePolicy` | `Automatic` | pybind11's return value policy. |
| `cxx_std` | `int` | `20` | C++ standard. Must be the same for every function in a module. |
| `help` | `str \| None` | `None` | Docstring for the *Python* function (the real docstring holds C++). |
| `module_name` | `str \| None` | `None` | Extension module to build into, default the defining file's stem. An ASCII identifier. Functions from several files with the same name share a module. Always set it in notebooks. |
| `constants` | `list[str] \| None` | `None` | Python variables to declare as C++ `constexpr` constants, by name; see below. |

Functions in one module must have compatible settings; put conflicting ones in separate modules
(via `module_name` or separate files).

## Default Python → C++ type mapping

| Python | C++ |
|--------|-----|
| `None` | `void` |
| `int` | `int` |
| `np.int8` / `np.int16` / `np.int32` / `np.int64` | `int8_t` / `int16_t` / `int32_t` / `int64_t` |
| `np.uint8` / `np.uint16` / `np.uint32` / `np.uint64` | `uint8_t` / `uint16_t` / `uint32_t` / `uint64_t` |
| `bool` | `bool` |
| `float`, `np.float64` | `double` |
| `np.float32` | `float` |
| `complex`, `np.complex128` | `std::complex<double>` |
| `np.complex64` | `std::complex<float>` |
| `str` | `std::string` |
| `bytes` / `bytearray` | `py::bytes` / `py::bytearray` |
| `np.ndarray` / `npt.NDArray[T]` | `py::array_t<T>` |
| `list` | `std::vector` |
| `set` / `frozenset` | `std::unordered_set` / `const std::unordered_set` |
| `dict` | `std::unordered_map` |
| `tuple` | `std::tuple` |
| `slice` | `py::slice` |
| `Any` / `Self` | `py::object` |
| `type` | `py::type` |
| `T \| None` | `std::optional<T>` |
| `T \| U` | `std::variant<T, U>` |
| `Callable[[A, B], R]` | `std::function<R(A, B)>` |
| `...` (`EllipsisType`) | `py::ellipsis` |
| `*args` / `**kwargs` | `py::args` / `const py::kwargs&` |

Nested generics recurse: `dict[str, list[float]]` → `std::unordered_map<std::string, std::vector<double>>`.
The headers each type needs are included automatically.

Override any mapping with `Annotated`; the override is the whole C++ type, so its type parameters
needn't have a mapping, but you supply any header it needs via `extra_includes`:

```py
@compile()
def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:  # ty: ignore[empty-body]
    ...
```

## Constants

The C++ body can't refer to Python values, so pass them by name:

```py
from math import pi  # noqa: F401 - used only by name below, so a linter would remove it

N_STEPS = 1000
SEED = 2**40


@compile(constants=["N_STEPS", "SEED: uint64_t", "pi"])
def simulate(x: float) -> float:  # ty: ignore[empty-body]
    "..."
```

Each becomes e.g. `constexpr int N_STEPS{1000};` before the functions. Names are looked up where
the decorator is written (locals and class bodies, then module-level and imported names), and
values are captured then. The type follows the value's type, as for arguments; `str` becomes
`std::string_view`; override with `"NAME: cpp_type"`. Brace initialisation makes a value that
doesn't fit its type a compile error: `2**40` needs `uint64_t` or `int64_t`. Only values with a C++
literal (numbers, including `inf`/`nan`, `bool`, `str`) work. A local used only in `constants`
needs `# noqa: F841`.

## Gotchas

- **`CppTypeError: Don't know a C++ type for ...`** means the type has no default mapping. Add an
  `Annotated` override (e.g. `Annotated[pd.Series, "py::object"]`).
- **Only numpy arrays are mutable in place by default.** `list`, `dict` and `set` are converted to
  STL copies; to mutate in place, override to `py::list`/`py::dict`/`py::set`. To mutate a bound
  C++ object from another extension, override to a reference (`"ExtObj&"`) and include its header.
- **Callables** work as arguments and return values, interchangeably with Python functions and
  lambdas, via `std::function` (include nothing extra).
- **No recursion at the Python level** and **no compiled lambdas**: the body is an anonymous C++
  lambda, so recurse in C++ with a named `std::function` inside the body. Nested functions work but
  can't capture their enclosing scope.
- **Two functions with the same name in one module become pybind11 overloads** of each other, so
  each Python name dispatches to both. Keep names distinct across files that share a `module_name`.
- **Editing an `#include`-d file doesn't trigger a rebuild**: change the inline code, or delete the
  module's `.checksum` file.
- **Code must be threadsafe under a free-threaded interpreter** (modules are built without the GIL);
  set `XENOFORM_DISABLE_FT` to opt out.
- **Notebooks**: set `module_name` (the default is a hash of the cell's source, so each edit compiles
  a new module and orphans the old one's `ext/` folder). Running the defining cell only registers the
  function; it compiles on the first call, and compile errors appear in that cell. **Any change needs
  a kernel restart**: a process can't unload a compiled module, so without one an edit after a call is
  silently ignored, an edit before the first call may silently lose to the old definition, and a
  function added to a used module raises `AttributeError`.
- **Built modules aren't importable by name** (`import my_module_ext.my_module`): xenoform loads
  them from their files.

## Configuration (environment variables)

| Variable | Effect |
|----------|--------|
| `XENOFORM_EXTMODULE_ROOT` | Where compiled modules go (default `./ext`). Any path. |
| `XENOFORM_DISABLE_FT` | If set, build with the GIL even under a free-threaded interpreter. |
| `XENOFORM_CPP_FORMAT` | clang-format style for the generated source (default `file`, i.e. a `.clang-format` in the project). |
| `XENOFORM_VERBOSE` | Any value (including empty) logs each step (register, check, build, load, redirect) with timings. |
| `XENOFORM_BUILD_TIMEOUT` | Seconds a build may take (positive, default 300); a timeout raises `CompilationError`. |

## Troubleshooting a failed build

A failed build raises `CompilationError` at the first call. Its message is the compiler's **first
error** (later ones are often knock-on effects), a count of the rest, and the path to `build.log`.
For a template error it shows the line in `module.cpp` that instantiated the template rather than
the whole chain. Line numbers refer to the generated `module.cpp`, not the Python file. Every error
and warning is on `e.diagnostics` as `CppDiagnostic`s (`level`, `file`, `line`, `column`, `code`,
`message`, and `rendered`, the full text).

A successful build issues each warning in your code (`module.cpp` and headers under
`extra_include_paths`) as a `CppWarning` (a `UserWarning`), only when the module is (re)built.
Escalate with `warnings.simplefilter("error", CppWarning)`, or by message:
`PYTHONWARNINGS="error:compiler warning"` / pytest `filterwarnings = ["error:compiler warning"]`.

For a module `my_module.py`, the generated files are in `ext/my_module_ext/`:

- `module.cpp` — the generated C++; read it to see exactly what was produced from the signatures.
- `setup.py` — builds the module; rerun by hand with `python setup.py build_ext --inplace` there.
- `build.log` — the full compiler output.
- `my_module.<abi>.checksum` — the hash the binary was built from; delete it to force a rebuild.
- `.build.lock` — serialises concurrent builds of the module (processes or threads); harmless.

The build runs `sys.executable` in a subprocess, so it can't build in an embedded interpreter whose
`sys.executable` isn't Python.

## Working on xenoform itself (not just using it)

If you're editing this library's own source (`src/xenoform/`) rather than using it in a downstream
project, this repo's `AGENTS.md` governs the workflow: plan and get sign-off before non-trivial
changes, run the full quality-gate suite (`ruff check`, `ruff format --check`, `ty check`, `pytest`,
and the examples) before calling anything done, and add a Why/What/Design-decisions/Follow-ups
entry to `JOURNAL.md` for every task.
