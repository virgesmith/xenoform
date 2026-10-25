import importlib.metadata

__version__ = importlib.metadata.version("xenoform")


from .compile import compile
from .cppmodule import ReturnValuePolicy
from .diagnostics import CppDiagnostic
from .errors import AnnotationError, CompilationError, CppTypeError, CppWarning
from .utils import (
    Platform,
    platform_specific,
)

__all__ = [
    "AnnotationError",
    "CompilationError",
    "CppDiagnostic",
    "CppTypeError",
    "CppWarning",
    "Platform",
    "ReturnValuePolicy",
    "__version__",
    "compile",
    "platform_specific",
]
