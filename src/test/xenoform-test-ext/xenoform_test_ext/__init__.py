import importlib.metadata

__version__ = importlib.metadata.version("xenoform_test_ext")

from _xenoform_test_ext import *  # ty: ignore[import-not-found] # noqa: F403
