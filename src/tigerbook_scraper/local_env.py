"""Configure process-local credentials with hidden terminal prompts, then run."""

import getpass
import os
import sys
import warnings
from pathlib import Path

from .__main__ import main as run_scraper

KEYS = ("TIGERNET_USERNAME", "TIGERNET_PASSWORD")


def read_env_file(path):
    """Read only the two supported keys without evaluating shell syntax."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError("The local environment file could not be read.") from None

    values = {}
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw = stripped.partition("=")
        key = key.strip()
        if not separator or key not in KEYS:
            raise ValueError(f"Unsupported entry in .env.local on line {number}.")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value

    if not values:
        return None
    if set(values) != set(KEYS) or not all(values.values()):
        raise ValueError("Set both credential values in .env.local.")
    return tuple(values[key] for key in KEYS)


def main(argv=None, *, env_file=None):
    args = sys.argv[1:] if argv is None else argv
    if "--help" in args or "-h" in args:
        return run_scraper(args)
    configured = tuple(os.environ.get(key) for key in KEYS)
    if any(value is not None for value in configured):
        if not all(configured):
            print("Set both TIGERNET_USERNAME and TIGERNET_PASSWORD.", file=sys.stderr)
            return 3
        username, password = configured
    else:
        try:
            file_values = read_env_file(Path(".env.local") if env_file is None else env_file)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 3
        if file_values is not None:
            username, password = file_values
        else:
            if not sys.stdin.isatty():
                print(
                    "Configure .env.local or run this launcher in an interactive terminal.",
                    file=sys.stderr,
                )
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
                    "Hidden terminal input is unavailable; no credentials were configured.",
                    file=sys.stderr,
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
        print("Launcher failed; credentials were cleared from the process.", file=sys.stderr)
        return 3
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
