import pytest

from tigerbook_scraper.errors import AuthenticationError, ExtractionError
from tigerbook_scraper.export import export_run
from tigerbook_scraper.models import ListingPage, ProfileRef
from tigerbook_scraper.runner import collect
from tigerbook_scraper.state import State


class SyntheticAdapter:
    def __init__(self, fail=None):
        self.fetched = []
        self.fail = fail

    def list_page(self, cursor):
        ids = ["1", "2"] if cursor is None else ["2", "3"]
        return ListingPage(
            tuple(ProfileRef(i, f"https://example.test/{i}") for i in ids),
            "page2" if cursor is None else None,
            3,
            True,
        )

    def profile(self, ref):
        self.fetched.append(ref.id)
        if self.fail and ref.id == "2":
            raise self.fail
        return {"Name": "Same display name", "Late Field": [ref.id, "東京"]}

    def audit(self, ref, fields):
        return fields == {"Name": "Same display name", "Late Field": [ref.id, "東京"]}


def new_state(path, limit=None):
    return State(
        path,
        {
            "target": "https://example.test",
            "account": "synthetic",
            "scope": "full" if limit is None else f"sample-{limit}",
            "limit": limit,
        },
    )


def test_uninterrupted_and_resumed_runs_match(tmp_path):
    first = new_state(tmp_path / "resumed.sqlite")
    with pytest.raises(KeyboardInterrupt):
        collect(SyntheticAdapter(KeyboardInterrupt()), first, progress=lambda _: None)
    assert first.counts()["complete"] == 1
    first.close()
    resumed = new_state(tmp_path / "resumed.sqlite")
    adapter = SyntheticAdapter()
    collect(adapter, resumed, progress=lambda _: None)
    assert "1" not in adapter.fetched
    clean = new_state(tmp_path / "clean.sqlite")
    collect(SyntheticAdapter(), clean, progress=lambda _: None)
    assert list(resumed.records()) == list(clean.records())
    assert export_run(resumed, tmp_path / "out")["status"] == "complete"
    resumed.close()
    clean.close()


def test_limit_keeps_full_scope_incomplete(tmp_path):
    state = new_state(tmp_path / "sample.sqlite", limit=1)
    adapter = SyntheticAdapter()
    collect(adapter, state, limit=1, progress=lambda _: None)
    assert adapter.fetched == ["1"]
    report = export_run(state, tmp_path / "out")
    assert report["status"] == "partial" and "limited_run" in report["reasons"]
    state.close()


def test_failed_profile_is_retried_on_next_run(tmp_path):
    state = new_state(tmp_path / "run.sqlite")
    collect(SyntheticAdapter(ExtractionError("synthetic")), state, progress=lambda _: None)
    assert state.counts()["failed"] == 1
    collect(SyntheticAdapter(), state, progress=lambda _: None)
    assert state.counts()["complete"] == 3
    state.close()


def test_authentication_block_preserves_pending_profile(tmp_path):
    state = new_state(tmp_path / "run.sqlite")
    with pytest.raises(AuthenticationError):
        collect(SyntheticAdapter(AuthenticationError("synthetic")), state, progress=lambda _: None)
    assert state.counts()["pending"] == 1
    state.close()
