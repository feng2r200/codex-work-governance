"""YAML compatibility layer for cold-start controller execution.

The Work Governance controller must run before a project-local dependency
cache exists. PyYAML is preferred when available for reading broad YAML input,
but the public controller cannot require fetching it just to bootstrap hooks,
help, or layout recovery. Writes always use the conservative YAML subset
understood by the fallback reader: mappings, lists, nested mappings, simple
scalars, and single-line quoted strings.
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

_PY_YAML_DISABLED = os.environ.get("WORK_GOVERNANCE_DISABLE_PYYAML") == "1"
_pyyaml: ModuleType | None

if not _PY_YAML_DISABLED:
    try:  # pragma: no cover - exercised by repository integration tests.
        import yaml as _pyyaml_module
    except ImportError:  # pragma: no cover - depends on the bootstrap environment.
        _pyyaml = None
    else:
        _pyyaml = _pyyaml_module
else:  # pragma: no cover - used by fallback-specific tests.
    _pyyaml = None


class _FallbackYAMLError(ValueError):
    """Raised when the fallback parser cannot safely read YAML."""


YAMLError: type[Exception]
if _pyyaml is not None:
    _pyyaml_present: Any = _pyyaml
    YAMLError = _pyyaml_present.YAMLError

    def safe_load(stream: str | bytes) -> Any:
        """Load YAML using PyYAML when the dependency is present."""
        return _pyyaml_present.safe_load(stream)

else:
    YAMLError = _FallbackYAMLError

    @dataclass(frozen=True)
    class _Line:
        """One significant YAML line."""

        indent: int
        text: str

    _INT_RE = re.compile(r"^[+-]?\d+$")
    _FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")

    def safe_load(stream: str | bytes) -> Any:
        """Load the controller's generated YAML subset without external wheels."""
        text = stream.decode("utf-8") if isinstance(stream, bytes) else stream
        stripped = text.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        lines = _significant_lines(text)
        if not lines:
            return None
        value, position = _parse_block(lines, 0, lines[0].indent)
        if position != len(lines):
            raise YAMLError("unexpected trailing YAML content")
        return value

    def _significant_lines(text: str) -> list[_Line]:
        lines: list[_Line] = []
        for raw_line in text.splitlines():
            if raw_line.strip() in {"---", "..."}:
                continue
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip(" "))]:
                raise YAMLError("tabs are not supported for indentation")
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            lines.append(_Line(indent=indent, text=raw_line[indent:].rstrip()))
        return lines

    def _parse_block(lines: Sequence[_Line], position: int, indent: int) -> tuple[Any, int]:
        if position >= len(lines):
            return None, position
        line = lines[position]
        if line.indent < indent:
            return None, position
        if line.indent != indent:
            raise YAMLError("unexpected indentation")
        if line.text == "-" or line.text.startswith("- "):
            return _parse_sequence(lines, position, indent)
        return _parse_mapping(lines, position, indent)

    def _parse_mapping(
        lines: Sequence[_Line],
        position: int,
        indent: int,
    ) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while position < len(lines):
            line = lines[position]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise YAMLError("unexpected mapping indentation")
            if line.text == "-" or line.text.startswith("- "):
                break
            key, raw_value = _split_key_value(line.text)
            position += 1
            if raw_value == "":
                value, position = _parse_nested_value(lines, position, indent)
            else:
                value, position = _parse_scalar_with_continuations(
                    lines,
                    position,
                    raw_value,
                    scalar_indent=indent,
                )
            result[key] = value
        return result, position

    def _parse_sequence(
        lines: Sequence[_Line],
        position: int,
        indent: int,
    ) -> tuple[list[Any], int]:
        result: list[Any] = []
        while position < len(lines):
            line = lines[position]
            if line.indent < indent:
                break
            if line.indent != indent or (line.text != "-" and not line.text.startswith("- ")):
                break
            content = "" if line.text == "-" else line.text[2:].strip()
            position += 1
            if content == "":
                value, position = _parse_nested_value(lines, position, indent)
                result.append(value)
                continue
            split = _maybe_split_key_value(content)
            if split is not None:
                key, raw_value = split
                mapping_indent = indent + 2
                item: dict[str, Any] = {}
                if raw_value == "":
                    value, position = _parse_nested_value(lines, position, mapping_indent)
                else:
                    value, position = _parse_scalar_with_continuations(
                        lines,
                        position,
                        raw_value,
                        scalar_indent=mapping_indent,
                    )
                item[key] = value
                if position < len(lines) and lines[position].indent == mapping_indent:
                    extra, position = _parse_mapping(lines, position, mapping_indent)
                    item.update(extra)
                result.append(item)
                continue
            value, position = _parse_scalar_with_continuations(
                lines,
                position,
                content,
                scalar_indent=indent,
            )
            result.append(value)
        return result, position

    def _parse_nested_value(
        lines: Sequence[_Line],
        position: int,
        parent_indent: int,
    ) -> tuple[Any, int]:
        if position >= len(lines):
            return None, position
        next_line = lines[position]
        if next_line.indent < parent_indent:
            return None, position
        if next_line.indent == parent_indent and (
            next_line.text == "-" or next_line.text.startswith("- ")
        ):
            return _parse_sequence(lines, position, parent_indent)
        if next_line.indent <= parent_indent:
            return None, position
        return _parse_block(lines, position, next_line.indent)

    def _parse_scalar_with_continuations(
        lines: Sequence[_Line],
        position: int,
        raw_value: str,
        *,
        scalar_indent: int,
    ) -> tuple[Any, int]:
        parts = [raw_value.strip()]
        open_quote = _open_multiline_quote(parts)
        while position < len(lines):
            line = lines[position]
            if line.indent <= scalar_indent:
                break
            parts.append(line.text.strip())
            position += 1
            open_quote = _open_multiline_quote(parts)
        if open_quote is not None:
            raise YAMLError("unterminated quoted scalar")
        if parts and parts[0].startswith('"'):
            return _parse_double_quoted_scalar_parts(parts), position
        return _parse_scalar(" ".join(part for part in parts if part)), position

    def _open_multiline_quote(parts: Sequence[str]) -> str | None:
        text = " ".join(part.strip() for part in parts if part.strip())
        if not text or text[0] not in {"'", '"'}:
            return None
        quote = text[0]
        if _quoted_scalar_is_closed(text, quote):
            return None
        return quote

    def _quoted_scalar_is_closed(text: str, quote: str) -> bool:
        escaped = False
        index = 1
        while index < len(text):
            character = text[index]
            if quote == '"' and escaped:
                escaped = False
                index += 1
                continue
            if quote == '"' and character == "\\":
                escaped = True
                index += 1
                continue
            if character == quote:
                if quote == "'" and index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                return text[index + 1 :].strip() == ""
            index += 1
        return False

    def _split_key_value(text: str) -> tuple[str, str]:
        split = _maybe_split_key_value(text)
        if split is None:
            raise YAMLError(f"expected key/value mapping line: {text}")
        return split

    def _maybe_split_key_value(text: str) -> tuple[str, str] | None:
        quote: str | None = None
        escaped = False
        for index, character in enumerate(text):
            if escaped:
                escaped = False
                continue
            if quote == '"' and character == "\\":
                escaped = True
                continue
            if character in {"'", '"'}:
                if quote is None:
                    quote = character
                elif quote == character:
                    quote = None
                continue
            if character == ":" and quote is None:
                if index + 1 < len(text) and not text[index + 1].isspace():
                    continue
                key = text[:index].strip()
                if not key or " " in key:
                    return None
                return _parse_key(key), text[index + 1 :].strip()
        return None

    def _parse_key(text: str) -> str:
        if (text.startswith("'") and text.endswith("'")) or (
            text.startswith('"') and text.endswith('"')
        ):
            value = _parse_scalar(text)
            if not isinstance(value, str):
                raise YAMLError("mapping key must be a string")
            return value
        return text

    def _parse_scalar(text: str) -> Any:
        value = text.strip()
        if value == "":
            return ""
        lowered = value.lower()
        if lowered in {"null", "~"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1].replace("''", "'")
        if value.startswith('"') and value.endswith('"'):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise YAMLError(str(exc)) from exc
        if value.startswith(("[", "{")) and value.endswith(("]", "}")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(value)
                except (SyntaxError, ValueError) as exc:
                    raise YAMLError(str(exc)) from exc
        if _INT_RE.fullmatch(value):
            return int(value)
        if _FLOAT_RE.fullmatch(value) and any(marker in value for marker in ".eE"):
            return float(value)
        return value

    def _parse_double_quoted_scalar_parts(parts: Sequence[str]) -> str:
        inner_parts = list(parts)
        if not inner_parts[0].startswith('"') or not inner_parts[-1].endswith('"'):
            raise YAMLError("invalid quoted scalar")
        inner_parts[0] = inner_parts[0][1:]
        inner_parts[-1] = inner_parts[-1][:-1]
        text = inner_parts[0]
        for part in inner_parts[1:]:
            text = (
                text[:-1] + part
                if _has_unescaped_trailing_backslash(text)
                else f"{text} {part}"
            )
        try:
            value = json.loads(f'"{_normalize_yaml_double_quoted_escapes(text)}"')
        except (json.JSONDecodeError, ValueError) as exc:
            raise YAMLError(str(exc)) from exc
        if not isinstance(value, str):
            raise YAMLError("quoted scalar must decode to a string")
        return value

    def _has_unescaped_trailing_backslash(text: str) -> bool:
        count = 0
        index = len(text) - 1
        while index >= 0 and text[index] == "\\":
            count += 1
            index -= 1
        return count % 2 == 1

    def _normalize_yaml_double_quoted_escapes(text: str) -> str:
        result: list[str] = []
        index = 0
        yaml_escapes = {
            "0": "\u0000",
            "a": "\u0007",
            "v": "\u000b",
            "e": "\u001b",
            " ": " ",
            "_": "\u00a0",
            "N": "\u0085",
            "L": "\u2028",
            "P": "\u2029",
        }
        json_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
        while index < len(text):
            character = text[index]
            if character != "\\":
                result.append(character)
                index += 1
                continue
            if index + 1 >= len(text):
                raise YAMLError("unterminated escape sequence")
            escaped = text[index + 1]
            if escaped in yaml_escapes:
                result.append(json.dumps(yaml_escapes[escaped])[1:-1])
                index += 2
                continue
            if escaped in json_escapes:
                result.append("\\" + escaped)
                index += 2
                continue
            if escaped in {"x", "u", "U"}:
                width = {"x": 2, "u": 4, "U": 8}[escaped]
                raw = text[index + 2 : index + 2 + width]
                if len(raw) != width or re.fullmatch(r"[0-9A-Fa-f]+", raw) is None:
                    raise YAMLError("invalid unicode escape")
                result.append(json.dumps(chr(int(raw, 16)))[1:-1])
                index += 2 + width
                continue
            raise YAMLError(f"unsupported escape sequence: \\{escaped}")
        return "".join(result)


_DUMP_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9_./@:+-][A-Za-z0-9_./@:+ -]*$")
_DUMP_INT_RE = re.compile(r"^[+-]?[0-9][0-9_]*$")
_DUMP_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:[0-9][0-9_]*)?\.[0-9_]*|[0-9][0-9_]*)(?:[eE][+-]?[0-9_]+)?$"
)
_DUMP_YAML_SPECIAL_FLOAT_RE = re.compile(r"^[+-]?\.(?:inf|nan)$", re.IGNORECASE)
_DUMP_YAML_BASE_INT_RE = re.compile(
    r"^[+-]?(?:0b[0-1_]+|0o[0-7_]+|0x[0-9A-Fa-f_]+|0[0-7_]+)$"
)
_DUMP_YAML_SEXAGESIMAL_RE = re.compile(
    r"^[+-]?[0-9][0-9_]*(?::[0-5]?[0-9])+(?:\.[0-9_]*)?$"
)
_DUMP_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[Tt\s]\d{2}:\d{2}:\d{2})")
_DUMP_YAML_IMPLICIT_STRINGS = {
    "",
    "~",
    "false",
    "no",
    "null",
    "off",
    "on",
    "true",
    "yes",
}


