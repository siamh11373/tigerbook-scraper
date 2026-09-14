"""Sequential installed-Chrome collection with durable, shared cooldowns."""

import argparse
import os
import time
from pathlib import Path

from .__main__ import open_state
from .adapter import load_contract
from .auth import authenticate
from .config import TARGET, Credentials, load_credentials, scope_name
from .errors import AccessBlocked, RateLimited, ScraperError
from .export import export_run
from .fetch import Fetcher, Pacer
from .local_env import read_env_file
from .locking import run_lock
from .runner import collect
from .tigernet import TigerNetAdapter


class CoolingAdapter:
    """One browser and one operation at a time; no queued recovery burst."""

    def __init__(self, adapter, state, *, pause, sleep=time.sleep, clock=time.time, progress=print):
        self.adapter, self.state = adapter, state
        self.pause, self.sleep, self.clock, self.progress = pause, sleep, clock, progress
        self.started = clock()
        self.initial = state.counts()["complete"]

    @property
    def field_coverage_verified(self):
        return self.adapter.field_coverage_verified

    def wait(self):
        until = self.state.get("chrome_cooldown_until", 0)
        while (remaining := until - self.clock()) > 0:
            self.progress(
                f"Collection paused; {remaining:.0f} seconds until next permitted attempt."
            )
            self.sleep(min(30, remaining))

    def call(self, operation):
        self.wait()
        for attempt in range(3):
            try:
                result = operation()
                self.state.note("chrome_cooldown_until", 0)
                return result
            except RateLimited as error:
                seconds = max(300 * 2**attempt, error.retry_after or 0)
                self.state.note("chrome_cooldown_until", self.clock() + seconds)
                self.state.note(
                    "chrome_last_throttle",
                    {
                        "observed_at": self.clock(),
                        "retry_after_seconds": error.retry_after,
                        "cooldown_seconds": seconds,
                    },
                )
                # Cancel background page traffic while the shared cooldown elapses.
                self.pause()
                self.progress(
                    f"HTTP 429: Retry-After={error.retry_after!r} seconds; "
                    f"collection cooldown={seconds:g} seconds."
                )
                if attempt == 2 or seconds > 3600:
                    raise AccessBlocked(
                        "Repeated throttling; saved cooldown must elapse before resume."
                    ) from None
                self.wait()

    def list_page(self, cursor):
        return self.call(lambda: self.adapter.list_page(cursor))

    def profile(self, ref):
        counts = self.state.counts()
        elapsed = max(self.clock() - self.started, 0.001)
        new = counts["complete"] - self.initial
        self.state.note(
            "benchmark",
            {
                "new_profiles": new,
                "elapsed_seconds": elapsed,
                "phase": "chrome_extraction",
                "interpretation": "includes browser waits and cooldowns",
            },
        )
        self.progress(
            f"Chrome collection: completed {counts['complete']}; pending {counts['pending']}; "
            f"failed {counts['failed']}; {new / elapsed:.3f} profiles/s."
        )
        return self.call(lambda: self.adapter.profile(ref))

    def audit(self, ref, fields):
        return self.adapter.audit(ref, fields)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, help="Separate Chrome sample; never limits the saved full run"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--site-contract", type=Path, default=Path("site-contract.json"))
    parser.add_argument(
        "--request-rate",
        type=int,
        choices=(1, 2, 3, 6),
        default=1,
        help="Shared paced navigation/data requests per second",
    )
    parser.add_argument(
        "--benchmark",
        type=int,
        choices=(20, 100),
        help="Collect a bounded number of additional profiles in the saved full run",
    )
    args = parser.parse_args(argv)
    if args.request_rate == 6 and args.benchmark != 20:
        parser.error("Rate 6 requires a bounded --benchmark 20 experiment.")
    if args.benchmark is not None and args.limit is not None:
        parser.error("--benchmark uses full-run state and cannot combine with --limit.")
    os.umask(0o077)
    state = None
    try:
        scope = "fast-full" if args.limit is None else "chrome-" + scope_name(args.limit)
        directory = args.output_dir / scope
        configured = any(
            os.environ.get(k) is not None for k in ("TIGERNET_USERNAME", "TIGERNET_PASSWORD")
        )
        local = None if configured else read_env_file(Path(".env.local"))
        credentials = (
            Credentials(*local) if local else load_credentials(Path("credentials.local.json"))
        )
        contract = load_contract(args.site_contract)
        with run_lock(directory):
            state = open_state(directory, credentials, scope, args.limit, args.site_contract)
            # Respect a previous process's cooldown before initiating authentication.
            until = state.get("chrome_cooldown_until", 0)
            if until > time.time():
                raise AccessBlocked(
                    f"Saved cooldown has {until - time.time():.0f} seconds remaining."
                )
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=False)
                try:
                    context = browser.new_context()
                    page = context.new_page()

                    def login():
                        return authenticate(page, credentials, allow_interactive=True)

                    login()
                    fetcher = Fetcher(
                        context.request,
                        TARGET,
                        login,
                        stop_on_throttle=True,
                        pacer=Pacer(1 / args.request_rate),
                    )
                    adapter = CoolingAdapter(
                        TigerNetAdapter(page, fetcher, contract),
                        state,
                        pause=lambda: page.goto("about:blank"),
                    )
                    adapter.list_page(None)  # Verify current protected access before resuming.
                    state.note(
                        "collection_mode",
                        "mixed_fast_and_chrome" if scope == "fast-full" else "chrome",
                    )
                    stop_at = (
                        state.counts()["complete"] + args.benchmark
                        if args.benchmark
                        else args.limit
                    )
                    state.note("chrome_request_rate", args.request_rate)
                    collect(adapter, state, limit=stop_at)
                finally:
                    browser.close()
            report = export_run(state, directory)
            print(
                f"Export {report['status']}: {report['rows']} profiles; "
                f"{report['columns']} columns."
            )
            return 0 if report["status"] == "complete" else 2
    except (Exception, KeyboardInterrupt) as error:
        if state is not None:
            state.note(
                "blocker",
                "interrupted"
                if isinstance(error, KeyboardInterrupt)
                else getattr(error, "code", "unexpected_failure"),
            )
            export_run(state, directory)
        if isinstance(error, ScraperError):
            print(f"{error.code}: {error}")
        else:
            print(
                "Chrome collection stopped; progress preserved. No raw browser errors are printed."
            )
        return 130 if isinstance(error, KeyboardInterrupt) else 3
    finally:
        if state is not None:
            state.close()


if __name__ == "__main__":
    raise SystemExit(main())
