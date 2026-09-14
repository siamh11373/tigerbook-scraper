"""Real Playwright request transport against an ephemeral loopback-only server."""

import asyncio
import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_fast import Gate, requests
from test_tigernet_fields import source

from tigerbook_scraper import adapter, fast
from tigerbook_scraper.models import ProfileRef
from tigerbook_scraper.state import State
from tigerbook_scraper.tigernet_fields import extract_profile


@pytest.mark.parametrize("reference_mismatch", [False, True])
@pytest.mark.parametrize("session_count", [1, 2])
def test_async_transport_reuses_in_memory_session_and_collects_without_browser(
    tmp_path, monkeypatch, reference_mismatch, session_count
):
    values_by_id = {}
    for profile_id in range(1, session_count + 1):
        values = source()
        values["base"].update(id=profile_id, name=f"Synthetic {profile_id}")
        values["topics"].update(page=1, total_items=0)
        values_by_id[str(profile_id)] = values
    templates = fast.observed_templates(requests(), "1")
    cookie_checks, auth_checks, visited = [], [], []
    payloads = {}
    for profile_id, values in values_by_id.items():
        for kind, entry in templates.items():
            path = entry["url"].replace("{profile_id}", profile_id).removeprefix(fast.TARGET)
            payloads[path] = (profile_id, values[kind])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            visited.append(self.path)
            if self.path.startswith("/frontoffice/api/users?"):
                cookie_checks.append(
                    "synthetic-session=session-0" in self.headers.get("Cookie", "")
                )
                data = {
                    "users": [{"id": profile_id} for profile_id in range(1, session_count + 1)],
                    "total_items": session_count,
                }
            elif self.path in payloads:
                profile_id, data = payloads[self.path]
                expected_session = 0 if session_count == 1 else int(profile_id) % session_count
                cookie_checks.append(
                    f"synthetic-session=session-{expected_session}"
                    in self.headers.get("Cookie", "")
                )
                auth_checks.append(
                    self.headers.get("Authorization") == f"Bearer synthetic-{expected_session}"
                )
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
    monkeypatch.setattr(fast, "Throttle", lambda _start, _ceiling: Gate())
    for entry in templates.values():
        entry["url"] = entry["url"].replace(original_target, target)
    setups = []
    for session_index in range(session_count):
        session_templates = copy.deepcopy(templates)
        for entry in session_templates.values():
            entry["headers"]["authorization"] = f"Bearer synthetic-{session_index}"
        reference_id = "1" if session_count == 1 else str(session_count - session_index)
        reference = extract_profile(**values_by_id[reference_id])
        if reference_mismatch:
            reference = {**reference, "Synthetic mismatch": "browser"}
        setups.append(
            {
                "session": {
                    "cookies": [
                        {
                            "name": "synthetic-session",
                            "value": f"session-{session_index}",
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
                "templates": session_templates,
                "references": [
                    (
                        ProfileRef(reference_id, target + "/users/" + reference_id),
                        reference,
                    )
                ],
            }
        )
    setup_input = setups[0] if session_count == 1 else setups
    state = State(
        tmp_path / "run.sqlite",
        {
            "target": target,
            "account": "synthetic",
            "scope": f"fast-sample-{session_count}",
            "limit": session_count,
        },
    )
    try:
        asyncio.run(
            fast.session_run(
                state,
                setup_input,
                {
                    "listing_url": (
                        target + f"/frontoffice/api/users?page=1&per_page={session_count}"
                    )
                },
                limit=session_count,
                start_rate=1,
                ceiling=1,
                progress=lambda _: None,
            )
        )
        assert state.counts()["complete"] == session_count
        assert state.get("direct_browser_comparisons") == session_count
        assert state.get("direct_browser_mismatches") == int(reference_mismatch) * session_count
        assert state.get("browser_sessions") == session_count
        assert all(cookie_checks) and all(auth_checks) and auth_checks
        for profile_id in range(1, session_count + 1):
            assert any(
                path.startswith(f"/private/frontoffice/users/profiles/{profile_id}")
                for path in visited
            )
        assert all(record[2]["Custom/Brand new field"] == "東京" for record in state.records())
        assert "synthetic-" not in " ".join(
            row[0] for row in state.db.execute("select value from meta")
        )
    finally:
        state.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
