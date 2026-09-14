import argparse
import os
import sys
from pathlib import Path

from .config import TARGET, load_credentials, scope_name
from .errors import ScraperError
from .export import export_run
from .locking import run_lock
from .state import State


def parser():
    value = argparse.ArgumentParser(description="Resumable TigerNet directory export")
    value.add_argument("--limit", type=int, help="Isolated reviewer run with at most N profiles")
    value.add_argument(
        "--fast",
        action="store_true",
        help="Use observed concurrent requests with an automatic browser comparison",
    )
    value.add_argument(
        "--workers", type=int, help="Fast-mode in-flight request cap (1–32, default 32)"
    )
    value.add_argument(
        "--requests-per-second",
        type=float,
        help="Fast-mode starting request rate (default 2/s)",
    )
    value.add_argument(
        "--max-requests-per-second",
        type=float,
        help="Fast-mode adaptive request-rate ceiling (default 6/s, maximum 50/s)",
    )
    value.add_argument(
        "--browser-sessions",
        type=int,
        help="Independent authenticated fast-mode sessions (1–2, default 1)",
    )
    value.add_argument(
        "--allow-interactive",
        action="store_true",
        help="Open a visible browser and wait up to five minutes for your MFA approval",
    )
    mode = value.add_mutually_exclusive_group()
    mode.add_argument("--export-only", action="store_true", help="Validate saved records offline")
    mode.add_argument(
        "--check-auth", action="store_true", help="Verify fresh login and protected directory data"
    )
    mode.add_argument(
        "--inspect", action="store_true", help="Save a private authenticated inspection"
    )
    value.add_argument("--credentials-file", type=Path, default=Path("credentials.local.json"))
    value.add_argument("--output-dir", type=Path, default=Path("output"))
    value.add_argument("--site-contract", type=Path, default=Path("site-contract.json"))
    return value


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    # New databases, browser inspection files, and exports are private to this OS user.
    os.umask(0o077)
    state = None
    try:
        scope = scope_name(args.limit)
        if args.fast:
            scope = "fast-" + scope
            if args.workers is None:
                args.workers = 32
            if args.requests_per_second is None:
                args.requests_per_second = 2.0
            if args.max_requests_per_second is None:
                args.max_requests_per_second = 6.0
            if args.browser_sessions is None:
                args.browser_sessions = 1
            if args.inspect or args.check_auth:
                from .errors import ConfigurationError

                raise ConfigurationError("Use --fast for collection or offline export only.")
            if not (
                1 <= args.workers <= 32
                and 1 <= args.browser_sessions <= 2
                and 0 < args.requests_per_second <= args.max_requests_per_second <= 50
            ):
                from .errors import ConfigurationError

                raise ConfigurationError(
                    "Use 1–32 workers, 1–2 sessions, and rates where 0 < start <= maximum <= 50."
                )
        elif any(
            value is not None
            for value in (
                args.workers,
                args.requests_per_second,
                args.max_requests_per_second,
                args.browser_sessions,
            )
        ):
            from .errors import ConfigurationError

            raise ConfigurationError("Worker and rate options require --fast.")
        directory = args.output_dir / scope
        with run_lock(directory):
            if args.export_only:
                state = State(directory / "run.sqlite")
                report = export_run(state, directory)
                print(
                    f"Export {report['status']}: {report['rows']} rows, "
                    f"{report['columns']} columns."
                )
                return 0 if report["status"] == "complete" else 2
            credentials = load_credentials(args.credentials_file)
            # Browser dependencies are never loaded by --export-only.
            from playwright.sync_api import sync_playwright

            from .adapter import SiteAdapter, load_contract
            from .auth import authenticate
            from .fetch import Fetcher
            from .inspection import inspect_directory
            from .runner import collect

            contract = None
            if not args.inspect:
                contract = load_contract(args.site_contract)
            if args.fast:
                from .fast import collect_fast

                state = open_state(directory, credentials, scope, args.limit, args.site_contract)
                try:
                    collect_fast(
                        state,
                        credentials,
                        contract,
                        allow_interactive=args.allow_interactive,
                        limit=args.limit,
                        workers=args.workers,
                        start_rate=args.requests_per_second,
                        ceiling=args.max_requests_per_second,
                        browser_sessions=args.browser_sessions,
                    )
                except BaseException as error:
                    state.note(
                        "blocker",
                        "interrupted"
                        if isinstance(error, KeyboardInterrupt)
                        else getattr(error, "code", "unexpected_failure"),
                    )
                    export_run(state, directory)
                    raise
                report = export_run(state, directory)
                print(
                    f"Export {report['status']}: {report['rows']} rows, "
                    f"{report['columns']} columns."
                )
                if report["reasons"]:
                    print("Review report reasons: " + ", ".join(report["reasons"]))
                return 0 if report["status"] == "complete" else 2
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=not args.allow_interactive)
                context = browser.new_context()
                page = context.new_page()

                def login():
                    return authenticate(page, credentials, allow_interactive=args.allow_interactive)

                directory_url = login()
                print(
                    "Login flow reached a directory link; protected content still needs checking."
                )
                if args.inspect:
                    inspect_directory(page, directory_url, args.output_dir / "inspection")
                    print("Inspection saved locally under output-dir/inspection. Keep it private.")
                    return 0
                fetcher = Fetcher(context.request, TARGET, login)
                if contract["mode"] == "tigernet":
                    from .tigernet import TigerNetAdapter

                    adapter = TigerNetAdapter(page, fetcher, contract)
                else:
                    adapter = SiteAdapter(page, fetcher, contract)
                if args.check_auth:
                    listing = adapter.list_page(None)
                    if not listing.profiles:
                        from .errors import AuthenticationError

                        raise AuthenticationError("No accessible profiles verified the login.")
                    from .fields import from_mapping

                    from_mapping(adapter.profile(listing.profiles[0]))
                    print("Fresh login verified against directory and profile content.")
                    return 0
                state = open_state(directory, credentials, scope, args.limit, args.site_contract)
                try:
                    collect(adapter, state, limit=args.limit)
                except KeyboardInterrupt:
                    state.note("blocker", "interrupted")
                    export_run(state, directory)
                    print("Interrupted. Progress saved; restart the same command to resume.")
                    return 130
                except ScraperError as error:
                    state.note("blocker", error.code)
                    export_run(state, directory)
                    raise
                except Exception:
                    state.note("blocker", "unexpected_failure")
                    export_run(state, directory)
                    raise
                report = export_run(state, directory)
                print(
                    f"Export {report['status']}: {report['rows']} rows, "
                    f"{report['columns']} columns."
                )
                if report["reasons"]:
                    print("Review report reasons: " + ", ".join(report["reasons"]))
                return 0 if report["status"] == "complete" else 2
    except ScraperError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("Interrupted. Rerun the same command to continue saved progress.", file=sys.stderr)
        return 130
    except Exception:
        # No raw browser/HTTP exception traces: they may contain secrets or profile data.
        print(
            "Unexpected failure. Existing checkpoints are preserved; no success is claimed.",
            file=sys.stderr,
        )
        return 3
    finally:
        if state is not None:
            state.close()


def open_state(directory, credentials, scope, limit, contract_path):
    import hashlib

    from .errors import StateMismatch

    state = State(
        directory / "run.sqlite",
        {
            "target": TARGET,
            "account": credentials.account_key,
            "scope": scope,
            "limit": limit,
        },
    )
    try:
        digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
        if state.get("contract_sha256") not in (None, digest):
            raise StateMismatch("Parser contract changed; use a new output directory.")
        state.note("contract_sha256", digest)
        return state
    except BaseException:
        state.close()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
