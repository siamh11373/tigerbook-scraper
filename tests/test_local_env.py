from types import SimpleNamespace

import pytest

from tigerbook_scraper import local_env


@pytest.mark.parametrize("failure", [False, True])
def test_hidden_credentials_are_process_local_and_cleared(monkeypatch, capsys, failure):
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
    assert local_env.main(["--inspect"]) == (3 if failure else 0)
    assert all(key not in local_env.os.environ for key in local_env.KEYS)
    output = capsys.readouterr()
    assert "synthetic-password" not in output.out + output.err
    assert "synthetic-netid" not in output.out + output.err


def test_noninteractive_input_is_rejected_without_prompt(monkeypatch):
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(local_env.getpass, "getpass", lambda _: pytest.fail("Must not prompt"))
    assert local_env.main([]) == 3


def test_echo_fallback_is_rejected(monkeypatch):
    monkeypatch.setattr(local_env.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def unsafe_prompt(_):
        local_env.warnings.warn("Synthetic unavailable terminal", local_env.getpass.GetPassWarning)
        pytest.fail("Must not proceed with echoed input")

    monkeypatch.setattr(local_env.getpass, "getpass", unsafe_prompt)
    assert local_env.main([]) == 3
