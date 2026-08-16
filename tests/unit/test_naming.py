"""Tests for source<->target symbol naming and TS export extraction."""
from codeshift.adapters.typescript.symbols import extract_exports
from codeshift.utils.naming import build_symbol_map, snake_to_camel


def test_snake_to_camel():
    assert snake_to_camel("make_user") == "makeUser"
    assert snake_to_camel("slugify") == "slugify"
    assert snake_to_camel("to_json_string") == "toJsonString"


def test_extract_exports():
    code = (
        "export function makeUser() {}\n"
        "export const slugify = () => {}\n"
        "export class Foo {}\n"
        "function hidden() {}\n"
    )
    assert set(extract_exports(code)) == {"makeUser", "slugify", "Foo"}


def test_build_symbol_map_prefers_camelcase():
    assert build_symbol_map(["make_user", "slugify"], ["makeUser", "slugify"]) == {
        "make_user": "makeUser",
        "slugify": "slugify",
    }


def test_build_symbol_map_exact_fallback():
    assert build_symbol_map(["register"], ["register"]) == {"register": "register"}


def test_build_symbol_map_best_effort_when_missing():
    assert build_symbol_map(["make_user"], []) == {"make_user": "makeUser"}


def test_build_symbol_map_maps_a_method_one_segment_at_a_time():
    """The class is matched against the exports; the method can only be guessed,
    which is why the runtime drivers accept either spelling."""
    assert build_symbol_map(["Cart.add_item"], ["Cart"]) == {"Cart.add_item": "Cart.addItem"}


def test_build_symbol_map_leaves_the_construction_marker_alone():
    """camelCasing `__init__` would produce a name nothing answers to."""
    assert build_symbol_map(["User.__init__"], ["User"]) == {"User.__init__": "User.__init__"}
