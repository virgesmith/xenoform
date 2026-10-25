"""
Parse compiler output from build.log into structured diagnostics.

gcc and clang emit each diagnostic as a group: optional context lines (``In file included from``, ``In instantiation
of``, ``required from here``), the diagnostic line itself, then its source snippet and any notes, which may have
context of their own. MSVC emits one line per diagnostic, with any notes after it.
"""

import re
from dataclasses import dataclass

# gcc/clang: module.cpp:23:9: error: 'ARSE' was not declared in this scope
_GCC = re.compile(
    r"^(?P<file>[^\s:][^:]*?):(?P<line>\d+):(?:(?P<column>\d+):)? (?P<level>fatal error|error|warning|note): "
    r"(?P<message>.*)$"
)
# MSVC: C:\path\module.cpp(23,9): error C2065: 'ARSE': undeclared identifier
_MSVC = re.compile(
    r"^(?P<file>\S.*?)\((?P<line>\d+)(?:,(?P<column>\d+))?\)\s?: (?P<level>fatal error|error|warning|note)"
    r"(?: (?P<code>[A-Z]+\d+))?: (?P<message>.*)$"
)
# gcc/clang lines that introduce the diagnostic or note after them
_INCLUDE_CONTEXT = re.compile(r"^(In file included from |\s+from \S)")
_OTHER_CONTEXT = re.compile(r"^(?P<file>[^\s:][^:]*?)(:\d+(:\d+)?:\s+required (from|by) |: In )")
# lines after which nothing more belongs to the current diagnostic
_TRAILER = re.compile(
    r"^(compilation terminated\.|\d+ (errors?|warnings?)( and \d+ warnings?)? generated\.|error: [Cc]ommand )"
)
# in case colour is forced, e.g. by -fdiagnostics-color=always
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# keeps the exception readable when a diagnostic is long (e.g. clang's template instantiation notes)
_MAX_BRIEF_LINES = 30


@dataclass(frozen=True)
class CppDiagnostic:
    """An error or warning from the compiler, with all its lines as the compiler rendered them"""

    level: str
    file: str
    line: int
    column: int | None
    code: str | None
    message: str
    rendered: str

    @property
    def is_error(self) -> bool:
        return self.level in ("error", "fatal error")


def _match(line: str) -> re.Match[str] | None:
    return _GCC.match(line) or _MSVC.match(line)


def _is_head(line: str) -> bool:
    """An error or warning, as opposed to a note"""
    m = _match(line)
    return m is not None and m["level"] != "note"


def _is_context(line: str) -> bool:
    return bool(_INCLUDE_CONTEXT.match(line) or _OTHER_CONTEXT.match(line))


def parse_diagnostics(log: str) -> list[CppDiagnostic]:
    """The errors and warnings in a build log, in order"""
    diagnostics: list[CppDiagnostic] = []
    lines: list[str] = []  # the current diagnostic's lines
    head: re.Match[str] | None = None  # the current diagnostic's own line
    # context lines are held until the next diagnostic line shows what they introduce: a new error or warning, or a
    # note on the current one
    pending: list[str] = []

    def close() -> None:
        if head is not None:
            diagnostics.append(
                CppDiagnostic(
                    level=head["level"],
                    file=head["file"],
                    line=int(head["line"]),
                    column=int(head["column"]) if head["column"] else None,
                    code=head.groupdict().get("code"),
                    message=head["message"],
                    rendered="\n".join(lines),
                )
            )

    for line in _ANSI.sub("", log).splitlines():
        if _is_head(line):
            close()
            lines, head, pending = [*pending, line], _match(line), []
        elif _match(line):
            lines += [*pending, line]
            pending = []
        elif _is_context(line):
            pending.append(line)
        elif _TRAILER.match(line):
            close()
            lines, head, pending = [], None, []
        elif pending:
            # the snippet under a context line, e.g. "required from here"
            pending.append(line)
        elif head is not None:
            # the diagnostic's or a note's snippet
            lines.append(line)
    close()
    return diagnostics


def _points_at(line: str, source: str) -> bool:
    m = _OTHER_CONTEXT.match(line)
    return m is not None and m["file"].replace("\\", "/").rsplit("/", 1)[-1] == source


def brief(diagnostic: CppDiagnostic, source: str = "module.cpp") -> str:
    """
    The diagnostic for an exception message. Of the context before it, include chains are dropped, as is any other
    context (with its snippet) that doesn't point at the generated source. In a template error that leaves the line
    of user code that instantiated the template, rather than the whole instantiation chain. Everything from the
    diagnostic's own line on is kept, notes included. The full text is in ``rendered``
    """
    lines = diagnostic.rendered.splitlines()
    head = next(i for i, line in enumerate(lines) if _is_head(line))
    kept: list[str] = []
    keep = False
    for line in lines[:head]:
        if _is_context(line):
            keep = _points_at(line, source)
        # a snippet line goes with the context line above it
        if keep:
            kept.append(line)
    kept += lines[head:]
    if len(kept) > _MAX_BRIEF_LINES:
        kept = [*kept[:_MAX_BRIEF_LINES], f"... ({len(kept) - _MAX_BRIEF_LINES} more lines)"]
    return "\n".join(kept)
