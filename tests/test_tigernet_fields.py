import pytest

from tigerbook_scraper.errors import ExtractionError
from tigerbook_scraper.tigernet_fields import extract_profile, visible_base_keys


def source():
    return {
        "base": {
            "id": 1,
            "name": "Synthetic",
            "profile_is_private": False,
            "can_access_to_contact": True,
        },
        "header": {
            "header": {
                "name": "Header",
                "type": "data",
                "data": [{"display_name": "Name", "value": "Synthetic", "privacy": "with_all"}],
            }
        },
        "body": {
            "center": [
                {
                    "name": "Custom",
                    "type": "data",
                    "data": [
                        {"display_name": "Brand new field", "value": "東京", "privacy": "with_all"},
                        {
                            "display_name": "Admin field",
                            "value": "restricted",
                            "privacy": "with_admin",
                        },
                    ],
                }
            ],
            "contact": [],
        },
        "topics": {"topics": [], "has_next_page": False},
        "badges": {"data": [], "_metadata": {"has_next_page": False}},
        "rendered_text": "Synthetic 東京",
        "rendered_html": "",
    }


def test_new_fields_are_discovered_and_restricted_fields_excluded():
    fields = extract_profile(**source())
    assert fields["Custom/Brand new field"] == "東京"
    assert "Custom/Admin field" not in fields
    assert fields["Profile/name"] == "Synthetic"


def test_visible_base_keys_are_derived_per_profile_without_an_allowlist():
    base = {
        "name": "Synthetic",
        "new_header_attribute": "Appeared late",
        "hidden_backend_value": "Do not export",
    }
    header = {
        "header": {
            "name": "Header",
            "type": "data",
            "data": [
                {"display_name": "Name", "value": "Synthetic", "privacy": "with_all"},
                {
                    "display_name": "New header attribute",
                    "value": "Appeared late",
                    "privacy": "with_all",
                },
                {
                    "display_name": "Restricted",
                    "value": "Do not export",
                    "privacy": "with_admin",
                },
            ],
        }
    }
    assert visible_base_keys(base, header) == {"name", "new_header_attribute"}


def test_repeated_education_records_keep_their_associations():
    values = source()
    values["body"]["center"].append(
        {
            "name": "Education",
            "type": "educations",
            "data": [
                {
                    "school": {"name": "School A"},
                    "dynamic_attributes": [
                        {"display_name": "Degree", "value": "AB", "privacy": "with_all"}
                    ],
                },
                {
                    "school": {"name": "School B"},
                    "dynamic_attributes": [
                        {"display_name": "Degree", "value": "MS", "privacy": "with_all"}
                    ],
                },
            ],
        }
    )
    records = extract_profile(**values)["Education"]
    assert records[0]["school"]["name"] == "School A"
    assert records[1]["dynamic_attributes"]["Degree"] == "MS"


@pytest.mark.parametrize("problem", ["unknown_type", "unknown_privacy", "more_communities"])
def test_unknown_or_incomplete_structure_is_not_silently_accepted(problem):
    values = source()
    if problem == "unknown_type":
        values["body"]["center"][0]["type"] = "unobserved"
    elif problem == "unknown_privacy":
        values["body"]["center"][0]["data"][0]["privacy"] = "unknown_policy"
    else:
        values["topics"]["has_next_page"] = True
    with pytest.raises(ExtractionError):
        extract_profile(**values)
