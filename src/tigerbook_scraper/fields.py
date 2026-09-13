"""Field handling independent of the source's field names."""

import json
import re
from collections.abc import Iterable
from typing import Any

from .errors import ExtractionError
from .models import Fields


def field_key(section: str, label: str) -> str:
    # JSON Pointer escaping prevents collisions with literal separators in labels.
    def escape(value: str) -> str:
        return value.replace("~", "~0").replace("/", "~1")

    if not label.strip():
        raise ExtractionError("A profile value has no identifiable field label.")
    return "/".join(escape(part) for part in (section, label) if part.strip())


def from_pairs(pairs: Iterable[tuple[str, str, Any]]) -> Fields:
    grouped: dict[str, list[Any]] = {}
    for section, label, value in pairs:
        grouped.setdefault(field_key(section, label), []).append(value)
    if not grouped:
        raise ExtractionError("No recognized profile fields were found.")
    return {key: values[0] if len(values) == 1 else values for key, values in grouped.items()}


def from_mapping(value: Any) -> Fields:
    """Use only on the observed profile object, not arbitrary API envelopes."""
    if not isinstance(value, dict) or not value:
        raise ExtractionError("Expected a nonempty profile object.")
    if not all(isinstance(key, str) and key.strip() for key in value):
        raise ExtractionError("Profile keys must be nonempty strings.")
    # Validate before persistence; reject NaN/Infinity rather than corrupting the export.
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        raise ExtractionError("Profile contains values that cannot be serialized.") from None
    return dict(value)


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def needs_text_import(value: str) -> bool:
    return bool(
        value and (value.lstrip().startswith(("=", "+", "-", "@")) or re.fullmatch(r"0\d+", value))
    )
