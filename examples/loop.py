"""Example of unvectorisable function performance - python vs inline C++"""

from time import perf_counter
from typing import Annotated

import numpy as np
import pandas as pd

from xenoform import compile


def calc_balances_py(data: pd.Series, rate: float) -> pd.Series:
    """Cannot vectorise, since each value is dependent on the previous value"""
    result = pd.Series(index=data.index)
    result_a = result.to_numpy()
    result_a.flags.writeable = True  # required in pandas 3+
    current_value = 0.0
    for i, value in data.items():
        current_value = (current_value + value) * (1 - rate)
        result_a[i] = current_value
    return result


@compile(extra_includes=["<pybind11/numpy.h>"])
def calc_balances_cpp(data: Annotated[pd.Series, "py::object"], rate: float) -> Annotated[pd.Series, "py::object"]:  # ty: ignore[empty-body]
    """
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
    """


def main() -> None:
    """Run a performance comparison for varying series lengths"""
    rng = np.random.default_rng(19937)
    rate = 0.001

    print("N | py (ms) | cpp (ms) | speedup")
    print("-:|--------:|---------:|-----------:")
    for n in [1000, 10000, 100000, 1000000, 10000000]:
        data = pd.Series(index=range(n), data=rng.integers(-100, 101, size=n), name="cashflow")

        start = perf_counter()
        py_result = calc_balances_py(data, rate)
        py_time = perf_counter() - start

        start = perf_counter()
        # Although pybind11/C++ doesn't understand the type pd.Series, it can use the py::object API to manipulate
        # and create instances of this type
        cpp_result = calc_balances_cpp(data, rate)
        cpp_time = perf_counter() - start

        # guard against a zero cpp_time (possible on platforms with a coarse timer for the smallest n)
        speedup = f"{(py_time / cpp_time - 1.0):.0%}" if cpp_time else "n/a"
        print(f"{n} | {py_time * 1000:.1f} | {cpp_time * 1000:.1f} | {speedup}")
        assert py_result.equals(cpp_result)


if __name__ == "__main__":
    main()
