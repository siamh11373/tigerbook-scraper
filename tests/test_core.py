import csv
import json

import pytest

from tigerbook_scraper.config import Credentials, load_credentials, scope_name
from tigerbook_scraper.errors import (
    ConfigurationError,
    DiscoveryError,
    ExtractionError,
    StateMismatch,
)
from tigerbook_scraper.export import export_run
from tigerbook_scraper.fields import from_mapping, from_pairs
from tigerbook_scraper.models import ListingPage, ProfileRef
from tigerbook_scraper.state import State


@pytest.fixture
def identity():
    return {
        "target": "https://example.test",
        "account": "synthetic",
        "scope": "full",
        "limit": None,
    }


@pytest.fixture
def state(tmp_path, identity):
    value = State(tmp_path / "run.sqlite", identity)
    yield value
    value.close()


def listing(*ids, next_cursor=None, total=None):
    return ListingPage(
        tuple(ProfileRef(i, f"https://example.test/people/{i}") for i in ids),
        next_cursor,
        total,
        True,
    )


def test_identity_and_secret_repr(tmp_path, monkeypatch):
    monkeypatch.setenv("TIGERNET_USERNAME", "sample")
    monkeypatch.setenv("TIGERNET_PASSWORD", "synthetic-secret")
    c = load_credentials(tmp_path / "missing.json")
    assert "sample" not in repr(c) and "synthetic-secret" not in repr(c)
    assert c.account_key == Credentials("SAMPLE", "different").account_key
    monkeypatch.delenv("TIGERNET_PASSWORD")
    with pytest.raises(ConfigurationError):
        load_credentials(tmp_path / "missing.json")


