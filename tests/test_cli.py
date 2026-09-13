from tigerbook_scraper.__main__ import main
from tigerbook_scraper.errors import ConfigurationError
from tigerbook_scraper.locking import run_lock


def test_help_does_not_need_credentials(capsys):
    import pytest

    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "--export-only" in capsys.readouterr().out


def test_missing_credentials_is_an_explicit_blocker(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TIGERNET_USERNAME", raising=False)
    monkeypatch.delenv("TIGERNET_PASSWORD", raising=False)
    code = main(
        [
            "--credentials-file",
            str(tmp_path / "absent.json"),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )
    assert code == 3
    assert "configuration_error" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.csv"))


def test_offline_export_does_not_read_credentials_or_import_browser(tmp_path, monkeypatch):
    import builtins

    from tigerbook_scraper.models import ListingPage, ProfileRef
    from tigerbook_scraper.state import State

    path = tmp_path / "full/run.sqlite"
    state = State(
        path,
        {"target": "https://example.test", "account": "synthetic", "scope": "full", "limit": None},
    )
    for phase in ("discovery", "reconciliation"):
        state.save_page(
            phase, None, ListingPage((ProfileRef("1", "https://example.test/1"),), None, 1, True)
        )
    state.complete("1", {"Name": "Synthetic"})
    state.note("field_fidelity_verified", True)
    state.close()
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise AssertionError("Offline export imported browser dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setenv("TIGERNET_USERNAME", "incomplete-environment")
    assert main(["--export-only", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "full/profiles.csv").is_file()


def test_lock_prevents_two_writers_and_is_released(tmp_path):
    import pytest

    with run_lock(tmp_path), pytest.raises(ConfigurationError), run_lock(tmp_path):
        pass
    with run_lock(tmp_path):
        pass


def test_fast_configuration_rejects_unbounded_rate_before_login(tmp_path, capsys):
    assert main(["--fast", "--requests-per-second", "1000", "--output-dir", str(tmp_path)]) == 3
    assert "rate ceiling" in capsys.readouterr().err


def test_fast_offline_export_uses_separate_scope(tmp_path, monkeypatch):
    from tigerbook_scraper.models import ListingPage, ProfileRef
    from tigerbook_scraper.state import State

    state = State(
        tmp_path / "fast-full/run.sqlite",
        {
            "target": "https://example.test",
            "account": "synthetic",
            "scope": "fast-full",
            "limit": None,
        },
    )
    state.save_page(
        "discovery",
        None,
        ListingPage(
            (ProfileRef("1", "https://example.test/1"),),
            None,
            1,
            False,
        ),
    )
    state.complete("1", {"Name": "Synthetic"})
    state.note("collection_mode", "direct_requests_fixed_header")
    state.close()
    monkeypatch.setenv("TIGERNET_USERNAME", "incomplete-environment")
    assert main(["--fast", "--export-only", "--output-dir", str(tmp_path)]) == 2
    assert (tmp_path / "fast-full/profiles.csv").exists()
    assert not (tmp_path / "full").exists()
