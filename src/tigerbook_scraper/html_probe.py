"""Bounded raw-HTML feasibility check; never exports a claimed complete record."""

import json
import os
import sqlite3
import time
from html.parser import HTMLParser
from pathlib import Path

from .config import TARGET, Credentials, load_credentials
from .local_env import read_env_file


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.scripts = []
        self.links = []
        self.script = None
        self.json_objects = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script = []
        for key in ("href", "src", "content"):
            if attrs.get(key):
                self.links.append(attrs[key])

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        else:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            value = "".join(self.script)
            self.scripts.append(value)
            try:
                self.json_objects.append(json.loads(value))
            except ValueError:
                pass
            self.script = None


def strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str) and value.strip():
        yield " ".join(value.split())


def compare_html(html, fields):
    """Presence is necessary, not sufficient: never declare field fidelity here."""
    doc = Document()
    doc.feed(html)
    corpus = " ".join(
        " ".join(part.split())
        for part in [*doc.text, *doc.links, *doc.scripts, *strings(doc.json_objects)]
    )
    checked = matched = 0
    missing = []
    for label, value in fields.items():
        leaves = list(strings(value))
        if not leaves:
            continue
        checked += 1
        if all(leaf in corpus for leaf in leaves):
            matched += 1
        else:
            missing.append(label)
    return {
        "html_bytes": len(html.encode("utf-8")),
        "script_count": len(doc.scripts),
        "standalone_json_blocks": len(doc.json_objects),
        "fields_checked": checked,
        "fields_with_all_string_values_present": matched,
        "missing_field_labels": missing,
        "full_record_verified": False,
        "conclusion": "missing_reference_values" if missing else "needs_structural_validation",
    }


def run():
    from playwright.sync_api import sync_playwright

    from .adapter import load_contract, target_url
    from .auth import authenticate
    from .fetch import login_response

    os.umask(0o077)
    configured = any(
        os.environ.get(key) is not None for key in ("TIGERNET_USERNAME", "TIGERNET_PASSWORD")
    )
    values = None if configured else read_env_file(Path(".env.local"))
    credentials = (
        Credentials(*values) if values else load_credentials(Path("credentials.local.json"))
    )
    path = Path("output/fast-full/run.sqlite").resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        identity = json.loads(
            db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0]
        )
        if identity["account"] != credentials.account_key or identity["target"] != TARGET:
            raise ValueError("Reference account or target mismatch.")
        rows = db.execute(
            "SELECT id,url,fields FROM profiles WHERE status='complete' ORDER BY length(fields),id"
        ).fetchall()
    if not rows:
        raise ValueError("No completed reference profiles available.")
    samples = [rows[index] for index in sorted({0, len(rows) // 2, len(rows) - 1})]
    contract = load_contract(Path("private/site-contract.json"))
    report = {"reference": "saved permitted records; may differ if source changed", "samples": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        try:
            authenticate(context.new_page(), credentials, allow_interactive=True)
            # Verify directory access independently of the login redirect.
            response = context.request.get(target_url(contract["listing_url"]), max_redirects=0)
            try:
                if response.status != 200 or not isinstance(response.json().get("users"), list):
                    raise ValueError("Protected directory verification failed.")
            finally:
                response.dispose()
            for number, (_, url, saved) in enumerate(samples, 1):
                time.sleep(1)
                response = context.request.get(
                    target_url(url),
                    headers={"accept": "text/html"},
                    max_redirects=0,
                    timeout=30000,
                )
                try:
                    html = response.text()
                    if response.status != 200 or login_response(response.url, html):
                        raise ValueError("HTML fetch blocked or unauthenticated; probe stopped.")
                    if "text/html" not in response.headers.get("content-type", ""):
                        raise ValueError("Profile response is not HTML.")
                    result = compare_html(html, json.loads(saved))
                    report["samples"].append(result)
                    print(
                        f"Sample {number}: {result['fields_with_all_string_values_present']}/"
                        f"{result['fields_checked']} fields have their string values in raw HTML; "
                        f"{result['standalone_json_blocks']} JSON blocks.",
                        flush=True,
                    )
                finally:
                    response.dispose()
        finally:
            context.close()
            browser.close()
    output = Path("output/html-probe")
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Probe finished. Private report: output/html-probe/report.json", flush=True)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("HTML probe cancelled; saved collection unchanged.")
        raise SystemExit(130) from None
    except Exception:
        print("HTML probe stopped: authentication, response, or configuration check failed.")
        raise SystemExit(3) from None