def test_local_credentials_and_sample_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("TIGERNET_USERNAME", raising=False)
    monkeypatch.delenv("TIGERNET_PASSWORD", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text('{"username":"sample", "password":"test"}')
    assert load_credentials(path).username == "sample"
    assert scope_name(None) == "full"
    assert scope_name(25) == "sample-25"
    with pytest.raises(ConfigurationError):
        scope_name(0)


def test_dynamic_fields_keep_sections_repetitions_and_label_collisions():
    fields = from_pairs(
        [
            ("Contact", "Name", "First"),
            ("Employer", "Name", "Second"),
            ("Education", "Degree", {"year": 2024, "value": "AB"}),
            ("Education", "Degree", {"year": 2026, "value": "MS"}),
            ("A/B", "C", "one"),
            ("A", "B/C", "two"),
        ]
    )
    assert fields["Contact/Name"] == "First"
    assert fields["Employer/Name"] == "Second"
    assert len(fields["Education/Degree"]) == 2
    assert fields["A~1B/C"] != fields["A/B~1C"]


@pytest.mark.parametrize("value", [None, [], {}, {"bad": float("nan")}, {"": "value"}])
def test_invalid_profile_is_a_failure(value):
    with pytest.raises(ExtractionError):
        from_mapping(value)


def test_pagination_overlap_and_repeated_cursor(state):
    state.save_page("discovery", None, listing("1", "2", next_cursor="page2"))
    state.save_page("discovery", "page2", listing("2", "3", total=3))
    assert state.counts()["discovered"] == 3
    assert state.checkpoint("discovery")["done"]
    with pytest.raises(DiscoveryError):
        state.save_page("discovery", "page2", listing("2", "3"))


def test_loop_does_not_advance_checkpoint(state):
    state.save_page("discovery", None, listing("1", next_cursor="page2"))
    with pytest.raises(DiscoveryError):
        state.save_page("discovery", "page2", listing("2", next_cursor="page2"))
    assert state.counts()["discovered"] == 1
    assert state.checkpoint("discovery")["cursor"] == "page2"


def test_stalled_discovery_rolls_back(state):
    state.save_page("discovery", None, listing("1", next_cursor="page2"))
    with pytest.raises(DiscoveryError):
        state.save_page("discovery", "page2", listing("1", next_cursor="page3"))
    assert state.checkpoint("discovery")["cursor"] == "page2"


def test_crash_during_checkpoint_is_atomic(state):
    state.db.execute("""CREATE TRIGGER inject_crash BEFORE INSERT ON pages
                       BEGIN SELECT RAISE(ABORT, 'synthetic crash'); END""")
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        state.save_page("discovery", None, listing("1", next_cursor="page2"))
    assert state.counts()["discovered"] == 0
    assert state.checkpoint("discovery") == {"cursor": None, "done": False}


def test_resume_and_scope_mismatch(tmp_path, identity):
    path = tmp_path / "run.sqlite"
    first = State(path, identity)
    first.save_page("discovery", None, listing("1", "2"))
    first.complete("1", {"Name": "Same Name"})
    first.close()
    resumed = State(path, identity)
    assert [ref.id for ref in resumed.pending()] == ["2"]
    resumed.complete("2", {"Name": "Same Name"})
    assert resumed.counts()["complete"] == 2
    resumed.close()
    with pytest.raises(StateMismatch):
        State(path, {**identity, "account": "other"})


def test_export_union_roundtrip_and_complete_status(state, tmp_path):
    for phase in ("discovery", "reconciliation"):
        state.save_page(phase, None, listing("1", "2", total=2))
    first = {"Name": 'A, "quote"\n東京', "Empty": None, "Phone": "+15550000000"}
    second = {
        "Name": "Other",
        "Unexpected Field": ["one", "two"],
        "profile_id": "actual source field",
        "Formula-like": "=1+1",
    }
    state.complete("1", first)
    state.complete("2", second)
    state.note("field_fidelity_verified", True)
    report = export_run(state, tmp_path / "out")
    with (tmp_path / "out/profiles.raw.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["field/Name"] == first["Name"]
    assert rows[0]["field/Empty"] == ""
    assert rows[0]["field/Unexpected Field"] == ""
    assert json.loads(rows[1]["field/Unexpected Field"]) == ["one", "two"]
    assert rows[1]["profile_id"] == "2"
    assert rows[1]["field/profile_id"] == "actual source field"
    assert rows[1]["field/Formula-like"] == "=1+1"
    assert report["status"] == "complete"
    assert report["raw_export"]["text_sensitive_cells"] == 2
    assert report["manual_sheet_import_verified"] is False


def test_failure_missing_data_and_incomplete_coverage(state, tmp_path):
    state.save_page("discovery", None, listing("1", "2", total=3))
    state.complete("1", {"Name": "Synthetic", "Phone": None})
    state.fail("2", "fetch_failed")
    report = export_run(state, tmp_path / "out")
    assert report["rows"] == 1
    assert report["status"] == "partial"
    assert "unresolved_profiles" in report["reasons"]
    assert "discovery_count_mismatch" in report["reasons"]
    assert "reconciliation_unfinished" in report["reasons"]
    assert "field_fidelity_not_verified" in report["reasons"]


def test_new_profile_in_reconciliation_is_pending(state):
    state.save_page("discovery", None, listing("1"))
    state.complete("1", {"Name": "Synthetic"})
    state.save_page("reconciliation", None, listing("1", "2"))
    assert [ref.id for ref in state.pending()] == ["2"]
    assert state.membership_differences() == 1


def test_large_values_and_original_labels_survive_export(state, tmp_path):
    state.save_page("discovery", None, listing("1"))
    large = "東京" * 100_000
    fields = from_pairs([("Section", "Label  with  spaces", large)])
    state.complete("1", fields)
    report = export_run(state, tmp_path / "out")
    assert report["max_cell_characters"] == len(large)
    assert report["csv_roundtrip_verified"]
    assert "Section/Label  with  spaces" in fields


def test_status_updates_do_not_skip_pending_batches(state):
    ids = [f"{i:04d}" for i in range(301)]
    state.save_page("discovery", None, listing(*ids))
    processed = []
    for ref in state.pending():
        state.complete(ref.id, {"Name": "Synthetic"})
        processed.append(ref.id)
    assert processed == ids
    assert state.counts()["complete"] == 301
