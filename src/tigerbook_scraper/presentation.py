"""Spreadsheet presentation only; the raw export retains the original values."""

import re


def label(value):
    return value.replace("~1", "/").replace("~0", "~").replace("_", " ").strip()


def headings(keys):
    used = {"Profile ID", "Profile URL"}
    result = []
    for key in keys:
        title = " · ".join(label(part) for part in key.split("/"))
        candidate, number = title, 2
        while candidate in used:
            candidate = f"{title} ({number})"
            number += 1
        used.add(candidate)
        result.append(candidate)
    return ["Profile ID", "Profile URL", *result]


def column_order(key):
    # Display priority only, never an extraction allowlist.
    name = label(key.split("/")[-1]).casefold()
    return (0 if name in ("full name", "name") else 1, key.casefold(), key)


def readable_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            text = readable_value(item)
            if not text:
                continue
            title = label(key)
            lines.append(
                f"{title}:\n  " + text.replace("\n", "\n  ") if "\n" in text else f"{title}: {text}"
            )
        return "\n".join(lines)
    if isinstance(value, list):
        if any(isinstance(item, (dict, list)) for item in value):
            return "\n\n".join(
                f"Record {index}\n{text}"
                for index, item in enumerate(value, 1)
                if (text := readable_value(item))
            )
        return "\n".join(readable_value(item) for item in value if item is not None)
    return str(value)


def spreadsheet_value(value):
    text = readable_value(value)
    # The raw companion preserves exact text. Protect the display copy from
    # formula evaluation and common loss of leading zeroes on spreadsheet open.
    if text and (text.lstrip().startswith(("=", "+", "-", "@")) or re.fullmatch(r"0\d+", text)):
        return "'" + text
    return text
