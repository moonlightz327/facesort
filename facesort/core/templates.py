"""Naming template parsing & rendering ({person}, {index:03d}, ...)."""

from __future__ import annotations

import re
import string
from typing import Any

# Characters illegal in path components (macOS/Windows superset) + control chars.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

KNOWN_VARS = {
    "person", "persons", "date", "datetime",
    "orig_name", "ext", "index", "similarity",
}


class TemplateError(Exception):
    pass


def sanitize_component(value: str) -> str:
    """Replace path-illegal characters with '_' (edge case #12)."""
    return _ILLEGAL.sub("_", value)


class SimilarityValue(float):
    """Float that formats as .2f by default so a plain {similarity} looks sane."""

    def __format__(self, spec: str) -> str:
        return format(float(self), spec or ".2f")

    def __str__(self) -> str:
        return self.__format__("")


class _SanitizingFormatter(string.Formatter):
    """Sanitizes every substituted value; literal template text is kept as-is
    (so a folder template may contain '/' for nesting, but a person named
    'a/b' becomes 'a_b')."""

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        if isinstance(key, str):
            if key not in kwargs:
                raise TemplateError(f"模板变量未知: {{{key}}}，可用变量: {sorted(KNOWN_VARS)}")
            return kwargs[key]
        raise TemplateError("模板不支持位置参数，如 {0}")

    def format_field(self, value: Any, format_spec: str) -> str:
        try:
            out = format(value, format_spec)
        except (ValueError, TypeError) as e:
            raise TemplateError(f"模板格式化失败 ({value!r}:{format_spec}): {e}") from e
        return sanitize_component(out)


_formatter = _SanitizingFormatter()


def template_fields(template: str) -> set[str]:
    """Names of variables referenced by a template."""
    try:
        return {
            field.split(".")[0].split("[")[0]
            for _, field, _, _ in _formatter.parse(template)
            if field
        }
    except ValueError as e:
        raise TemplateError(f"模板语法错误 '{template}': {e}") from e


def validate_template(template: str) -> None:
    unknown = template_fields(template) - KNOWN_VARS
    if unknown:
        raise TemplateError(
            f"模板 '{template}' 含未知变量: {sorted(unknown)}，可用变量: {sorted(KNOWN_VARS)}"
        )


def render(template: str, **variables: Any) -> str:
    """Render a template. Substituted values are sanitized for path safety."""
    if "similarity" in variables and not isinstance(variables["similarity"], SimilarityValue):
        sim = variables["similarity"]
        variables["similarity"] = SimilarityValue(sim if sim is not None else 0.0)
    try:
        return _formatter.vformat(template, (), variables)
    except (KeyError, IndexError) as e:
        raise TemplateError(f"模板渲染失败 '{template}': {e}") from e
