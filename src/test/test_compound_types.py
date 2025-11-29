from typing import Annotated

from xenoform import compile
from xenoform.extension_types import CppQualifier, translate_type


def test_translate_compound_types() -> None:
    assert str(translate_type(int | float)) == "std::variant<int, double>"  # type: ignore[arg-type]
    assert str(translate_type(int | None)) == "std::optional<int>"  # type: ignore[arg-type]
    assert str(translate_type(Annotated[int | float, "double"])) == "double"  # type: ignore[arg-type]
    assert str(translate_type(Annotated[int | None, "py::object"])) == "py::object"  # type: ignore[arg-type]
    assert str(translate_type(int | float | None)) == "std::optional<std::variant<int, double>>"  # type: ignore[arg-type]
    assert (
        str(translate_type(Annotated[int | float | None, CppQualifier.CRef]))  # type: ignore[arg-type]
        == "const std::optional<std::variant<int, double>>&"
    )


@compile()
def union_type(x: Annotated[int | str, CppQualifier.CRef]) -> str:  # type: ignore[empty-body]
    """
    return std::holds_alternative<int>(x) ? std::to_string(std::get<int>(x)) : std::get<std::string>(x);

    """


def test_union_type() -> None:
    assert union_type(1) == "1"
    assert union_type("42") == "42"


@compile()
def optional_type(x: int | None) -> int:  # type: ignore[empty-body]
    """
    return x ? x.value() : 42;
    """


def test_optional_type() -> None:
    assert optional_type(1) == 1
    assert optional_type(None) == 42


@compile()
def compound_type(x: int | float | None) -> str:  # type: ignore[empty-body]
    """
    if (x) {
        if (std::holds_alternative<int>(x.value())) {
            return "int";
        }
        return "float";
    }
    return "empty";
    """


def test_compound_type() -> None:
    assert compound_type(1) == "int"
    assert compound_type(1.0) == "float"
    assert compound_type(None) == "empty"


if __name__ == "__main__":
    test_translate_compound_types()
    test_union_type()
    test_optional_type()
    test_compound_type()
