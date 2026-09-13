import csv
import json

from tigerbook_scraper.export import export_run
from tigerbook_scraper.models import ListingPage, ProfileRef
from tigerbook_scraper.presentation import (
    KNOWN_FIELDS,
    headings,
    readable_fields,
    spreadsheet_value,
)
from tigerbook_scraper.state import State


def test_readable_export_and_lossless_companion(tmp_path):
    state = State(
        tmp_path / "run.sqlite",
        {
            "target": "https://example.test",
            "account": "synthetic",
            "scope": "sample-2",
            "limit": 2,
        },
    )
    state.save_page(
        "discovery",
        None,
        ListingPage(
            (
                ProfileRef("001", "https://example.test/1"),
                ProfileRef("002", "https://example.test/2"),
            ),
            None,
            2,
            True,
        ),
    )
    education = [
        {"school": {"name": "School A"}, "degree": "AB"},
        {"school": {"name": "School B"}, "degree": "MS"},
    ]
    state.complete(
        "001",
        {
            "Information/Full Name": 'Synthetic, "東京"',
            "Education": education,
            "Interests": ["Music", "Reading"],
            "Formula": "=1+1",
        },
    )
    state.complete("002", {"Information/Full Name": "Second", "Late field": "00123"})
    report = export_run(state, tmp_path)
    with (tmp_path / "profiles.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames[2 : 2 + len(KNOWN_FIELDS)] == list(KNOWN_FIELDS)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["Full Name"] == 'Synthetic, "東京"'
    assert rows[0]["Educational Institution"] == ("Record 1: School A\nRecord 2: School B")
    assert rows[0]["Degree"] == "Record 1: AB\nRecord 2: MS"
    assert rows[0]["Interests"] == "Music\nReading"
    assert rows[0]["Formula"] == "'=1+1"
    assert rows[1]["Late field"] == "'00123"
    assert rows[0]["Late field"] == rows[1]["Educational Institution"] == ""
    with (tmp_path / "profiles.raw.csv").open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    assert json.loads(raw[0]["field/Education"]) == education
    assert raw[0]["profile_id"] == "001"
    assert raw[0]["field/Formula"] == "=1+1"
    assert report["csv_roundtrip_verified"] and report["raw_export"]["csv_roundtrip_verified"]
    assert report["known_field_coverage"]["profiles_with_values"]["Full Name"] == 2
    assert "Employer" in report["known_field_coverage"]["fields_without_values"]
    first = (tmp_path / "profiles.csv").read_bytes()
    export_run(state, tmp_path)
    assert (tmp_path / "profiles.csv").read_bytes() == first
    state.close()


def test_headings_decode_escapes_without_losing_colliding_columns():
    result = headings(["A~1B/C", "A/B~1C", "Profile ID", "A/B_C", "A/B C"])
    assert "A/B · C" in result and "A · B/C" in result
    assert len(result) == len(set(result)) == 7


def test_multiline_and_empty_values_remain_readable():
    assert spreadsheet_value(None) == spreadsheet_value([]) == spreadsheet_value({}) == ""
    assert spreadsheet_value({"notes": "first\nsecond", "active": False}) == (
        "notes:\n  first\n  second\nactive: No"
    )
    assert spreadsheet_value("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"


def test_known_repeated_fields_are_promoted_and_records_stay_aligned():
    fields = readable_fields(
        {
            "Princeton Information/Full Name": "Synthetic Person",
            "Experience": [
                {
                    "position": "Engineer",
                    "company": {"name": "Company A", "industry": "Technology"},
                    "from": "2020",
                    "to": "2022",
                    "dynamic_attributes": {
                        "Field/Specialty": ["Software"],
                        "Work, Board, or Military": ["Work"],
                        "Unexpected work field": "Extra",
                    },
                },
                {
                    "position": "Manager",
                    "company": {"name": "Company B"},
                    "to": "Present",
                    "dynamic_attributes": {"Position Level (Types of Positions)": ["Management"]},
                },
            ],
            "Education": [
                {
                    "school": {"name": "School A", "country": "United States"},
                    "to": "2020",
                    "dynamic_attributes": {
                        "Degree Year": "2020",
                        "Degree": ["AB"],
                        "Major": ["Computer Science"],
                        "Academic Level": ["Undergraduate"],
                        "Unexpected school field": "Honors",
                    },
                }
            ],
            "Contact/Social media links/LinkedIn profile url": "https://example.test/person",
            "Contact/Emails/Primary email": "person@example.test",
            "Contact/Postal address(es)/Postal address (personal)": {"city": "Princeton"},
            "Profile/Alumni Communities": [
                {
                    "name": "Community A",
                    "location": "New Jersey",
                    "total_followings": 123,
                    "website": "https://example.test/community",
                }
            ],
        }
    )
    assert list(fields)[: len(KNOWN_FIELDS)] == list(KNOWN_FIELDS)
    assert fields["Job Title"] == "Record 1: Engineer\nRecord 2: Manager"
    assert fields["Employer"] == "Record 1: Company A\nRecord 2: Company B"
    assert fields["Employment Date"] == "Record 1: 2020 to 2022\nRecord 2: Present"
    assert fields["Field/Specialty"] == "Record 1: Software"
    assert fields["Degree Year"] == "Record 1: 2020"
    assert fields["Educational Institution"] == "Record 1: School A"
    assert fields["Social Media Links"].startswith("LinkedIn profile url:")
    assert fields["Emails"] == "Primary email: person@example.test"
    assert fields["Address"] == "Postal address (personal): city: Princeton"
    assert fields["Alumni Communities"] == "Record 1: Community A"
    assert fields["Community Location"] == "Record 1: New Jersey"
    assert fields["Community Member Count"] == "Record 1: 123"
    assert fields["Experience · Unexpected work field"] == "Record 1: Extra"
    assert fields["Experience · Employer · industry"] == "Record 1: Technology"
    assert fields["Education · Unexpected school field"] == "Record 1: Honors"
    assert fields["Education · Educational Institution · country"] == ("Record 1: United States")
    assert fields["Alumni Communities · website"] == ("Record 1: https://example.test/community")
