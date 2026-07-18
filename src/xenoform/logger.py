from datetime import datetime
from functools import cache
from typing import Any

from xenoform.config import get_config

# logging breaks after using redirect_stdout: ValueError: I/O operation on closed file.
# revert to a simple homemade solution for now


class Logger:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.t0 = datetime.now().timestamp()

    def __call__(self, *args: Any) -> None:
        if self.enabled:
            print(f"{datetime.now().timestamp() - self.t0:12.6f}", *args)


@cache
def get_logger() -> Logger:
    "Return logger, enabled when the XENOFORM_VERBOSE env var is set (disabled by default)"
    return Logger(enabled=get_config().verbose is not None)
