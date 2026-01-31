from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext_modules = [
    Pybind11Extension(
        "_xenoform_test_ext",
        ["src/module.cpp"],
        include_dirs=["./include"],
        depends=["setup.py", "./include/module.h"],
        cxx_std=20,
    ),
]

setup(
    name="xenoform-test-ext",
    packages=["xenoform_test_ext"],
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
)
