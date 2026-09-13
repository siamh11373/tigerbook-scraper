"""Offline feasibility hints. Decoded objects are private and never safe to log."""

import json
import re

from .html_probe import Document

_ASSIGNMENT = re.compile(
    r"(?:\b(?:var|let|const)\s+)?[\w$]+(?:\.[\w$]+|\[['\"][\w$]+['\"]\])*\s*=(?!=)\s*"
)
_PARSE = re.compile(r"\bJSON\s*\.\s*parse\s*\(\s*")
_HINTS = {
    "batch": r"\b(?:batch|batchGet|batchRead|bulk|bulkFetch)\b",
    "related": r"\b(?:include|includes|includeRelated|expand|populate)\b",
    "pagination": r"\b(?:cursor|nextCursor|pageSize|hasNextPage)\b",
    "graphql": r"\b(?:graphql|operationName)\b",
}


def _literal(source, start):
    """Decode a JS quoted string subset without evaluating JavaScript."""
    if start >= len(source) or source[start] not in "\"'":
        raise ValueError("Expected string")
    quote = source[start]
    chars = []
    index = start + 1
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
    while index < len(source):
        char = source[index]
        index += 1
        if char == quote:
            value = "".join(chars)
            return value.encode("utf-16", "surrogatepass").decode("utf-16"), index
        if char in "\r\n":
            raise ValueError("Unescaped newline")
        if char != "\\":
            chars.append(char)
            continue
        if index >= len(source):
            break
        char = source[index]
        index += 1
        if char in "ux":
            width = 4 if char == "u" else 2
            digits = source[index : index + width]
            if len(digits) != width or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                raise ValueError("Unsupported escape")
            chars.append(chr(int(digits, 16)))
            index += width
        elif char in "\\\"'/":
            chars.append(char)
        elif char in escapes:
            chars.append(escapes[char])
        else:
            raise ValueError("Unsupported escape")
    raise ValueError("Unterminated string")


def _objects(source):
    decoder = json.JSONDecoder()
    candidates = []
    try:
        value = json.loads(source)
        if isinstance(value, (dict, list)):
            candidates.append(value)
    except (ValueError, RecursionError):
        pass
    for match in _ASSIGNMENT.finditer(source):
        try:
            value, end = decoder.raw_decode(source, match.end())
            # Do not interpret an expression as an assigned JSON value.
            tail = source[end:].lstrip()
            if isinstance(value, (dict, list)) and (not tail or tail.startswith(";")):
                candidates.append(value)
        except (ValueError, RecursionError):
            continue
    for match in _PARSE.finditer(source):
        try:
            literal, end = _literal(source, match.end())
            if not source[end:].lstrip().startswith(")"):
                continue
            value = json.loads(literal)
            if isinstance(value, (dict, list)):
                candidates.append(value)
        except (ValueError, UnicodeError, RecursionError):
            continue
    return candidates


def inspect_script(source):
    """Return counts only. Keywords are hints, never verified interfaces."""
    return {
        "source_characters": len(source),
        "keyword_counts": {
            label: len(re.findall(pattern, source, re.IGNORECASE))
            for label, pattern in _HINTS.items()
        },
        "interfaces_confirmed": False,
    }


def inspect_embedded(html):
    """Return private candidate objects plus a separately safe count summary.

    This recognizes only a conservative subset of JS. Absence of candidates
    does not prove absence of embedded data, and presence does not prove fidelity.
    Do not serialize or print the objects in public logs or artifacts.
    """
    document = Document()
    document.feed(html)
    objects = []
    counts = dict.fromkeys(_HINTS, 0)
    for source in document.scripts:
        objects.extend(_objects(source))
        for key, count in inspect_script(source)["keyword_counts"].items():
            counts[key] += count
    return {
        "objects": objects,
        "summary": {
            "script_count": len(document.scripts),
            "decoded_candidate_count": len(objects),
            "keyword_counts": counts,
            "full_record_verified": False,
            "interfaces_confirmed": False,
        },
    }
