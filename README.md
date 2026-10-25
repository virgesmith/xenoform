# `xenoform`: inlined C++ functions

![PyPI - Version](https://img.shields.io/pypi/v/xenoform)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/xenoform)
![PyPI - License](https://img.shields.io/pypi/l/xenoform)

Write and execute superfast C or C++ inside your Python code! Here's how...

Write a type-annotated function or method definition **in python**, add the `compile` decorator and put the **C++
implementation** in a docstr:

```py
import xenoform


@xenoform.compile(vectorise=True)
def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
    "return i > j ? i : j;"
```

Here's what happens automatically when you import a module with `@compile`-decorated functions:

**First call or after code changes:**

1. C++ source code is generated with the Python type signatures translated to C++
2. The extension module is compiled
3. The decorated Python functions are replaced with their compiled C++ implementations

**Subsequent calls:**
The C++ functions execute directly with minimal overhead.

**Change detection:**
Each module stores a hash of its source code and configuration. On first call, xenoform compares it with the hash of
the current source and automatically rebuilds the module if anything has changed. The hash is kept in a `.checksum`
file next to the binary, named after the interpreter's ABI (e.g. `ext/my_module_ext/my_module.cpython-314-x86_64-linux-gnu.checksum`),
so checking an up-to-date module only reads two files. Deleting the checksum file, or the module's folder, forces a
rebuild.

**Where files go:**
By default, the `ext` subfolder contains binaries, generated source code and build scripts, and build logs. To change this location see
[below](#location-of-extension-modules).


## Features

- Supports [`numpy` arrays](https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html) for customised
"vectorised" operations. You can either implement the function directly, or write a scalar function and make
use of pybind11's auto-vectorisation feature, if appropriate. (Parallel library support out of the
box may vary, e.g. on a mac, you may need to manually `brew install libomp` for openmp support)
- By [default](#free-threaded-interpreter), supports parallel execution when the python interpreter is free-threaded.
- Supports positional and keyword arguments with defaults, including positional-only and keyword-only markers (`/`,`*`)
- Supports `*args` and `**kwargs`, mapped  (respectively) to `py::args` and `py::kwargs`. NB type annotations for these
types are still useful for python type checkers.
- Using annotated types, you can override the default mapping of python types to C++ types
- Automatically includes (minimal) required headers for compilation, according the function signatures in the module.
If necessary, headers (and include paths) can be added manually.
- Callable types are supported both as arguments and return values. See [below](#callable-types).
- Compound types are supported, by mapping (by default) to `std::optional` / `std::variant`
- Custom macros and extra headers/compiler/linker commands can be added as necessary
- Can link to separate C++ sources, prebuilt libraries, and even other extension modules. See
[test_external_source.py](src/test/test_external_source.py) [test_external_static.py](src/test/test_external_static.py),
[test_external_shared.py](src/test/test_external_shared.py) and [test_extmodule.py](src/test/test_extmodule.py) for
details.
- Supports pybind11's [return value policies](https://pybind11.readthedocs.io/en/stable/advanced/functions.html#return-value-policies)

Caveats & points to note:

- Compiled python lambdas are not supported but nested functions are, in a limited way - they cannot capture variables
from their enclosing scope
- Top-level recursion is not supported, since the functions themselves are implemented as anonymous C++ lambdas, and
recursion at the python-C++ interface would be hopelessly inefficient anyway. If necessary, implement the recursion
purely in C++ - see the Fibonacci example in [test_types.py](src/test/test_types.py)
- Functions with conflicting compiler or linker settings must be implemented in separate modules
- Auto-vectorisation naively applies operations to
[vector inputs in a piecewise manner](https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html#vectorizing-functions),
and although it will broadcast lower-dimensional arguments where possible (e.g. adding a scalar to a vector), it is
not suitable for more complex operations (e.g. matrix multiplication)
- Using auto-vectorisation incurs a major performance penalty when the function is called with all scalar arguments
- While the ellipsis (`...`) type is supported for array slicing, type annotations containing ellipses are not
translatable to C++. Arguments that may be of this type can be annotated with `typing.EllipsisType`.
- Header files are ordered in sensible groups (inline code, local headers, library headers, system headers), but there
is currently no way to fine-tune this ordering
- For methods, type annotations must be provided for the context: `self: Self` for instance methods, or `cls: type` for
class methods.
- IDE syntax highlighting and linting probably won't work correctly for inline C or C++ code. A workaround is to have
the inline code just call a function in a separate `.cpp` file.
- Any changes to `#include`-d files won't automatically trigger a rebuild - to rebuild either modify the inline code or
delete the module's `.checksum` file (or its folder under `ext`)
- Built modules are loaded from their files, and are not importable by name (e.g. `import my_module_ext.my_module`)
- Inline C++ code will break some pydocstyle linting rules, so these may need to be disabled. Likewise
`ignore[empty-body]` may be required to silence type checkers.

## Usage

Simply decorate your C++ functions with the `compile` decorator factory - it handles all the configuration and
compilation. It can be customised with these optional parameters:

kwarg | type(=default) | description
------|----------------|------------
`vectorise` | `bool=False` | If True, vectorizes the compiled function for array operations.
`define_macros` | `list[str] \| None = None` | `-D` definitions
`extra_includes` | `list[str] \| None = None` | Additional header/inline files to include during compilation.
`extra_include_paths` | `list[str] \| None = None` | Additional paths search for headers.
`extra_compile_args` | `list[str] \| None = None` | Extra arguments to pass to the compiler.
`extra_link_args` | `list[str] \| None = None` | Extra arguments to pass to the linker.
`cxx_std` | `int=20` | C++ standard to compile against
`return_value_policy` | `ReturnValuePolicy=ReturnValuePolicy.Automatic` | [Return value policy](https://pybind11.readthedocs.io/en/stable/advanced/functions.html#return-value-policies)
`help` | `str \| None=None` | Docstring for the function
`module_name` | `str \| None=None` | Extension module to build the function into, by default the stem of the file defining it. Must be an ASCII identifier. Functions from several files with the same `module_name` are built into one module, so must have compatible settings and distinct names. In notebooks, set it explicitly: the default comes from the kernel's temporary file for the cell, so isn't deterministic
`constants` | `list[str] \| None=None` | Python variables to declare as C++ constants, by name, see [below](#constants)

### Constants

The C++ code is a docstring, so it can't refer to Python values, and an f-string isn't a docstring. Instead, list the
variables the C++ needs in `constants`, by name, and each becomes a `constexpr` declaration in the module:

```py
from math import pi  # noqa: F401

from xenoform import compile

N_STEPS = 1000
TOLERANCE = 1e-9
SEED = 2**40


@compile(constants=["N_STEPS", "TOLERANCE", "SEED: uint64_t", "pi"])
def simulate(x: float) -> float:  # ty: ignore[empty-body]
    """
    // constexpr int N_STEPS{1000}; etc. are declared before this function
    ...
    """
```

- Names are looked up where the decorator is written: locals (e.g. in a function or class body) first, then
  module-level and imported names. Values are captured at decoration; reassigning the variable afterwards has no
  effect.
- A variable from an enclosing function is only visible if the decorating scope also uses it.
- The C++ type is translated from the value's type, as for arguments: `int` is `int`, `float` is `double`, numpy
  scalars keep their width. `str` becomes `std::string_view`, as a `std::string` can't be `constexpr`. Override the
  type with `"NAME: cpp_type"`, and supply any header it needs with `extra_includes`.
- Constants are brace-initialised, so a value that doesn't fit the type is a compile error, not a different number:
  `SEED = 2**40` needs `"SEED: uint64_t"` (or `int64_t`).
- Only values with a C++ literal are supported: numbers (including `inf` and `nan`), `bool` and `str`. Containers
  aren't.
- Constants are declared at module scope, so functions in the same module can share them. The same name with
  different values in one module is a redefinition error from the compiler.
- Linters can't see a name used only in a `constants` string, so may flag an import as unused (and `ruff check --fix`
  will delete it). Mark it with `# noqa: F401`, or `# noqa: F841` for a local.


## Performance

To run the example scripts, install the "examples" extra, e.g. `pip install xenoform[examples]` or
`uv sync --extra examples`. Links to the code can be found below.

The examples preload their functions so that everything is compiled and loaded before timing starts, keeping that cost out of the per-call wall-clock times (measured with `perf_counter`). Whilst compilation time will vary widely, the one-off initialisation cost of checking the extension is up-to-date, loading it and redirecting the python stub is well under a millisecond.

### Loops

Implementing loops in optimised compiled code can be orders of magnitude faster than loops in Python. Consider this
example: we have a series of cashflows and we need to compute a running balance. The complication is that a fee is
applied to the balance at each step, making each successive value dependent on the previous one, which prevents any
use of vectorisation. The fastest approach in python using pandas seems to be preallocating an empty series and
accessing it via numpy:

```py
def calc_balances_py(data: pd.Series, rate: float) -> pd.Series:
    """Cannot vectorise, since each value is dependent on the previous value"""
    result = pd.Series(index=data.index)
    result_a = result.to_numpy()
    current_value = 0.0
    for i, value in data.items():
        current_value = (current_value + value) * (1 - rate)
        result_a[i] = current_value
    return result
```

In C++ we can take essentially the same approach. Although there is no direct C++ API for pandas types, since
`pd.Series` and `pd.DataFrame` are implemented in terms of numpy arrays, we can use the python object API
to construct and extract the underlying arrays, taking advantage of the shallow-copy semantics. A C++ type override
(`py::object`) is required as there is no direct C++ equivalent of `pd.Series`, and we need to explicitly add pybind11's
numpy header:

```py
from typing import Annotated

from xenoform import compile

@compile(extra_headers=["<pybind11/numpy.h>"])
def calc_balances_cpp(data: Annotated[pd.Series, "py::object"], rate: float) -> Annotated[pd.Series, "py::object"]:  # ty: ignore[empty-body]
    """
```
```cpp
    // Import pandas
    auto pd = py::module::import("pandas");
    // Construct an empty pd.Series with the same index as the input
    auto result = pd.attr("Series")(py::arg("index") = data.attr("index"));

    // Access the values via numpy/py::array_t
    auto data_a = data.attr("to_numpy")().cast<py::array_t<int64_t>>();

    // for pandas >= 3 we need to explicitly make the underlying numpy array writeable via the python API.
    // (the pybind11 API doesn't appear to support modification of flags)
    auto result_np = result.attr("to_numpy")();
    result_np.attr("flags").attr("writeable") = true;
    auto result_a = result_np.cast<py::array_t<double>>();

    auto n = data_a.request().shape[0];
    auto d = data_a.unchecked<1>();
    auto r = result_a.mutable_unchecked<1>();

    // Do the calculation
    double current_value = 0.0;
    for (py::ssize_t i = 0; i < n; ++i) {
        current_value = (current_value + d(i)) * (1.0 - rate);
        r(i) = current_value;
    }
    return result;
```
```py
    """
```

Needless to say the C++ implementation vastly outperforms the python (3.14) implementation across the board:

N | py (ms) | cpp (ms) | speedup
-:|--------:|---------:|-----------:
1000 | 0.2 | 0.1 | 261%
10000 | 1.4 | 0.1 | 1485%
100000 | 14.2 | 0.6 | 2384%
1000000 | 122.5 | 3.5 | 3385%
10000000 | 1225.9 | 28.6 | 4185%

Full code is in [examples/loop.py](./examples/loop.py).

### `numpy` and vectorised operations

> "vectorisation" in this sense means implementing loops in compiled - rather than interpreted - code. In fact, the C++
implementation below also implements various optimisations including but by no means limited to "true" vectorisation (meaning
hardware SIMD instructions).

For "standard" linear algebra and array operations, implementations in *xenoform* are unlikely to significantly outperform heavily
optimised numpy implementations, such as matrix multiplication.

However, significant performance improvements may be seen for more "bespoke" operations, particularly for
larger objects (the pybind11 machinery has a constant overhead).

For example, to compute a distance matrix between $N$ points in $D$ dimensions, an efficient `numpy` implementation
could be:

```py
def calc_dist_matrix_py(p: npt.NDArray) -> npt.NDArray:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))
```
bearing in mind there is some redundancy here as the resulting matrix is symmetric; however vectorisation with
redundancy will always win the tradeoff against loops with no redundancy.

In C++ this tradeoff does not exist. A reasonably well optimised C++ implementation using *xenoform* is:

```py
from xenoform import compile

@compile(extra_compile_args=["-fopenmp"], extra_link_args=["-fopenmp"])
def calc_dist_matrix_cpp(points: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:  # ty: ignore[empty-body]
    """
```
```cpp
    py::buffer_info buf = points.request();
    if (buf.ndim != 2)
        throw std::runtime_error("Input array must be 2D");

    size_t n = buf.shape[0];
    size_t d = buf.shape[1];

    py::array_t<double> result({n, n});
    auto r = result.mutable_unchecked<2>();
    auto p = points.unchecked<2>();

    // Avoid redundant computation for symmetric matrix
    #pragma omp parallel for schedule(static)
    for (size_t i = 0; i < n; ++i) {
        r(i, i) = 0.0;
        for (size_t j = i + 1; j < n; ++j) {
            double sum = 0.0;
            #pragma omp simd reduction(+:sum)
            for (size_t k = 0; k < d; ++k) {
                double diff = p(i, k) - p(j, k);
                sum += diff * diff;
            }
            double dist = std::sqrt(sum);
            r(i, j) = dist;
            r(j, i) = dist;
        }
    }
    return result;
```
```py
    """
```

Wall-clock execution times (in ms, measured with `perf_counter`) are shown below for each implementation for a varying number of 3d points. The compiled implementation is significantly faster:

N | py (ms) | cpp (ms) | speedup
-:|--------:|---------:|-----------:
100 | 0.5 | 0.2 | 125%
300 | 4.0 | 0.2 | 1960%
1000 | 29.9 | 1.0 | 2795%
3000 | 232.7 | 8.0 | 2804%
10000 | 2568.3 | 83.2 | 2988%

The compiled version wins on several fronts at once, which compound:

- **No redundant work.** The result is symmetric, so the C++ loop computes only the upper triangle (`j > i`) and mirrors it, roughly halving the distance calculations. The `numpy` version computes the full $N \times N$ matrix — it can't skip the lower triangle without falling back to Python-level loops that would erase its vectorisation advantage.
- **No large temporaries.** `numpy` broadcasts `p[:, None, :] - p[None, :, :]` into an $N \times N \times D$ intermediate array, squares it, then reduces over the last axis. For $N=10000, D=3$ that's a ~2.4 GB temporary, so the computation is limited by memory bandwidth. The C++ version accumulates each squared distance in a register in a single pass, touching each input point repeatedly from cache and only ever allocating the $N \times N$ output.
- **SIMD vectorisation.** `#pragma omp simd reduction(+:sum)` lets the compiler evaluate the inner dimension loop with vector instructions, several `double`s per instruction.
- **Multithreading.** `#pragma omp parallel for` spreads the outer loop across all available cores (via OpenMP), so on an $n$-core machine the wall-clock time drops by up to a further factor of $n$. This is why the times are measured with `perf_counter` (wall clock) and not `process_time` — the latter would sum CPU time across every core and hide exactly this speedup.

The gains grow with $N$: at $N=100$ the pybind11 call overhead dominates and the edge is modest, but by $N \geq 1000$ the memory-bandwidth and parallelism advantages take over and the compiled version is ~28–30x faster.

Full code is in [examples/distance_matrix.py](./examples/distance_matrix.py).

## Configuration

### Location of Extension Modules

By default, compiled modules are placed in an `ext` subdirectory of your project's root. If this location is unsuitable,
it can be overridden using the environment variable `XENOFORM_EXTMODULE_ROOT`, which can be any path, absolute or
relative to the working directory.

### Free-threaded Interpreter

By default, if the interpreter is free-threaded, extension modules will be built without the GIL. This requires the
extension code to be threadsafe. If xenoform detects an environment variable `XENOFORM_DISABLE_FT`, free-threading is
disabled.

## Type Translations

### Default mapping

Basic Python types are recursively mapped to C++ types, like so:

Python | C++
-------|----
`None` | `void`
`int` | `int`
`np.int8` / `np.int16` / `np.int32` / `np.int64` | `int8_t` / `int16_t` / `int32_t` / `int64_t`
`np.uint8` / `np.uint16` / `np.uint32` / `np.uint64` | `uint8_t` / `uint16_t` / `uint32_t` / `uint64_t`
`bool` | `bool`
`float` | `double`
`np.float32` | `float`
`np.float64` | `double`
`complex` | `std::complex<double>`
`np.complex64` | `std::complex<float>`
`np.complex128` | `std::complex<double>`
`str` | `std::string`
`np.ndarray` | `py::array_t`
`bytes` | `py::bytes`
`bytearray` | `py::bytearray`
`list` | `std::vector`
`set` | `std::unordered_set`
`frozenset` | `const std::unordered_set`
`dict` | `std::unordered_map`
`tuple` | `std::tuple`
`slice` | `py::slice`
`Any` | `py::object`
`Self` | `py::object`
`type` | `py::type`
`*args` | `py::args`
`**kwargs` | `const py::kwargs&`
`T \| None` | `std::optional<T>`
`T \| U` | `std::variant<T, U>`
`Callable` | `std::function`
`...` | `py::ellipsis`

Thus, `dict[str, list[float]]` becomes - by default -  `std::unordered_map<std::string, std::vector<double>>`. Also,
any C++ headers required to define the mapped type will be automatically #include'd in the module source code.

By default, only `np.array` is mapped to a type that supports in-place modification. For `dict`, `list`,
or `set` map to the corresponding pybind11 type, e.g. `py::list` (see below). Note also `py::bytearray` has no mutable
methods.

### Custom Type Mappings

The mapping of types above is not exhaustive and there may be a number of reasons for requiring a new or different
mapping. Some examples:

- to restrict inputs to narrower C++ types. E.g. use an unsigned type:

    ```py
    from typing import Annotated

    from xenoform import compile


    @compile()
    def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]: ...
    ```

- there is no explicit C++ type, e.g. `pd.Series`. This example is covered in the performance section [above](#loops).
The override replaces the whole type, so its type parameters needn't have a mapping either, e.g.
`Annotated[npt.NDArray[np.datetime64], "py::array"]`.

- a different mapping to the default is required - e.g. for in-place modification of a list:

    ```py
    @compile()
    def mutate_list(a: Annotated[list[int], "py::list"]) -> None:
        """
        a.append(42);
        """
    ```

    Note that the argument is passed *by value* - like `np.array` it is shallow-copied, so no requirement for pointers
    or references. Consult the [pybind11 documentation](https://pybind11.readthedocs.io/en/stable/reference.html)
    for more info.

- the type is a bound C++ object from a separate extension module. In-place modification may also be required, which
can be achieved by qualifying the override type as a mutable reference. A header file with the C++ definition must
also be provided:

    ```py
    from other_ext import ExtObj


    @compile(extra_include_paths=["path_to_other_ext_include"], extra_includes=['"extobj.h"'])
    def mutate_ext_object(obj: Annotated[ExtObj, "ExtObj&"], n: int) -> None:
        """
        obj.set(n);
        """
    ```

    See [test_extmodule.py](src/test/test_extmodule.py) for more examples.

- an [opaque type](https://pybind11.readthedocs.io/en/stable/advanced/cast/stl.html#making-opaque-types) is required,
e.g. for exposing STL containers directly to python. This must be registered in a separate module, and the C++ type must be known, and can be qualified as necessary. Here we modify it through a pointer:

    ```py
    from other_ext import UIntVector


    @compile(extra_includes=["<pybind11/stl.h>"])
    def mutate_uint_vector_ptr(vec: Annotated[UIntVector, "std::vector<uint64_t>*"], n: int) -> None:
        """
        for (auto& i: *vec) i += n;
        """
    ```

    Note we had to manually specify an extra header file.

## Callable Types

Passing and returning functions to and from C++ is supported, and they can be used interchangeably with python functions
and lambdas. Annotate types using `Callable` e.g.

```py
@compile()
def modulo(n: int) -> Callable[[int], int]:  # ty: ignore[empty-body]
    """
    return [n](int i) { return i % n; };
    """
```

pybind11's `py::function` and `py::cpp_function` types do not intrinsically contain information about the function's
argument and return types, and are not used by default, although they can be used as type overrides if
necessary, although code may also need to be modified to deal with `py::object` return types.

See the examples in [test_callable.py](src/test/test_callable.py) for more detail.

## C++ Code Style

By default, generated C++ code is formatted using `clang-format` (if available) using it's default style (LLVM). This
can be changed by either:

- setting the environment variable `XENOFORM_CPP_FORMAT` to an alternative style, e.g. "GNU"
- defining a custom style in `.clang-format` in the project root directory

See `clang-format` documentation for more info.

## Troubleshooting

The generated module source code is written to `module.cpp` in a specific folder (e.g. `ext/my_module_ext`), along
with the `setup.py` that builds it. The build runs in a separate process, using the same interpreter, and its full
output, including any compiler errors, goes to `build.log` in that folder. To rerun a build by hand, run
`python setup.py build_ext --inplace` in that folder.

If the build fails, the `CompilationError` shows the compiler's first error (later errors are often knock-on effects of
it), a count of the rest, and the path to `build.log`. Line numbers refer to the generated `module.cpp`. For a
template error, of the compiler's instantiation chain only the line in `module.cpp` that started it is shown, e.g.:

```txt
xenoform.errors.CompilationError: building my_module_ext.my_module failed (line numbers refer to ext/my_module_ext/module.cpp):
module.cpp:25:18:   required from here
   25 |         std::sort(v.begin(), v.end(), 42);
      |         ~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~
/usr/include/c++/15/bits/predefined_ops.h:158:30: error: expression cannot be used as a function
  158 |         { return bool(_M_comp(*__it1, *__it2)); }
      |                       ~~~~~~~^~~~~~~~~~~~~~~~
(2 more errors, 2 warnings, full log: ext/my_module_ext/build.log)
```

Every error and warning is also available, unabridged, as `CppDiagnostic`s in the exception's `diagnostics` attribute
(gcc, clang and MSVC output is recognised). If no error can be recognised, e.g. for a linker failure, the exception
shows the end of the log instead.

Compiler warnings in your code are issued as `CppWarning`s (a `UserWarning`) when the module is built, attributed to
the call that triggered the build. Each carries its `CppDiagnostic` as `diagnostic`. "Your code" means `module.cpp` and
headers under your `extra_include_paths`: warnings from the standard library's, Python's, pybind11's and numpy's
headers stay in `build.log`. An up-to-date module isn't rebuilt, so its warnings aren't repeated. They can be filtered
like any other warning, e.g. to make them errors in CI:

```py
import warnings

from xenoform import CppWarning

warnings.simplefilter("error", CppWarning)
```

or, as `-W`/`PYTHONWARNINGS` can't name a category from a third-party package, by message:
`PYTHONWARNINGS="error:compiler warning"`, or with pytest, `filterwarnings = ["error:compiler warning"]`.

Because the build runs `sys.executable`, xenoform can't build modules in an embedded interpreter whose `sys.executable`
isn't Python.

Modules can be built concurrently, by several processes (e.g. pytest-xdist or multiprocessing) or threads: a lock file in
each module's folder makes sure a module is built only once. Threads building different modules don't wait for each
other. On Linux and macOS the (empty) `.build.lock` file stays after the build: deleting a lock file on release would
let two processes hold the lock at once.

If xenoform detects an environment variable `XENOFORM_VERBOSE` (any value, including empty), debug logging of the steps
taken is enabled, with timings, e.g.:

```txt
$ python perf.py
    0.000285 registering perf_ext.perf.array_max (in ext)
    0.000427 registering perf_ext.perf.array_max_autovec (in ext)
    0.169118 module is up-to-date (e73f2972262ff9b0ae2c5c7a4abde95c035fb85d7b29317becf14ee282b5c79a)
    0.169668 imported compiled module perf_ext.perf
    0.169684 redirected perf.array_max to compiled function perf_ext.perf._array_max
    0.213621 redirected perf.array_max_autovec to compiled function perf_ext.perf._array_max_autovec
    ...
```

## See also

[https://pybind11.readthedocs.io/en/stable/](https://pybind11.readthedocs.io/en/stable/)
