import importlib.metadata

__version__ = importlib.metadata.version("xenoform_test_ext")

from _xenoform_test_ext import *  # ty: ignore[unresolved-import] # noqa: F403
