"""Invented fixtures exercise the adapter; these are NOT TigerNet selectors/endpoints."""

import json
from types import SimpleNamespace

import pytest

from tigerbook_scraper.adapter import SiteAdapter, load_contract, target_url
from tigerbook_scraper.config import TARGET
from tigerbook_scraper.errors import ConfigurationError, DiscoveryError, ExtractionError
from tigerbook_scraper.fetch import Pacer
from tigerbook_scraper.models import ProfileRef


def contract():
    return {
        "target": TARGET,
        "mode": "dom",
        "evidence": "Synthetic test only; no live-site claim",
        "listing_url": TARGET + "/synthetic-list",
        "cards": ".card",
        "profile_link": "a",
        "next_link": ".next",
        "total": ".total",
        "exhaustive": True,
        "field_coverage_evidence": "Synthetic fixture reviewed in this test",
        "audit": {
            "root": "#profile",
            "sections": "section",
            "heading": "h2",
            "rows": "dl",
            "label": "dt",
            "value": "dd",
        },
    }


def adapter_on_html(browser, html, config=None):
    context = browser.new_context()
    context.route(
        "**/*", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body=html)
    )
    fetcher = SimpleNamespace(pacer=Pacer(interval=0), attempts=2)
    return SiteAdapter(context.new_page(), fetcher, config or contract()), context


def test_dom_listing_uses_urls_not_names_and_relative_continuation(browser):
    adapter, context = adapter_on_html(
        browser,
        """
        <span class=total>2</span>
        <div class=card><a href='/synthetic-person/1'>Same name</a></div>
        <div class=card><a href='/synthetic-person/2'>Same name</a></div>
        <a class=next href='?page=2'>Next</a>
    """,
    )
    result = adapter.list_page(None)
    assert len(set(ref.id for ref in result.profiles)) == 2
    assert result.next_cursor == TARGET + "/synthetic-list?page=2"
    assert result.total == 2
    context.close()


def test_dynamic_dom_fields_keep_repetitions_links_and_photo_urls(browser):
    adapter, context = adapter_on_html(
        browser,
        """
        <main id=profile><section><h2>Contact</h2>
        <dl><dt>Unexpected label</dt><dd>東京, "quoted"</dd></dl>
        <dl><dt>Links</dt><dd><a href='https://example.test'>Site</a>
        <img src='https://example.test/photo.png'></dd></dl>
        <dl><dt>Affiliation</dt><dd>First</dd></dl>
        <dl><dt>Affiliation</dt><dd>Second</dd></dl>
        <dl><dt>Missing</dt><dd></dd></dl>
        </section></main>
    """,
    )
    ref = ProfileRef("1", TARGET + "/synthetic-person/1")
    fields = adapter.profile(ref)
    assert fields["Contact/Unexpected label"] == '東京, "quoted"'
    assert fields["Contact/Affiliation"] == ["First", "Second"]
    assert fields["Contact/Links"]["images"] == ["https://example.test/photo.png"]
    assert fields["Contact/Missing"] == ""
    assert adapter.audit(ref, fields)
    del adapter.contract["field_coverage_evidence"]
    assert not adapter.audit(ref, fields)
    context.close()


def test_unrecognized_profile_is_not_empty_success(browser):
    adapter, context = adapter_on_html(browser, "<main id=profile>Unexpected content</main>")
    with pytest.raises(ExtractionError):
        adapter.profile(ProfileRef("1", TARGET + "/synthetic-person/1"))
    context.close()


def test_structured_listing_and_nested_records():
    config = {
        **contract(),
        "mode": "json",
        "records_path": ["people"],
        "id_path": ["id"],
        "url_path": ["url"],
        "next_path": ["next"],
        "total_path": ["total"],
        "profile_path": ["profile"],
    }
    payload = {"people": [{"id": 1, "url": "/synthetic-person/1"}], "next": None, "total": 1}
    fetcher = SimpleNamespace(get=lambda _: (json.dumps(payload), "application/json"))
    adapter = SiteAdapter(None, fetcher, config)
    listing = adapter.list_page(None)
    assert listing.profiles[0].id == "1"
    nested = {"Education": [{"Degree": "AB", "Year": "0012"}, {"Degree": "MS", "Year": None}]}
    payload = {"profile": nested}
    assert adapter.profile(listing.profiles[0]) == nested
    payload = {"unrecognized": []}
    with pytest.raises(DiscoveryError):
        adapter.list_page(None)


def test_no_contract_means_no_invented_integration(tmp_path):
    with pytest.raises(ConfigurationError, match="Authenticated inspection"):
        load_contract(tmp_path / "absent.json")
    with pytest.raises(ExtractionError):
        target_url("https://unapproved.test/people")
