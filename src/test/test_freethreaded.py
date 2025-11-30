import time
from concurrent.futures import ThreadPoolExecutor

from itrx import Itr

from xenoform import compile
from xenoform.utils import build_freethreaded


@compile(extra_includes=["<thread>", "<chrono>"])
def artifically_slow_function(time: float) -> None:
    """
    auto ms = static_cast<int>(time * 1000);
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    """


def test_freethreaded() -> None:
    # ensure module is built by calling the function before any timing
    artifically_slow_function(0.0)

    t = 0.1
    # GIL should run sequentially (~2 * 0.1), freethreaded in parallel (~0.1, depending on available resources)
    n_threads = 2

    start = time.perf_counter()
    with ThreadPoolExecutor() as executor:
        futures = Itr(executor.submit(artifically_slow_function, t) for _ in range(n_threads))
        futures.consume()
    elapsed = time.perf_counter() - start

    if build_freethreaded():
        # this cant be tested reliably in pytest,
        # assert elapsed < t * n_threads
        print(elapsed, t * n_threads)
    else:
        assert elapsed > t * n_threads


if __name__ == "__main__":
    print("FT?", build_freethreaded())
    test_freethreaded()
