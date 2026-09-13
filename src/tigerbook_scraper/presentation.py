"""Spreadsheet presentation only; the raw export retains the original values."""

import re
from collections import OrderedDict

KNOWN_FIELDS = (
    "Location",
    "Cluster",
    "Full Name",
    "Primary Affiliation",
    "Primary Class/Degree Year",
    "Preferred PAA",
    "Affiliation(s)",
    "Class/Degree Year(s) of Affiliations",
    "Regions",
    "Affinity Groups",
    "Student Activities",
    "Nickname",
    "Institutional Suffix",
    "Prefix",
    "Family Name (if different from current name)",
    "Volunteer Activity 1",
    "Volunteer Activity 2",
    "Volunteer Activity 3",
    "Volunteer Activity 4",
    "Marital Status",
    "Job Title",
    "Employer",
    "Employment Date",
    "Field/Specialty",
    "Position Level (Types of Positions)",
    "Work, Board, or Military",
    "Educational Institution",
    "Education Date",
    "Degree Year",
    "Degree",
    "Major",
    "Academic Level",
    "Social Media Links",
    "Emails",
    "Personal Mobile",
    "Address",
    "Alumni Communities",
    "Community Location",
    "Community Member Count",
)

TECHNICAL_RECORD_KEYS = {"id", "main", "user_editable", "privacy"}


def normalized(value):
    return " ".join(label(value).split()).casefold()


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


def present_entity(value):
    if isinstance(value, dict) and value.get("name"):
        return readable_value(value["name"])
    return readable_value(value)


def record_lines(records, getter):
    lines = []
    for number, record in enumerate(records or (), 1):
        if not isinstance(record, dict):
            continue
        text = readable_value(getter(record))
        if text:
            lines.append(f"Record {number}: {text.replace(chr(10), '; ')}")
    return "\n".join(lines)


def record_date(record):
    start, end = readable_value(record.get("from")), readable_value(record.get("to"))
    if start and end:
        return f"{start} to {end}"
    return start or end


def dynamic_record_value(record, name):
    values = record.get("dynamic_attributes")
    if not isinstance(values, dict):
        return None
    wanted = normalized(name)
    return next((value for key, value in values.items() if normalized(key) == wanted), None)


def nested_record_keys(records, container):
    keys = set()
    for record in records:
        value = record.get(container) if isinstance(record, dict) else None
        if isinstance(value, dict):
            keys.update(value)
    return keys


def nested_record_value(record, container, key):
    value = record.get(container)
    return value.get(key) if isinstance(value, dict) else None


def grouped_fields(fields, predicate):
    lines = []
    for key, value in fields.items():
        if not predicate(normalized(key.split("/")[-1]), key):
            continue
        text = readable_value(value)
        if text:
            lines.append(f"{label(key.split('/')[-1])}: {text.replace(chr(10), '; ')}")
    return "\n".join(lines)


