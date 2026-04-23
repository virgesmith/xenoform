from typing import Self

import pytest

from xenoform import compile
from xenoform.utils import get_function_scope

from .other_module import Base, ClassA


class ClassB(Base):
    X: str = "B"

    def __init__(self) -> None:
        self.x = 2

    @compile()
    def method(self: Self) -> int:  # ty: ignore[empty-body]
        """
        // extract instance variable
        return self.attr("x").cast<int>();
        """

    @staticmethod
    @compile()
    def static_method(i: int) -> int:  # ty: ignore[empty-body]
        """
        return i + 1000;
        """

    @classmethod
    @compile()
    def class_method(cls: type) -> str:  # ty: ignore[empty-body]
        """
        // extract X from cls arg
        auto val = cls.attr("X").cast<std::string>();
        return val;
        """


class ClassC(Base):
    X: str = "C"

    @compile()
    def method(self: Self) -> int:  # ty: ignore[empty-body]
        """
        return 3;
        """

    @classmethod
    @compile()
    def class_method(cls: type) -> str:  # ty: ignore[empty-body]
        """
        // extract X from cls arg
        auto val = cls.attr("X").cast<std::string>();
        return val;
        """


def test_function_scope() -> None:
    assert get_function_scope(ClassA.method) == ("ClassA",)


def test_method() -> None:
    a = ClassA()
    b = ClassB()
    c = ClassC()

    def f(obj: Base) -> int:
        return obj.method()

    # test scope resolution works for instance methods
    assert a.method() == f(a) == 1
    assert b.method() == f(b) == 2
    assert c.method() == f(c) == 3


def test_method_incorrect_usage() -> None:
    with pytest.raises(TypeError):
        ClassA.method()  # ty: ignore[call-arg]
    # C++ impl should raise same error type as python
    with pytest.raises(TypeError):
        ClassB.method()  # ty: ignore[call-arg]


def test_class_method() -> None:
    a = ClassA()
    b = ClassB()
    c = ClassC()

    # test scope resolution works for class methods
    assert a.class_method() == ClassA.class_method() == "A"
    assert b.class_method() == ClassB.class_method() == "B"
    assert c.class_method() == ClassC.class_method() == "C"


def test_static_method() -> None:
    b = ClassB()
    with pytest.raises(AttributeError):
        ClassA.static_method(6)  # ty: ignore[attr-defined]
    assert ClassB.static_method(6) == b.static_method(6) == 1006
