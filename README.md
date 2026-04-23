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

When Python loads this file, all functions using this decorator have their function signatures translated to C++ and
the source for an extension module is generated. The first time any function is called, the module is built, and the
attribute corresponding to the (empty) Python function is replaced with the C++ implementation in the extension module.

Subsequent calls to the function incur minimal overhead, as the attribute corresponding now points to the C++
implementation.

Each module stores a hash of the source code that built it. Modules are checked on load and automatically rebuilt when
changes to any of the functions in the module (including decorator parameters) are detected.

By default, the binaries, source code and build logs for the compiled modules can be found in the `ext` subfolder (this
location can be changed).

## Features

- Supports [`numpy` arrays](https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html) for customised
"vectorised" operations. You can either implement the function directly, or write a scalar function and make
use of pybind11's auto-vectorisation feature, if appropriate. (Parallel library support out of the
box may vary, e.g. on a mac, you may need to manually `brew install libomp` for openmp support)
- By [default](#free-threaded-interpreter), supports parallel execution when the python interpreter is free-threaded.
- Supports positional and keyword arguments with defaults, including positional-only and keyword-only markers (`/`,`*`)
- Supports `*args` and `**kwargs`, mapped  (respectively) to `py::args` and `py::kwargs`. NB type annotations for these
types are still useful for python type checkers.
- Using annotated types, you can:
    - override the default mapping of python types to C++ types
    - where necessary, qualify C++ arguments by value, reference, or (dumb) pointer, with or without `const`
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
delete the ext module
- Inline C++ code will break some pydocstyle linting rules, so these may need to be disabled. Likewise
`type: ignore[empty-body]` may be required to silence mypy.

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
`verbose` | `bool=False` | enable debug logging


## Performance

To run the example scripts, install the "examples" extra, e.g. `pip install xenoform[examples]` or
`uv sync --extra examples`. Links to the code can be found below.

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
    auto pd = py::module::import("pandas");
    auto result = pd.attr("Series")(py::arg("index") = data.attr("index"));

    auto data_a = data.attr("to_numpy")().cast<py::array_t<int64_t>>();
    auto result_a = result.attr("to_numpy")().cast<py::array_t<double>>();

    auto n = data_a.request().shape[0];
    auto d = data_a.unchecked<1>();
    auto r = result_a.mutable_unchecked<1>();

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

Needless to say, the C++ implementation vastly outperforms the python (3.13) implementation for all but the smallest arrays:

N | py (ms) | cpp (ms) | speedup (%)
-:|--------:|---------:|-----------:
1000 | 0.7 | 1.1 | -43
10000 | 3.3 | 0.3 | 1067
100000 | 35.1 | 1.7 | 1950
1000000 | 311.5 | 6.5 | 4709
10000000 | 2872.4 | 42.9 | 6601

Full code is in [examples/loop.py](./examples/loop.py).

### `numpy` and vectorised operations

> "vectorisation" in this sense means implementing loops in compiled - rather than interpreted - code. In fact, the C++
implementation below also various optimisations including but by no means limited to "true" vectorisation (meaning
hardware SIMD instructions).

For "standard" linear algebra and array operations, implementations in *xenoform* are very unlikely to improve on heavily
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

Execution times (in ms) are shown below for each implementation for a varying number of 3d points. Even at relatively small sizes, the compiled implementation is significantly faster.

N | py (ms) | cpp (ms) | speedup (%)
-:|--------:|---------:|-----------:
100 | 0.5 | 2.5 | -82%
300 | 3.2 | 2.2 | 46%
1000 | 43.3 | 13.6 | 218%
3000 | 208.2 | 82.5 | 152%
10000 | 2269.0 | 803.2 | 183%

Full code is in [examples/distance_matrix.py](./examples/distance_matrix.py).

## Configuration

### Location of Extension Modules

By default, compiled modules are placed in an `ext` subdirectory of your project's root. If this location is unsuitable,
it can be overridden using the environment variable `XENOFORM_EXTMODULE_ROOT`. NB avoid using characters in paths
(e.g. space, hyphen) that would not be valid in a python module name.

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
`np.int32` | `int32_t`
`np.int64` | `int64_t`
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

### Custom Type Mappings and Qualifiers

The mapping of types above is not exhaustive and there may be a number of reasons for requiring a new or different
mapping. Some examples:

- to restrict inputs to narrower C++ types. E.g. use an unsigned type:

    ```py
    from typing import Annotated

    from xenoform import compile

    @compile()
    def fibonacci(n: Annotated[int, "uint64_t"]) -> Annotated[int, "uint64_t"]:
        ...
    ```

- there is no explicit C++ type, e.g. `pd.Series`. This example is covered in the performance section [above](#loops).

- a different mapping to the default is required - e.g. for in-place modification of a list:

    ```py
    @compile()
    def mutate_list(a: Annotated[list[int], "py::list"]) -> None:
        """
        a.append(42);
        """
    ```

    Note that the argument is passed *by value* - like `np.array` it is shallow-copied, so no requirement for pointers or references. Consult the
    [pybind11 documentation](https://pybind11.readthedocs.io/en/stable/reference.html) for more info.

- the type is a bound C++ object from a separate extension module. In-place modification may also be required. The type
override must be provided, as well as a header file for the C++ definition:

    ```py
    from other_ext import ExtObj

    @compile(extra_include_paths=["path_to_other_ext_include"], extra_includes=['"extobj.h"'])
    def mutate_ext_object(obj: Annotated[ExtObj, "ExtObj&"], n: int) -> None:
        """
        obj.set(n);
        """
    ```

    See test_extmodule.py for more examples.

- an [opaque type](https://pybind11.readthedocs.io/en/stable/advanced/cast/stl.html#making-opaque-types) is required,
e.g. for exposing STL containers directly to python. This must be registered in a separate module, and the C++ type must be known, but can be qualified as necessary. Here we modify it through a pointer:

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

The generated module source code is written to `module.cpp` in a specific folder (e.g. `ext/my_module_ext`). Compiler
commands are redirected to `build.log` in the that folder. NB: build errors refuse to be redirected to a file, and
`build.log` is not produced when running via pytest, due to the way it captures output streams.

Adding `verbose=True` to the `compile(...)` decorator logs the steps taken, with timings, e.g.:

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
