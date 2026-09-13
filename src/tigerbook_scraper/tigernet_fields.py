"""Dynamic extraction from the profile response structures observed on TigerNet."""

from .errors import ExtractionError
from .fields import from_pairs


def allowed(node):
    if node.get("visibility") not in (None, "everybody"):
        return False
    privacy = node.get("privacy")
    if privacy in (None, "with_all"):
        return True
    if privacy in ("with_admin", "tagged_user"):
        return False
    raise ExtractionError("An unfamiliar field privacy policy requires inspection.")


def clean_value(value):
    if isinstance(value, list):
        return [clean_value(item) for item in value if not isinstance(item, dict) or allowed(item)]
    if isinstance(value, dict):
        if not allowed(value):
            raise ExtractionError("A restricted value cannot be exported.")
        # Native repeated records contain separately described dynamic attributes.
        result = {}
        for key, item in value.items():
            if key in ("user_editable", "privacy"):
                continue
            if key == "dynamic_attributes":
                if not isinstance(item, list):
                    raise ExtractionError("Repeated record attributes changed structure.")
                pairs = []
                for field in item:
                    if not isinstance(field, dict) or "display_name" not in field:
                        raise ExtractionError("A repeated record field has no display label.")
                    if allowed(field):
                        pairs.append(("", field["display_name"], clean_value(field.get("value"))))
                result[key] = from_pairs(pairs) if pairs else {}
            elif isinstance(item, dict) and not allowed(item):
                continue
            else:
                result[key] = clean_value(item)
        return result
    return value


def extract_profile(base, header, body, topics, badges, *, rendered_text, rendered_html):
    """Export display-labelled fields, intact repeated records, and visible basics.

    Unknown structures fail. Restricted fields are conservatively omitted, including
    self-only fields until account-specific visibility is established. This parser
    alone does not establish exhaustive field coverage.
    """
    if base.get("profile_is_private") is not False or not base.get("id"):
        raise ExtractionError("Accessible profile identity has not been established.")
    if not isinstance(header.get("header"), dict):
        raise ExtractionError("The observed profile header is missing.")
    if not isinstance(body.get("center"), list) or not isinstance(body.get("contact"), list):
        raise ExtractionError("The observed profile sections are missing.")
    pairs = []

    def section(node, parents=()):
        if not isinstance(node, dict) or not allowed(node):
            return
        name = node.get("name")
        if not isinstance(name, str) or not isinstance(node.get("data"), list):
            raise ExtractionError("A profile section no longer matches its observed structure.")
        context = (*parents, name)
        kind = node.get("type")
        if kind in ("experiences", "educations"):
            pairs.append(("/".join(parents), name, clean_value(node["data"])))
            return
        if kind not in ("data", "contact"):
            raise ExtractionError("An unrecognized profile section type needs inspection.")
        for entry in node["data"]:
            if not isinstance(entry, dict):
                raise ExtractionError("A profile row no longer has field metadata.")
            if not allowed(entry):
                continue
            if "data" in entry:
                section(entry, context)
            elif "display_name" in entry and "value" in entry:
                label = entry["display_name"]
                if not isinstance(label, str) or not label.strip():
                    raise ExtractionError("A profile field has no display label.")
                pairs.append(("/".join(context), label, clean_value(entry["value"])))
            else:
                raise ExtractionError("An unrecognized profile field needs inspection.")

    section(header["header"])
    for node in body["center"]:
        section(node)
    if base.get("can_access_to_contact") is True:
        for node in body["contact"]:
            section(node)
    # Capture unlabelled visible header values without copying permission flags or
    # hidden backend data. Labelled/custom fields above never use a fixed field list.
    text = " ".join(rendered_text.split())
    for key, value in base.items():
        if isinstance(value, str) and value.strip():
            normalized = " ".join(value.split())
            if normalized in text or (value.startswith("https://") and value in rendered_html):
                pairs.append(("Profile", key, value))
    if body.get("introduction"):
        pairs.append(("Profile", "introduction", clean_value(body["introduction"])))
    if not isinstance(topics.get("topics"), list) or not isinstance(badges.get("data"), list):
        raise ExtractionError("Community or badge response structure changed.")
    if topics.get("has_next_page") or badges.get("_metadata", {}).get("has_next_page"):
        raise ExtractionError("Additional community or badge pages must be collected.")
    pairs.append(("Profile", "Alumni Communities", clean_value(topics["topics"])))
    pairs.append(("Profile", "Badges", clean_value(badges["data"])))
    return from_pairs(pairs)
