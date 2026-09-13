import json
from urllib.parse import urlsplit

from tigerbook_scraper.config import TARGET
from tigerbook_scraper.inspection import contains_secret, inspect_directory


def test_token_payloads_are_excluded():
    assert contains_secret({"token": "synthetic"})
    assert contains_secret({"nested": [{"access_token": "synthetic"}]})
    assert not contains_secret({"users": [{"id": 1, "fields": []}]})


def test_inspection_follows_observed_links_and_next_button(browser, tmp_path):
    context = browser.new_context()
    visits = []

    def route(r):
        path = urlsplit(r.request.url).path
        visits.append(path)
        if path == "/synthetic-directory":
            body = """<button aria-label="Next page"
                onclick="fetch('/frontoffice/api/users?page=2')">Next</button>
                <a href="/users/1">Synthetic</a><a href="/users/1">Duplicate</a>
                <a href="/users/2">Synthetic</a><a href="/users/3">Synthetic</a>
                <script>fetch('/synthetic-token-service')</script>"""
            r.fulfill(content_type="text/html", body=body)
        elif path == "/frontoffice/api/users":
            r.fulfill(content_type="application/json", body='{"total_items":3,"users":[]}')
        elif path == "/synthetic-token-service":
            r.fulfill(content_type="application/json", body='{"token":"synthetic-token"}')
        elif path in ("/users/1", "/users/2", "/users/3"):
            r.fulfill(content_type="text/html", body="Synthetic profile")
        else:
            r.abort()

    context.route("**/*", route)
    inspect_directory(context.new_page(), TARGET + "/synthetic-directory", tmp_path, settle_ms=100)
    assert json.loads((tmp_path / "inspection-summary.json").read_text())["profile_samples"] == 3
    assert (tmp_path / "directory-page-2-responses.json").exists()
    for i in range(1, 4):
        assert visits.count(f"/users/{i}") == 1
        assert (tmp_path / f"profile-{i}.html").exists()
    assert "synthetic-token" not in (tmp_path / "responses.json").read_text()
    context.close()
