"""Example of custom vectorised function performance - python vs inline C++"""

import time

import numpy as np
import numpy.typing as npt

from xenoform import compile


def calc_dist_matrix_py(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))


@compile(extra_compile_args=["-fopenmp"], extra_link_args=["-fopenmp"])
def calc_dist_matrix_cpp(points: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:  # ty: ignore[empty-body]
    """
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
    """


if __name__ == "__main__":
    print("N | py (ms) | cpp (ms) | speedup (%)")
    print("-:|--------:|---------:|-----------:")

    for size in [100, 300, 1000, 3000, 10000]:
        p = np.random.uniform(size=(size, 3))

        start = time.process_time()
        dist_p = calc_dist_matrix_py(p)
        elapsed_p = time.process_time() - start

        start = time.process_time()
        dist_c = calc_dist_matrix_cpp(p)
        elapsed_c = time.process_time() - start

        assert np.abs(dist_c - dist_p).max() < 1e-15

        speedup = elapsed_p / elapsed_c - 1.0

        print(f"{size} | {elapsed_p * 1000:.1f} | {elapsed_c * 1000:.1f} | {speedup:.0%}")
