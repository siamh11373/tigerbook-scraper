import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from test_tigernet_fields import source

from tigerbook_scraper.config import TARGET
from tigerbook_scraper.errors import ExtractionError
from tigerbook_scraper.fetch import Fetcher, Pacer
from tigerbook_scraper.models import ProfileRef
from tigerbook_scraper.tigernet import TigerNetAdapter, all_topics, response_kind


def test_community_pagination_collects_all_eight_memberships():
    def payload(page, ids, more):
        return {
            "page": page,
            "topics": [{"id": i} for i in ids],
            "total_items": 8,
            "has_next_page": more,
        }

    pages = [payload(2, [4, 5, 6], True), payload(3, [7, 8], False)]
    calls = []

    def get(url):
        calls.append(parse_qs(urlsplit(url).query)["page"][0])
        return json.dumps(pages.pop(0)), "application/json"

    result = all_topics(
        payload(1, [1, 2, 3], True),
        TARGET + "/synthetic?page=1&per_page=3",
        SimpleNamespace(get=get),
    )
    assert len(result["topics"]) == 8 and not result["has_next_page"]
    assert calls == ["2", "3"]


def test_community_count_mismatch_does_not_pass():
    with pytest.raises(ExtractionError):
        all_topics(
            {"page": 1, "topics": [], "total_items": 8, "has_next_page": False},
            TARGET + "/synthetic?page=1",
            None,
        )


def test_listing_uses_source_ids_and_leaves_coverage_unproven():
    fetcher = SimpleNamespace(
        get=lambda _: (
            json.dumps({"users": [{"id": 1}, {"id": 2}], "total_items": 3}),
            "application/json",
        )
    )
    adapter = TigerNetAdapter(
        None, fetcher, {"listing_url": TARGET + "/frontoffice/api/users?page=1&per_page=2"}
    )
    result = adapter.list_page(None)
    assert [ref.id for ref in result.profiles] == ["1", "2"]
    assert parse_qs(urlsplit(result.next_cursor).query)["page"] == ["2"]
    assert not result.exhaustive


def test_response_matching_checks_subject_id_not_stale_route_prefix():
    assert response_kind(TARGET + "/users/99/users/2/followed_topics?page=1", "2") == "topics"
    assert response_kind(TARGET + "/users/99/users/3/followed_topics?page=1", "2") is None
    assert response_kind("https://other.test/users/1/badges.json", "1") is None


def test_browser_profile_captures_observed_responses_without_api_url_guessing(browser):
    context = browser.new_context()
    values = source()
    values["base"]["photo_url"] = TARGET + "/synthetic-photo.png"
    paths = {
        "/private/frontoffice/users/profiles/1": values["base"],
        "/users/1/user_profiles/header_data": values["header"],
        "/users/1/users/1/data": values["body"],
        "/users/1/users/1/followed_topics?page=1&per_page=3": {
            **values["topics"],
            "page": 1,
            "total_items": 0,
        },
        "/users/1/badges.json": values["badges"],
    }
    visited = []

    def route(r):
        path = r.request.url.removeprefix(TARGET)
        visited.append(path)
        if path == "/users/1":
            script = ";".join(f"fetch({json.dumps(p)})" for p in paths)
            r.fulfill(
                content_type="text/html; charset=utf-8",
                body=(
                    f'<body>Synthetic 東京<img src="{values["base"]["photo_url"]}">'
                    f"<script>{script}</script></body>"
                ),
            )
        elif path in paths:
            r.fulfill(content_type="application/json", body=json.dumps(paths[path]))
        else:
            r.abort()

    context.route("**/*", route)
    fetcher = Fetcher(
        context.request, TARGET, lambda: pytest.fail("Unexpected renewal"), pacer=Pacer(interval=0)
    )
    adapter = TigerNetAdapter(context.new_page(), fetcher, {})
    ref = ProfileRef("1", TARGET + "/users/1")
    fields = adapter.profile(ref)
    assert fields["Custom/Brand new field"] == "東京"
    assert fields["Profile/photo_url"] == TARGET + "/synthetic-photo.png"
    assert "/synthetic-photo.png" not in visited
    assert adapter.audit(ref, fields)
    assert not adapter.field_coverage_verified
    assert set(paths).issubset(visited)
    context.close()
