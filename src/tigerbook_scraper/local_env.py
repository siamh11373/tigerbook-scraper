"""Configure process-local credentials with hidden terminal prompts, then run."""

import getpass
import os
import sys
import warnings

from .__main__ import main as run_scraper

KEYS = ("TIGERNET_USERNAME", "TIGERNET_PASSWORD")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if "--help" in args or "-h" in args:
        return run_scraper(args)
    if not sys.stdin.isatty():
        print("Run this credential launcher in an interactive terminal.", file=sys.stderr)
        return 3
    try:
        # Refuse getpass's fallback to echoed input if terminal hiding is unavailable.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            username = getpass.getpass("Princeton NetID (hidden): ").strip()
            password = getpass.getpass("Princeton CAS password (hidden): ")
    except (EOFError, KeyboardInterrupt):
        print("Credential entry cancelled.", file=sys.stderr)
        return 130
    except getpass.GetPassWarning:
        print(
            "Hidden terminal input is unavailable; no credentials were configured.", file=sys.stderr
        )
        return 3
    if not username or not password:
        print("Both credentials are required.", file=sys.stderr)
        return 3

    previous = {key: os.environ.get(key) for key in KEYS}
    try:
        os.environ.update(dict(zip(KEYS, (username, password), strict=True)))
        return run_scraper(args)
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("Launcher failed; credentials were not saved to a file.", file=sys.stderr)
        return 3
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
