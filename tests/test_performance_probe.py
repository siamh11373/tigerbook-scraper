import json
from types import SimpleNamespace

import pytest

from tigerbook_scraper.performance_probe import (
    BROWSER_BATCH,
    compare_payloads,
    experiment_complete,
    profile_pacer,
    summarize_overlap,
)


def test_incomplete_samples_never_mark_experiment_complete():
    report = {"samples": [{"blocker": "incomplete_observed_responses"}]}
    assert not experiment_complete(report, 1)
    report["samples"] = [
        {
            "transports": [
                {"transport": mode, "concurrency": concurrency, "statuses": [200] * 5}
                for mode, concurrency in (
                    ("request_context", 1),
                    ("browser_fetch", 1),
                    ("browser_fetch", 3),
                )
            ]
        }
    ]
    assert experiment_complete(report, 1)
    assert not experiment_complete(report, 3)
    report["samples"][0]["transports"][0]["statuses"][0] = 429
    assert not experiment_complete(report, 1)


def test_profile_pacer_accepts_playwright_second_argument():
    calls = []
    request = SimpleNamespace(
        resource_type="xhr", url="https://tigernet.princeton.edu/users/1/badges.json"
    )
    route = SimpleNamespace(request=request, continue_=lambda: calls.append("continued"))
    profile_pacer("1")(route, request)
    assert calls == ["continued"]


def test_overlap_counts_types_and_paths_without_printing_values():
    result = summarize_overlap({"base": {"a": 1}, "header": {"a": "1"}})
    assert result["base"]["unique_path_value_leaves"] == 1
    assert compare_payloads({"base": {"a": 1}}, {"base": {"a": "1"}})["base"] is False


@pytest.mark.parametrize("concurrency", [1, 3])
def test_browser_fetch_uses_observed_jobs_and_preserves_json(browser, concurrency):
    context = browser.new_context()
    page = context.new_page()
    page.route("https://example.test/", lambda route: route.fulfill(body="<html></html>"))
    page.route(
        "https://example.test/data*",
        lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({"field": "東京", "records": [1, 2]})
        ),
    )
    page.goto("https://example.test/")
    results = page.evaluate(
        BROWSER_BATCH,
        {
            "jobs": [{"url": "https://example.test/data", "headers": {}} for _ in range(5)],
            "concurrency": concurrency,
            "interval": 5,
        },
    )
    assert len(results) == 5
    assert all(result["status"] == 200 for result in results)
    assert all(json.loads(result["text"])["field"] == "東京" for result in results)
    context.close()


def test_browser_fetch_stops_after_429(browser):
    context = browser.new_context()
    page = context.new_page()
    page.route("https://example.test/", lambda route: route.fulfill(body="<html></html>"))
    page.route(
        "https://example.test/data*", lambda route: route.fulfill(status=429, body="limited")
    )
    page.goto("https://example.test/")
    results = page.evaluate(
        BROWSER_BATCH,
        {
            "jobs": [{"url": "https://example.test/data", "headers": {}} for _ in range(5)],
            "concurrency": 1,
            "interval": 5,
        },
    )
    assert [result["status"] for result in results if result] == [429]
    context.close()