def readable_fields(fields):
    """Return the stable known columns, then every other dynamically found field."""
    result = OrderedDict((name, "") for name in KNOWN_FIELDS)
    consumed = set()

    direct = {normalized(key.split("/")[-1]): (key, value) for key, value in fields.items()}
    for name in KNOWN_FIELDS:
        match = direct.get(normalized(name))
        if match:
            key, value = match
            result[name] = readable_value(value)
            consumed.add(key)

    experience = fields.get("Experience")
    if isinstance(experience, list):
        consumed.add("Experience")
        result["Job Title"] = record_lines(experience, lambda row: row.get("position"))
        result["Employer"] = record_lines(
            experience, lambda row: present_entity(row.get("company"))
        )
        result["Employment Date"] = record_lines(experience, record_date)
        for name in (
            "Field/Specialty",
            "Position Level (Types of Positions)",
            "Work, Board, or Military",
        ):
            result[name] = record_lines(
                experience, lambda row, name=name: dynamic_record_value(row, name)
            )
        known_dynamic = {normalized(name) for name in KNOWN_FIELDS}
        native = set().union(*(row.keys() for row in experience if isinstance(row, dict)))
        for key in sorted(
            native
            - TECHNICAL_RECORD_KEYS
            - {"position", "company", "from", "to", "dynamic_attributes"}
        ):
            result[f"Experience · {label(key)}"] = record_lines(
                experience, lambda row, key=key: row.get(key)
            )
        dynamic = set()
        for row in experience:
            if isinstance(row, dict) and isinstance(row.get("dynamic_attributes"), dict):
                dynamic.update(row["dynamic_attributes"])
        for name in sorted(dynamic, key=normalized):
            if normalized(name) not in known_dynamic:
                result[f"Experience · {label(name)}"] = record_lines(
                    experience, lambda row, name=name: dynamic_record_value(row, name)
                )
        for key in sorted(nested_record_keys(experience, "company") - {"id", "name"}):
            result[f"Experience · Employer · {label(key)}"] = record_lines(
                experience,
                lambda row, key=key: nested_record_value(row, "company", key),
            )

    education = fields.get("Education")
    if isinstance(education, list):
        consumed.add("Education")
        result["Educational Institution"] = record_lines(
            education, lambda row: present_entity(row.get("school"))
        )
        result["Education Date"] = record_lines(education, record_date)
        for name in ("Degree Year", "Degree", "Major", "Academic Level"):
            result[name] = record_lines(
                education,
                lambda row, name=name: (
                    dynamic_record_value(row, name)
                    or row.get({"Degree": "degree", "Major": "field_of_study"}.get(name, ""))
                ),
            )
        known_dynamic = {normalized(name) for name in KNOWN_FIELDS}
        native = set().union(*(row.keys() for row in education if isinstance(row, dict)))
        for key in sorted(
            native
            - TECHNICAL_RECORD_KEYS
            - {"school", "from", "to", "degree", "field_of_study", "dynamic_attributes"}
        ):
            result[f"Education · {label(key)}"] = record_lines(
                education, lambda row, key=key: row.get(key)
            )
        dynamic = set()
        for row in education:
            if isinstance(row, dict) and isinstance(row.get("dynamic_attributes"), dict):
                dynamic.update(row["dynamic_attributes"])
        for name in sorted(dynamic, key=normalized):
            if normalized(name) not in known_dynamic:
                result[f"Education · {label(name)}"] = record_lines(
                    education, lambda row, name=name: dynamic_record_value(row, name)
                )
        for key in sorted(nested_record_keys(education, "school") - {"id", "name"}):
            result[f"Education · Educational Institution · {label(key)}"] = record_lines(
                education,
                lambda row, key=key: nested_record_value(row, "school", key),
            )

    result["Social Media Links"] = grouped_fields(
        fields, lambda name, key: "social media" in normalized(key) or name.endswith(" profile url")
    )
    result["Emails"] = grouped_fields(fields, lambda name, _key: "email" in name)
    result["Address"] = grouped_fields(fields, lambda name, _key: "address" in name)
    for key in fields:
        whole = normalized(key)
        leaf = normalized(key.split("/")[-1])
        if (
            "social media" in whole
            or leaf.endswith(" profile url")
            or "email" in leaf
            or "address" in leaf
        ):
            consumed.add(key)

    communities = fields.get("Profile/Alumni Communities")
    if isinstance(communities, list):
        consumed.add("Profile/Alumni Communities")
        result["Alumni Communities"] = record_lines(communities, lambda row: row.get("name"))
        result["Community Location"] = record_lines(communities, lambda row: row.get("location"))
        result["Community Member Count"] = record_lines(
            communities, lambda row: row.get("total_followings")
        )
        community_known = {"id", "name", "location", "total_followings"}
        community_keys = set().union(*(row.keys() for row in communities if isinstance(row, dict)))
        for key in sorted(community_keys - community_known):
            result[f"Alumni Communities · {label(key)}"] = record_lines(
                communities, lambda row, key=key: row.get(key)
            )

    for key, value in sorted(fields.items(), key=lambda item: column_order(item[0])):
        if key not in consumed and normalized(key.split("/")[-1]) not in {
            normalized(name) for name in KNOWN_FIELDS
        }:
            result[" · ".join(label(part) for part in key.split("/"))] = readable_value(value)
    return result


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
