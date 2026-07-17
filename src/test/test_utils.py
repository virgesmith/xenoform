import pytest

from xenoform.utils import _translate_value, group_headers


def test_translate_value() -> None:
    # bool must be handled before int since bool subclasses int
    assert _translate_value(True, "bool") == "true"
    assert _translate_value(False, "bool") == "false"
    # None maps to std::nullopt regardless of the optional type
    assert _translate_value(None, "std::optional<int>") == "std::nullopt"
    # numbers use repr, which is a valid C++ literal for these cases
    assert _translate_value(5, "int") == "5"
    assert _translate_value(1.5, "double") == "1.5"
    # plain string is quoted
    assert _translate_value("hi", "std::string") == '"hi"'
    # double-quote and backslash are escaped
    assert _translate_value('a"b\\c', "std::string") == '"a\\"b\\\\c"'
    # newline and tab escapes
    assert _translate_value("a\nb\tc", "std::string") == '"a\\nb\\tc"'
    # non-ASCII uses octal escapes of the UTF-8 bytes (é -> 0xc3 0xa9 -> \303\251)
    assert _translate_value("é", "std::string") == '"\\303\\251"'
    # empty containers become value-initialised instances of the C++ type
    assert _translate_value((), "std::tuple<>") == "std::tuple<>{}"
    assert _translate_value([], "std::vector<int>") == "std::vector<int>{}"
    # non-empty container cannot be translated
    with pytest.raises(TypeError):
        _translate_value([1, 2], "std::vector<int>")
    # unknown type cannot be translated
    with pytest.raises(TypeError):
        _translate_value(object(), "auto")


def test_group_headers_basic() -> None:
    headers = [
        "<vector>",
        '"local.h"',
        "<thirdparty.h>",
        "<string>",
        '"code.inl"',
        '"another_local.hpp"',
        "<anotherthirdparty.hpp>",
        "<pybind11/stl.h>",
        "<map>",
    ]
    result = group_headers(headers)
    # Expected order:
    # 1. inlined code
    # 2. "local.h", "another_local.h"
    # 3. <thirdparty.h>, <anotherthirdparty.h>
    # 4. <vector>, <string>, <map>
    expected = [
        ['"code.inl"'],
        ['"local.h"', '"another_local.hpp"'],
        ["<thirdparty.h>", "<anotherthirdparty.hpp>", "<pybind11/stl.h>", "<pybind11/pybind11.h>"],
        ["<vector>", "<string>", "<map>"],
    ]
    assert result == expected


def test_group_headers_only_local() -> None:
    headers = ['"foo.h"', '"bar.h"']
    assert group_headers(headers) == [[], ['"foo.h"', '"bar.h"'], ["<pybind11/pybind11.h>"], []]


def test_group_headers_only_thirdparty() -> None:
    headers = ["<lib.h>", "<otherlib.h>"]
    assert group_headers(headers) == [[], [], ["<lib.h>", "<otherlib.h>", "<pybind11/pybind11.h>"], []]


def test_group_headers_only_stdlib() -> None:
    headers = ["<vector>", "<string>"]
    assert group_headers(headers) == [[], [], ["<pybind11/pybind11.h>"], ["<vector>", "<string>"]]


def test_group_headers_other() -> None:
    headers = ["<vector>", '"custom.inl"']
    assert group_headers(headers) == [['"custom.inl"'], [], ["<pybind11/pybind11.h>"], ["<vector>"]]


def test_group_headers_empty() -> None:
    assert group_headers([]) == [[], [], ["<pybind11/pybind11.h>"], []]


def test_group_headers_mixed_with_spaces() -> None:
    headers = [
        "  <vector>  ",
        ' "local.h" ',
        "<thirdparty.h> ",
        "<string>",
        "other_header ",
    ]
    # Only '<string>' matches stdlib, '<thirdparty.h> ' matches thirdparty, '"local.h" ' matches local, others are "other"
    expected = [["other_header"], ['"local.h"'], ["<thirdparty.h>", "<pybind11/pybind11.h>"], ["<vector>", "<string>"]]
    assert group_headers(headers) == expected
