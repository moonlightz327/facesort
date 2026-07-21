import pytest

from facesort.core.templates import (
    TemplateError,
    render,
    sanitize_component,
    template_fields,
    validate_template,
)


def test_render_basic_vars():
    out = render("{person}/{orig_name}{ext}", person="张三", orig_name="IMG_001", ext=".jpg")
    assert out == "张三/IMG_001.jpg"


def test_render_index_format_spec():
    assert render("{index:03d}", index=7) == "007"
    assert render("{person}_{index:04d}{ext}", person="李四", index=12, ext=".png") == "李四_0012.png"


def test_render_similarity_default_two_decimals():
    assert render("{similarity}", similarity=0.61834) == "0.62"
    assert render("{similarity:.3f}", similarity=0.61834) == "0.618"


def test_illegal_path_chars_replaced_in_values():
    # Person name with path-illegal characters becomes safe (edge case #12)
    assert render("{person}", person="张/三") == "张_三"
    assert render("{person}", person='a\\b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"


def test_literal_slash_in_template_kept():
    # Slashes typed in the template itself mean nested folders and are kept
    assert render("{date}/{person}", date="2026-07-17", person="张三") == "2026-07-17/张三"


def test_sanitize_component():
    assert sanitize_component("a/b") == "a_b"
    assert sanitize_component("normal-name_1") == "normal-name_1"


def test_unknown_variable_raises():
    with pytest.raises(TemplateError):
        render("{nope}", person="x")
    with pytest.raises(TemplateError):
        validate_template("{person}/{bogus}")


def test_template_fields():
    assert template_fields("{person}_{index:03d}{ext}") == {"person", "index", "ext"}
    assert template_fields("no vars") == set()


def test_persons_and_datetime_vars():
    out = render("{persons}@{datetime}", persons="张三+李四", datetime="2026-07-17_10-00-00")
    assert out == "张三+李四@2026-07-17_10-00-00"
