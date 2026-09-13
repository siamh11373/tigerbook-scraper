from types import SimpleNamespace

import pytest

from tigerbook_scraper import local_env


@pytest.mark.parametrize("failure", [False, True])
def test_hidden_credentials_are_process_local_and_cleared(tmp_path, monkeypatch, capsys, failure):
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    for key in local_env.KEYS:
        monkeypatch.delenv(key, raising=False)
    inputs = iter(["synthetic-netid", "synthetic-password"])
    monkeypatch.setattr(local_env.getpass, "getpass", lambda _: next(inputs))

    def run(args):
        assert args == ["--inspect"]
        assert local_env.os.environ["TIGERNET_USERNAME"] == "synthetic-netid"
        assert local_env.os.environ["TIGERNET_PASSWORD"] == "synthetic-password"
        if failure:
            raise RuntimeError("synthetic-password")
        return 0

    monkeypatch.setattr(local_env, "run_scraper", run)
    assert local_env.main(["--inspect"], env_file=tmp_path / ".env.local") == (3 if failure else 0)
    assert all(key not in local_env.os.environ for key in local_env.KEYS)
    output = capsys.readouterr()
    assert "synthetic-password" not in output.out + output.err
    assert "synthetic-netid" not in output.out + output.err


def test_noninteractive_input_is_rejected_without_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(local_env.getpass, "getpass", lambda _: pytest.fail("Must not prompt"))
    assert local_env.main([], env_file=tmp_path / ".env.local") == 3


def test_local_env_file_works_without_a_terminal_and_is_cleared(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "TIGERNET_USERNAME='synthetic-netid'\nTIGERNET_PASSWORD=\"synthetic-password\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    for key in local_env.KEYS:
        monkeypatch.delenv(key, raising=False)

    def run(args):
        assert args == ["--fast"]
        assert local_env.os.environ["TIGERNET_USERNAME"] == "synthetic-netid"
        assert local_env.os.environ["TIGERNET_PASSWORD"] == "synthetic-password"
        return 0

    monkeypatch.setattr(local_env, "run_scraper", run)
    assert local_env.main(["--fast"], env_file=env_file) == 0
    assert all(key not in local_env.os.environ for key in local_env.KEYS)
    output = capsys.readouterr()
    assert "synthetic-password" not in output.out + output.err
    assert "synthetic-netid" not in output.out + output.err


def test_local_env_file_rejects_missing_or_unknown_entries(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / ".env.local"
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(local_env, "run_scraper", lambda _: pytest.fail("Must not run"))
    env_file.write_text("TIGERNET_USERNAME=synthetic\n", encoding="utf-8")
    assert local_env.main([], env_file=env_file) == 3
    assert "both credential values" in capsys.readouterr().err

    env_file.write_text("UNSUPPORTED=value\n", encoding="utf-8")
    assert local_env.main([], env_file=env_file) == 3
    assert "Unsupported entry" in capsys.readouterr().err


def test_echo_fallback_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def unsafe_prompt(_):
        local_env.warnings.warn("Synthetic unavailable terminal", local_env.getpass.GetPassWarning)
        pytest.fail("Must not proceed with echoed input")

    monkeypatch.setattr(local_env.getpass, "getpass", unsafe_prompt)
    assert local_env.main([], env_file=tmp_path / ".env.local") == 3
