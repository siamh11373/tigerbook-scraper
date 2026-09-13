"""Real Playwright request transport against an ephemeral loopback-only server."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_fast import Gate, requests
from test_tigernet_fields import source

from tigerbook_scraper import adapter, fast
from tigerbook_scraper.models import ProfileRef
from tigerbook_scraper.state import State
from tigerbook_scraper.tigernet_fields import extract_profile


def test_async_transport_reuses_in_memory_session_and_collects_without_browser(
    tmp_path, monkeypatch
):
    values = source()
    values["topics"].update(page=1, total_items=0)
    expected = extract_profile(**values)
    templates = fast.observed_templates(requests(), "1")
    cookie_checks, auth_checks, visited = [], [], []
    payloads = {
        entry["url"].replace("{profile_id}", "1").removeprefix(fast.TARGET): values[kind]
        for kind, entry in templates.items()
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            visited.append(self.path)
            cookie_checks.append(self.headers.get("Cookie") == "synthetic-session=test-only")
            if self.path.startswith("/frontoffice/api/users?"):
                data = {"users": [{"id": 1}], "total_items": 1}
            elif self.path in payloads:
                auth_checks.append(
                    self.headers.get("Authorization") == "Bearer synthetic-test-only"
                )
                data = payloads[self.path]
            else:
                self.send_error(404)
                return
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = f"http://127.0.0.1:{server.server_port}"
    original_target = fast.TARGET
    monkeypatch.setattr(adapter, "TARGET", target)
    monkeypatch.setattr(fast, "TARGET", target)
    monkeypatch.setattr(fast, "Throttle", lambda _: Gate())
    for entry in templates.values():
        entry["url"] = entry["url"].replace(original_target, target)
        entry["headers"]["authorization"] = "Bearer synthetic-test-only"
    setup = {
        "session": {
            "cookies": [
                {
                    "name": "synthetic-session",
                    "value": "test-only",
                    "domain": "127.0.0.1",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ],
            "origins": [],
        },
        "templates": templates,
        "base_keys": {"name"},
        "references": [(ProfileRef("1", target + "/users/1"), expected)],
    }
    state = State(
        tmp_path / "run.sqlite",
        {
            "target": target,
            "account": "synthetic",
            "scope": "fast-sample-1",
            "limit": 1,
        },
    )
    try:
        asyncio.run(
            fast.session_run(
                state,
                setup,
                {"listing_url": target + "/frontoffice/api/users?page=1&per_page=1"},
                limit=1,
                ceiling=1,
                progress=lambda _: None,
            )
        )
        assert state.counts()["complete"] == 1
        assert state.get("direct_browser_comparisons") == 1
        assert all(cookie_checks) and all(auth_checks) and auth_checks
        assert "/users/1" not in visited
        assert list(state.records())[0][2]["Custom/Brand new field"] == "東京"
        assert "synthetic-test-only" not in " ".join(
            row[0] for row in state.db.execute("select value from meta")
        )
    finally:
        state.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
