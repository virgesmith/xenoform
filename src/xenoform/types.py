# dummy generic types for references and pointers
from collections.abc import Callable
from copy import copy
from enum import StrEnum
from types import EllipsisType, NoneType, UnionType
from typing import Annotated, Any, Self, get_args, get_origin

import numpy as np

from xenoform.errors import CppTypeError


class CppQualifier(StrEnum):
    Auto = "{}"
    Ref = "{}&"
    CRef = "const {}&"
    RRef = "{}&&"
    Ptr = "{}*"
    PtrC = "const {}*"  # pointer-to-const
    CPtr = "{}* const"  # const pointer
    CPtrC = "const {}* const"
    # NB pybind11 doesnt seem to support shared/unique ptr as a function arg


DEFAULT_TYPE_MAPPING = {
    None: "void",  # py::none?
    int: "int",
    np.int32: "int32_t",
    np.int64: "int64_t",
    bool: "bool",
    float: "double",
    np.float32: "float",
    np.float64: "double",
    complex: "std::complex<double>",
    np.complex64: "std::complex<float>",
    np.complex128: "std::complex<double>",
    str: "std::string",
    np.ndarray: "py::array_t",
    bytes: "py::bytes",
    bytearray: "py::bytearray",
    list: "std::vector",
    set: "std::unordered_set",
    frozenset: "const std::unordered_set",
    dict: "std::unordered_map",
    tuple: "std::tuple",  # ... ellipsis not supported here
    slice: "py::slice",
    Any: "py::object",
    Self: "py::object",
    type: "py::type",
    UnionType: "std::variant",
    Callable: "std::function",
    EllipsisType: "py::ellipsis",
}

header_requirements = {
    "std::complex<double>": "<pybind11/complex.h>",
    "std::complex<float>": "<pybind11/complex.h>",
    "std::string": "<string>",
    "std::vector": "<pybind11/stl.h>",
    "std::unordered_set": "<pybind11/stl.h>",
    "std::unordered_map": "<pybind11/stl.h>",
    "std::tuple": "<pybind11/stl.h>",
    "py::array_t": "<pybind11/numpy.h>",
    "std::variant": "<pybind11/stl.h>",
    "std::optional": "<pybind11/stl.h>",
    "std::function": "<pybind11/functional.h>",
}


class PyTypeTree:
    """Tree structure for python types"""

    def __init__(self, type_: type) -> None:
        origin = get_origin(type_)
        if origin is Annotated:
            raise TypeError("Don't pass annotated types directly to PyTypeTree, use translate_type")

        self.type = origin if origin is not None else type_

        if self.type is Callable:
            # flatten args, put ret first
            args, ret = get_args(type_)
            self.subtypes = (PyTypeTree(ret), *(PyTypeTree(a) for a in args))
        else:
            self.subtypes = tuple(PyTypeTree(t) for t in get_args(type_))

    def __repr__(self) -> str:
        if self.type == Ellipsis:
            return "..."
        if self.subtypes:
            return f"{self.type.__name__}[{', '.join(repr(t) for t in self.subtypes)}]"
        return f"{self.type.__name__}"


class CppTypeTree:
    """Mapped tree structure for C++ types"""

    def __init__(self, tree: PyTypeTree, *, override: str | None = None, qualifier: CppQualifier | None = None) -> None:
        self.type = DEFAULT_TYPE_MAPPING.get(tree.type)  # type: ignore[arg-type]
        if not self.type and not override:
            raise CppTypeError(f"Don't know a C++ type for '{tree.type}' and no override provided")
        self.override = override
        self.qualfier = qualifier
        # special treatment for numpy arrays
        if tree.type == np.ndarray:
            self.subtypes: tuple[CppTypeTree, ...] = (CppTypeTree(tree.subtypes[1].subtypes[0]),)
        else:
            self.subtypes = tuple(CppTypeTree(t) for t in tree.subtypes if t.type is not NoneType)
        # if we have a "T | None" -> std::variant with one fewer type param, make it a std::optional
        if self.type == "std::variant" and len(self.subtypes) == len(tree.subtypes) - 1:
            if len(self.subtypes) > 1:
                # T | U | None -> std::optional<std::variant<T, U>>
                subtype = copy(self)
                subtype.override = None
                subtype.qualfier = None
                self.subtypes = (subtype,)
            self.type = "std::optional"

    def __repr__(self) -> str:
        if self.override:
            return self.override
        t = f"{self.type}"
        if self.type == "std::function":
            t = t + f"<{self.subtypes[0]}({', '.join(repr(t) for t in self.subtypes[1:])})>"
        elif self.subtypes:
            t = t + f"<{', '.join(repr(t) for t in self.subtypes)}>"
        if self.qualfier:
            t = self.qualfier.format(t)
        return t

    def headers(self, mapping: dict[str, str], _collected: list[str] | None = None) -> list[str]:
        """
        Returns headers needed based on the types in the structure
        2nd argument used internally to collect recursively
        """
        _collected = _collected or []
        # if you override the C++ signature, you may need to explicitly supply any header required
        if self.override:
            return _collected
        if h := mapping.get(self.type or ""):
            _collected.append(h)
        for st in self.subtypes:
            _collected = st.headers(mapping, _collected)
        return _collected


def parse_annotation(origin: type) -> tuple[type, dict[str, CppQualifier] | dict[str, str]]:
    """
    Extract content from Annotation, if present
    """
    t = get_origin(origin)
    # if t is None and get_args(origin):
    #     raise CppTypeError("Python types with no default mapping must be annotated with a type override")
    if t is Annotated:
        base, *extras = get_args(origin)
        assert len(extras) == 1, "one and only one annotation must be specified"
        # CppQualifier subclasses str so check this first
        if isinstance(extras[0], CppQualifier):
            return base, {"qualifier": extras[0]}
        if isinstance(extras[0], str):
            return base, {"override": extras[0]}
        raise TypeError(f"Unexpected extra for {base}: {extras[0]}({type(extras[0])})")
    return origin, {}


def translate_type(t: type) -> CppTypeTree:
    """
    Covert a python type to a string representing the C++ equivalent
    using the default mappings defined in default_type_mapping
    """

    base_type, extras = parse_annotation(t)
    return CppTypeTree(PyTypeTree(base_type), **extras)