def safe_dump(
    data: object,
    *,
    sort_keys: bool = True,
    allow_unicode: bool = True,
) -> str:
    """Dump deterministic YAML that the cold-start fallback can always read."""
    lines = _dump_compatible_value(
        data,
        indent=0,
        sort_keys=sort_keys,
        allow_unicode=allow_unicode,
    )
    return "\n".join(lines) + "\n"


def _dump_compatible_value(
    value: object,
    *,
    indent: int,
    sort_keys: bool,
    allow_unicode: bool,
) -> list[str]:
    prefix = " " * indent
    if isinstance(value, Mapping):
        if not value:
            return [prefix + "{}"]
        lines: list[str] = []
        items: Iterable[tuple[object, object]]
        items = value.items()
        if sort_keys:
            items = sorted(items, key=lambda item: str(item[0]))
        for raw_key, item_value in items:
            key = _dump_compatible_key(raw_key)
            inline = _dump_compatible_empty_collection(item_value)
            if inline is not None:
                lines.append(f"{prefix}{key}: {inline}")
            elif _dump_compatible_is_collection(item_value):
                lines.append(f"{prefix}{key}:")
                lines.extend(
                    _dump_compatible_value(
                        item_value,
                        indent=indent + 2,
                        sort_keys=sort_keys,
                        allow_unicode=allow_unicode,
                    )
                )
            else:
                lines.append(
                    f"{prefix}{key}: {_dump_compatible_scalar(item_value, allow_unicode)}"
                )
        return lines
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return [prefix + "[]"]
        lines = []
        for item in value:
            inline = _dump_compatible_empty_collection(item)
            if inline is not None:
                lines.append(f"{prefix}- {inline}")
            elif _dump_compatible_is_collection(item):
                lines.append(prefix + "-")
                lines.extend(
                    _dump_compatible_value(
                        item,
                        indent=indent + 2,
                        sort_keys=sort_keys,
                        allow_unicode=allow_unicode,
                    )
                )
            else:
                lines.append(f"{prefix}- {_dump_compatible_scalar(item, allow_unicode)}")
        return lines
    return [prefix + _dump_compatible_scalar(value, allow_unicode)]


