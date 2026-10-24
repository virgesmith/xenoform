import importlib
import importlib.util
import inspect
import os
import sys
import sysconfig
from collections import defaultdict
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from functools import lru_cache, wraps
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import numpy as np
from itrx import Itr
from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

from xenoform.config import get_config
from xenoform.cppmodule import FunctionSpec, ModuleSpec, ReturnValuePolicy
from xenoform.errors import AnnotationError, CompilationError
from xenoform.logger import get_logger
from xenoform.utils import deduplicate, format_cpp, get_function_scope, translate_function_signature

logger = get_logger()

_module_registry: dict[str, ModuleSpec] = defaultdict(ModuleSpec)


def _get_binary_path(module_dir: Path, module_name: str) -> Path:
    """The built extension, named by setuptools for this interpreter's ABI"""
    return module_dir / f"{module_name}{sysconfig.get_config_var('EXT_SUFFIX')}"


def _get_checksum_path(module_dir: Path, module_name: str) -> Path:
    """
    The hash of the source the binary was built from. Named after the binary, so each ABI (e.g. 3.14 and 3.14t,
    which share the module dir and its source) has its own and can't vouch for another's binary
    """
    return _get_binary_path(module_dir, module_name).with_suffix(".checksum")


def _read_checksum(module_dir: Path, module_name: str) -> str | None:
    # reading a file rather than loading the module (which would need a subprocess, since a loaded
    # extension module can't be unloaded or reloaded) keeps the up-to-date check cheap
    try:
        return _get_checksum_path(module_dir, module_name).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def _load_module(name: str, path: Path) -> ModuleType:
    """Load an extension module by path, so the extmodule root needn't be on sys.path"""
    if module := sys.modules.get(name):
        # a loaded extension module can't be reloaded, even after a rebuild
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        # defensive: a path with an extension module suffix always gets an ExtensionFileLoader
        raise ImportError(f"cannot load extension module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parse_macros(macro_list: list[str]) -> dict[str, str | None]:
    """Map ["DEF1", "DEF2=3"] to {"DEF1": None, "DEF2": "3"}"""
    return (
        Itr(macro_list)
        .map(lambda d: d.split("="))
        .map(lambda kv: (kv[0], kv[1] if len(kv) == 2 else None))
        .collect(dict)
    )


def _check_build_fetch_module_impl(
    module_name: str,
    module_spec: ModuleSpec,
) -> ModuleType:
    extmodule_root = get_config().extmodule_root

    ext_name = module_name + "_ext"
    qualified_name = f"{ext_name}.{module_name}"

    module_dir = extmodule_root / ext_name
    binary_path = _get_binary_path(module_dir, module_name)
    checksum_path = _get_checksum_path(module_dir, module_name)

    code, hashval = module_spec.make_source(module_name)

    # if a built module already exists, and matches the hash of the source code, just use it
    module_checksum = _read_checksum(module_dir, module_name) if binary_path.exists() else None

    # assume exists and up-to-date
    exists, outdated = True, False
    if not module_checksum:
        logger(f"module {qualified_name} not found")
        exists = False
    elif module_checksum != hashval:
        logger(f"module is outdated ({hashval})")
        outdated = True
    else:
        logger(f"module is up-to-date ({hashval})")

    if outdated or not exists:
        logger(f"(re)building module {qualified_name}")

        # invalidate first, so a checksum only ever exists for a completed build
        checksum_path.unlink(missing_ok=True)
        module_dir.mkdir(exist_ok=True, parents=True)

        # save the code with the hash embedded, formatted only now so an up-to-date check runs no subprocesses
        with (module_dir / "module.cpp").open("w") as fd:
            # can't use format as its full of { }
            fd.write(format_cpp(code.replace("__HASH__", hashval)))

        logger(f"wrote {module_dir}/module.cpp")

        ext_modules = [
            Pybind11Extension(
                module_name,
                ["module.cpp"],
                define_macros=list(_parse_macros(deduplicate(module_spec.define_macros)).items()),
                extra_compile_args=deduplicate(module_spec.extra_compile_args),
                extra_link_args=deduplicate(module_spec.extra_link_args),
                include_dirs=[np.get_include(), *deduplicate(module_spec.include_paths)],
                cxx_std=module_spec.cxx_std,
            )
        ]

        logger(f"building {qualified_name}...")
        cwd = Path.cwd()
        try:
            os.chdir(module_dir)
            # Redirect stdout to a log file (does not work in pytest)
            # Redirecting stderr doesnt work at all
            with Path("./build.log").open("w") as fd, redirect_stdout(fd), redirect_stderr(fd):
                setup(
                    name=ext_name,
                    ext_modules=ext_modules,
                    script_args=["build_ext", "--inplace"],
                    cmdclass={"build_ext": build_ext},
                )
        except SystemExit as e:
            raise CompilationError(str(e)) from e
        finally:
            os.chdir(cwd)
        checksum_path.write_text(hashval, encoding="utf-8")
        logger(f"built {qualified_name}")
    return _load_module(qualified_name, binary_path)


@lru_cache(maxsize=256)
def _get_module(module_name: str) -> ModuleType:
    module = _check_build_fetch_module_impl(module_name, _module_registry[module_name])
    logger(f"imported compiled module {module.__name__}")
    return module


def _check_annotations[**P, R](func: Callable[P, R]) -> None:
    """Ensures all args and return are typed"""
    sig = inspect.signature(func)

    missing_annotations = ", ".join(
        param for param, type_ in sig.parameters.items() if type_.annotation is inspect.Parameter.empty
    )
    if sig.return_annotation is inspect.Parameter.empty:
        missing_annotations += ", (return)"

    if missing_annotations:
        raise AnnotationError(f"Function {func.__name__} has missing annotations: {missing_annotations}")  # ty: ignore[unresolved-attribute]


@lru_cache(maxsize=256)
def _get_function(module_name: str, function_name: str) -> Callable[..., Any]:
    module = _get_module(module_name)
    logger(f"redirected {module_name}.{function_name[1:]} to compiled function {module.__name__}.{function_name}")
    return getattr(module, function_name)


def compile[**P, R](
    *,
    vectorise: bool = False,
    define_macros: list[str] | None = None,
    extra_includes: list[str] | None = None,
    extra_include_paths: list[str] | None = None,
    extra_compile_args: list[str] | None = None,
    extra_link_args: list[str] | None = None,
    return_value_policy: ReturnValuePolicy = ReturnValuePolicy.Automatic,
    cxx_std: int = 20,
    help: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory for compiling C/C++ function implementations into extension modules.

    Parameters:
        vectorise (bool, optional): If True, vectorizes the compiled function for array operations.
        define_macros: list[str] | None = None,
        extra_includes (list[str], optional): Additional header/inline files to include during compilation.
        extra_include_paths (list[str], optional): Additional paths search for headers.
        extra_compile_args (list[str], optional): Extra arguments to pass to the compiler.
        extra_link_args (list[str], optional): Extra arguments to pass to the linker.
        cxx_std (int, optional, default 20): C++ standard to compile
        help (str, optional): Docstring for the function

    Returns:
        Callable[..., Callable[..., Any]]: A function that when called, will return the compiled function.

    Debug logging is controlled globally by the presence of the `XENOFORM_VERBOSE` environment
    variable (any value enables it), not per-decorator.
    """

    def register_function[**P, R](func: Callable[P, R]) -> Callable[P, R]:
        """This registers the function, actual compilation is deferred"""
        extmodule_root = get_config().extmodule_root

        scope = get_function_scope(func)

        _check_annotations(func)

        sig, args, headers = translate_function_signature(func)
        module_name = f"{Path(inspect.getfile(func)).stem}"
        function_body = sig + " {" + (func.__doc__ or "") + "}"

        logger(f"registering {module_name}_ext.{module_name}.{func.__name__} (in {extmodule_root})")  # ty: ignore[unresolved-attribute]

        if vectorise:
            function_body = f"py::vectorize({function_body})"
            headers.append("<pybind11/numpy.h>")

        arg_defs = "".join(f", {kwarg}" for kwarg in args)

        # need to directly alter the original function's help...
        # for reasons unknown, copying the pybind11 function's docstr to the python stub on first use
        # (in _get_function) doesn't actually work
        # TODO try this:
        # > Modifying func.__doc__ directly can be an unexpected side effect for a decorator. While functional, it
        # > deviates from the common pattern of decorators modifying the returned wrapper function's attributes. If
        # > help is provided, test_help.py's assertion should also be adjusted to == docstr for exact match.
        if help:
            func.__doc__ = help

        # ...as well as adding the help to the ext module
        function_spec = FunctionSpec(
            name=func.__name__,  # ty: ignore[unresolved-attribute]
            body=function_body,
            arg_annotations=arg_defs,
            scope=scope,
            return_value_policy=return_value_policy,
            help=help,
        )

        _module_registry[module_name].add_function(
            function_spec,
            headers=headers + (extra_includes or []),
            include_paths=extra_include_paths or [],
            define_macros=define_macros or [],
            extra_compile_args=extra_compile_args or [],
            extra_link_args=extra_link_args or [],
            cxx_std=cxx_std,
        )

        @wraps(func)
        def call_function(*args: P.args, **kwargs: P.kwargs) -> R:
            """Compilation is deferred until here (and cached)"""
            cpp_fn = cast(Callable[P, R], _get_function(module_name, function_spec.qualified_cpp_name()))
            return cpp_fn(*args, **kwargs)

        return call_function

    return register_function
