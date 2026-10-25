from xenoform.diagnostics import CppDiagnostic


class XenoformError(RuntimeError):
    pass


class AnnotationError(XenoformError):
    pass


class CompilationError(XenoformError):
    """A failed build. ``diagnostics`` holds every error and warning parsed from the compiler output"""

    def __init__(self, message: str, diagnostics: list[CppDiagnostic] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or []


class CppTypeError(XenoformError):
    pass


class CppWarning(UserWarning):
    """A compiler warning from a successful build, with the parsed diagnostic as ``diagnostic``"""

    def __init__(self, message: str, diagnostic: CppDiagnostic) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic
