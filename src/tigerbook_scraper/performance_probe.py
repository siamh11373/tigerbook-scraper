"""One authenticated, bounded experiment; no automatic collection-path changes."""

import json
import os
import sqlite3
import time
from pathlib import Path

from .adapter import load_contract, target_url
from .config import TARGET, Credentials, load_credentials
from .embedded_probe import inspect_embedded, inspect_script
from .fast import KINDS
from .fetch import login_response
from .html_probe import strings
from .local_env import read_env_file
from .tigernet import response_kind
from .tigernet_fields import extract_profile

BROWSER_BATCH = """async ({jobs, concurrency, interval}) => {
  const results = new Array(jobs.length);
  let next = 0, nextAt = performance.now(), stopped = false;
  async function worker() {
    while (!stopped && next < jobs.length) {
      const index = next++;
      const scheduled = Math.max(nextAt, performance.now());
      nextAt = scheduled + interval;
      await new Promise(resolve => setTimeout(resolve, Math.max(0, scheduled-performance.now())));
      if (stopped) return;
      const started = performance.now();
      try {
        const response = await fetch(jobs[index].url, {
          credentials: 'include', headers: jobs[index].headers,
          redirect: 'error', signal: AbortSignal.timeout(30000)
        });
        const text = await response.text();
        results[index] = {status: response.status, text,
          seconds: (performance.now()-started)/1000};
        if (!response.ok) stopped = true;
      } catch (_) { results[index] = {status: 0, text: '', seconds: 30}; stopped = true; }
    }
  }
  await Promise.all(Array.from({length: concurrency}, worker));
  return results;
}"""


def typed_leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from typed_leaves(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from typed_leaves(item, (*path, str(index)))
    else:
        yield path, type(value).__name__, json.dumps(value, ensure_ascii=False)


def compare_payloads(reference, actual):
    return {kind: reference.get(kind) == actual.get(kind) for kind in sorted(KINDS)}


def experiment_complete(report, expected_samples):
    required = {("request_context", 1), ("browser_fetch", 1), ("browser_fetch", 3)}
    return (
        not report.get("blocker")
        and len(report["samples"]) == expected_samples
        and all(
            not sample.get("blocker")
            and {(row["transport"], row["concurrency"]) for row in sample.get("transports", [])}
            == required
            and all(row.get("statuses") == [200] * 5 for row in sample["transports"])
            for sample in report["samples"]
        )
    )


def profile_pacer(profile_id):
    next_at = 0.0

    def pace(route, _request=None):
        nonlocal next_at
        if route.request.resource_type in ("image", "font", "media"):
            route.abort()
            return
        if response_kind(route.request.url, profile_id):
            time.sleep(max(0, next_at - time.monotonic()))
            next_at = time.monotonic() + 1
        route.continue_()

    return pace


def summarize_overlap(payloads):
    # Counts only. Identical leaves are evidence of repetition, not permission to omit a call.
    leaves = {kind: set(typed_leaves(value)) for kind, value in payloads.items()}
    return {
        kind: {
            "typed_leaves": len(items),
            "unique_path_value_leaves": len(
                items - set().union(*(other for name, other in leaves.items() if name != kind))
            ),
        }
        for kind, items in leaves.items()
    }


def main():
    from playwright.sync_api import sync_playwright

    from .auth import authenticate

    os.umask(0o077)
    output = Path("output/performance-probe")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "samples": [],
        "complete": False,
        "interfaces_confirmed": False,
        "pacing": "minimum 0.5 seconds between starts for each condition",
        "unmeasured_browser_background_traffic": True,
        "interpretation": "small-sample transport comparison, not a sustained-rate benchmark",
        "full_field_coverage_verified": False,
    }
    values = None
    if not any(
        os.environ.get(key) is not None for key in ("TIGERNET_USERNAME", "TIGERNET_PASSWORD")
    ):
        values = read_env_file(Path(".env.local"))
    credentials = (
        Credentials(*values) if values else load_credentials(Path("credentials.local.json"))
    )
    path = Path("output/fast-full/run.sqlite").resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        identity = json.loads(
            db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0]
        )
        if identity["account"] != credentials.account_key or identity["target"] != TARGET:
            raise ValueError("Reference identity mismatch")
        rows = db.execute(
            "SELECT id,url,fields FROM profiles WHERE status='complete' ORDER BY length(fields),id"
        ).fetchall()
    if not rows:
        raise ValueError("Missing references")
    samples = [rows[index] for index in sorted({0, len(rows) // 2, len(rows) - 1})]
    contract = load_contract(Path("site-contract.json"))
    scripts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            authenticate(page, credentials, allow_interactive=True)
            response = context.request.get(target_url(contract["listing_url"]), max_redirects=0)
            try:
                if response.status != 200:
                    raise ValueError("Directory blocked")
                listing = response.json()
                if not isinstance(listing.get("users"), list):
                    raise ValueError("Directory not verified")
                report["listing_record_keys"] = sorted(
                    set().union(*(set(user) for user in listing["users"]))
                )
            finally:
                response.dispose()
            for number, (profile_id, url, saved) in enumerate(samples, 1):
                captured, observed, blocked = {}, {}, []
                pace = profile_pacer(profile_id)

                def capture(
                    response,
                    profile_id=profile_id,
                    captured=captured,
                    observed=observed,
                    blocked=blocked,
                ):
                    kind = response_kind(response.url, profile_id)
                    try:
                        if kind and response.status in (403, 429):
                            blocked.append(response.status)
                        if kind and response.status == 200:
                            captured[kind] = response.json()
                            observed[kind] = {
                                "url": target_url(response.url),
                                "headers": {
                                    key: value
                                    for key, value in response.request.all_headers().items()
                                    if key
                                    in (
                                        "accept",
                                        "authorization",
                                        "x-csrf-token",
                                        "x-xsrf-token",
                                        "x-requested-with",
                                    )
                                },
                            }
                        elif response.request.resource_type == "script" and len(scripts) < 12:
                            body = response.text()
                            if len(body) <= 5_000_000 and len(scripts) < 12:
                                scripts.append(inspect_script(body))
                    except Exception:
                        pass

                page.route("**/*", pace)
                page.on("response", capture)
                try:
                    navigation = page.goto(
                        target_url(url), wait_until="domcontentloaded", timeout=30000
                    )
                    html = navigation.text() if navigation else ""
                    deadline = time.monotonic() + 45
                    while set(captured) != KINDS and not blocked and time.monotonic() < deadline:
                        page.wait_for_timeout(100)
                    embedded = inspect_embedded(html)
                    corpus = " ".join(strings(embedded["objects"]))
                    expected_values = list(strings(json.loads(saved)))
                    sample = {
                        "sample": number,
                        "embedded": embedded["summary"],
                        "reference_strings_found_in_decoded_state": sum(
                            value in corpus for value in expected_values
                        ),
                        "reference_string_count": len(expected_values),
                        "observed_response_kinds": sorted(captured),
                    }
                    report["samples"].append(sample)
                finally:
                    page.remove_listener("response", capture)
                    page.unroute("**/*", pace)
                if blocked:
                    report["blocker"] = "service_block_during_observation"
                    break
                if set(captured) != KINDS:
                    sample["blocker"] = "incomplete_observed_responses"
                    print(
                        f"Sample {number}: incomplete observed response set; skipped benchmark.",
                        flush=True,
                    )
                    continue
                sample["overlap"] = summarize_overlap(captured)
                sample["section_empty"] = {
                    "communities": captured["topics"].get("total_items") == 0,
                    "badges": captured["badges"].get("data") == [],
                }
                try:
                    rendered_text = page.locator("body").inner_text()
                    rendered_html = page.content()
                    baseline_fields = extract_profile(
                        **captured,
                        rendered_text=rendered_text,
                        rendered_html=rendered_html,
                    )
                    sample["baseline_field_count"] = len(baseline_fields)
                except Exception:
                    baseline_fields = None
                    sample["baseline_extraction_verified"] = False
                jobs = [observed[kind] for kind in sorted(KINDS)]
                sample["transports"] = []
                # Sequential conditions avoid adding rates. Reverse sample 2's order.
                modes = [("request_context", 1), ("browser_fetch", 1), ("browser_fetch", 3)]
                if number == 2:
                    modes.reverse()
                for transport, concurrency in modes:
                    # Keep even fast condition boundaries below the per-condition start rate.
                    time.sleep(0.5)
                    start = time.monotonic()
                    results = []
                    if transport == "request_context":
                        next_start = time.monotonic()
                        for job in jobs:
                            time.sleep(max(0, next_start - time.monotonic()))
                            next_start = time.monotonic() + 0.5
                            response = context.request.get(**job, max_redirects=0, timeout=30000)
                            try:
                                results.append({"status": response.status, "text": response.text()})
                                if response.status != 200:
                                    break
                            finally:
                                response.dispose()
                    else:
                        results = page.evaluate(
                            BROWSER_BATCH,
                            {
                                "jobs": jobs,
                                "concurrency": concurrency,
                                "interval": 500,
                            },
                        )
                    statuses = [result["status"] for result in results if result]
                    summary = {
                        "transport": transport,
                        "concurrency": concurrency,
                        "seconds": round(time.monotonic() - start, 3),
                        "statuses": statuses,
                    }
                    sample["transports"].append(summary)
                    if len(statuses) != 5 or any(status != 200 for status in statuses):
                        report["blocker"] = "transport_failed_or_throttled"
                        break
                    if any(login_response(url, result["text"]) for result in results):
                        report["blocker"] = "transport_login_response"
                        break
                    actual = {
                        kind: json.loads(result["text"])
                        for kind, result in zip(sorted(KINDS), results, strict=True)
                    }
                    summary["equal_payloads"] = compare_payloads(captured, actual)
                    summary["base_changed_keys"] = sorted(
                        key
                        for key in set(captured["base"]) | set(actual["base"])
                        if captured["base"].get(key) != actual["base"].get(key)
                    )
                    if baseline_fields is not None:
                        try:
                            parsed = extract_profile(
                                **actual, rendered_text=rendered_text, rendered_html=rendered_html
                            )
                            summary["equal_parsed_fields"] = parsed == baseline_fields
                        except Exception:
                            summary["equal_parsed_fields"] = False
                    print(
                        f"Sample {number}: {transport}, concurrency {concurrency}, "
                        f"{summary['seconds']}s, equal response kinds "
                        f"{sum(summary['equal_payloads'].values())}/5.",
                        flush=True,
                    )
                if report.get("blocker"):
                    break
            report["script_analysis"] = scripts
            report["complete"] = experiment_complete(report, len(samples))
        finally:
            (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            context.close()
            browser.close()
    print(
        "Bounded experiment finished; private report: output/performance-probe/report.json",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Experiment cancelled; collection checkpoint unchanged.")
        raise SystemExit(130) from None
    except Exception:
        print("Experiment stopped on a configuration, authentication, or response error.")
        raise SystemExit(3) from None