def _dump_compatible_is_collection(value: object) -> bool:
    return isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _dump_compatible_empty_collection(value: object) -> str | None:
    if isinstance(value, Mapping) and not value:
        return "{}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and not value:
        return "[]"
    return None


def _dump_compatible_key(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        return value
    return _dump_compatible_scalar(str(value), allow_unicode=False)


def _dump_compatible_scalar(value: object, allow_unicode: bool) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str) and _dump_plain_scalar_is_safe(value):
        return value
    text = str(value)
    ensure_ascii = not allow_unicode or any(character in text for character in "\u0085\u2028\u2029")
    return json.dumps(text, ensure_ascii=ensure_ascii)


def _dump_plain_scalar_is_safe(value: str) -> bool:
    if value != value.strip():
        return False
    if value.startswith(("-", "@")):
        return False
    if _DUMP_PLAIN_SCALAR_RE.fullmatch(value) is None:
        return False
    if re.search(r":(?:\s|$)", value) is not None:
        return False
    lowered = value.lower()
    if lowered in _DUMP_YAML_IMPLICIT_STRINGS:
        return False
    if _DUMP_INT_RE.fullmatch(value) is not None:
        return False
    if _DUMP_FLOAT_RE.fullmatch(value) is not None:
        return False
    if _DUMP_YAML_SPECIAL_FLOAT_RE.fullmatch(value) is not None:
        return False
    if _DUMP_YAML_BASE_INT_RE.fullmatch(value) is not None:
        return False
    if _DUMP_YAML_SEXAGESIMAL_RE.fullmatch(value) is not None:
        return False
    return _DUMP_TIMESTAMP_RE.match(value) is None
