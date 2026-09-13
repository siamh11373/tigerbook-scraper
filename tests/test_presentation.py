import csv
import json

from tigerbook_scraper.export import export_run
from tigerbook_scraper.models import ListingPage, ProfileRef
from tigerbook_scraper.presentation import headings, spreadsheet_value
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
        assert reader.fieldnames[2] == "Information · Full Name"
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["Information · Full Name"] == 'Synthetic, "東京"'
    assert rows[0]["Education"] == (
        "Record 1\nschool: name: School A\ndegree: AB\n\n"
        "Record 2\nschool: name: School B\ndegree: MS"
    )
    assert rows[0]["Interests"] == "Music\nReading"
    assert rows[0]["Formula"] == "'=1+1"
    assert rows[1]["Late field"] == "'00123"
    assert rows[0]["Late field"] == rows[1]["Education"] == ""
    with (tmp_path / "profiles.raw.csv").open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    assert json.loads(raw[0]["field/Education"]) == education
    assert raw[0]["profile_id"] == "001"
    assert raw[0]["field/Formula"] == "=1+1"
    assert report["csv_roundtrip_verified"] and report["raw_export"]["csv_roundtrip_verified"]
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
