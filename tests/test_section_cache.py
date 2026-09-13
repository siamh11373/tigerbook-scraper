import sqlite3

import pytest

from tigerbook_scraper.section_cache import SectionCache


def test_successful_sections_survive_interruption(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    with sqlite3.connect(path) as db:
        cache = SectionCache(db, clock=lambda: 10)
        cache.put("1", "header", {"name": "Synthetic Üser"})
        cache.put("1", "topics:2", {"topics": [{"id": 3}]})
        # Another request failed before a full record could be committed.
    with sqlite3.connect(path) as db:
        resumed = SectionCache(db, clock=lambda: 20)
        assert resumed.load("1") == {
            "header": {"name": "Synthetic Üser"},
            "topics:2": {"topics": [{"id": 3}]},
        }
        resumed.put("1", "body", {"new_field": ["a", "b"]})
        assert len(resumed.load("1")) == 3


def test_oldest_section_expires_entire_profile():
    db = sqlite3.connect(":memory:")
    current = [10]
    cache = SectionCache(db, max_age_seconds=20, clock=lambda: current[0])
    cache.put("1", "header", {"name": "Old"})
    current[0] = 25
    cache.put("1", "body", {"field": "New"})
    cache.put("2", "header", {"name": "Other"})
    current[0] = 30
    assert cache.load("1") == {}
    assert (
        db.execute("SELECT count(*) FROM profile_sections_v1 WHERE profile_id='1'").fetchone()[0]
        == 0
    )
    assert cache.load("2") == {"header": {"name": "Other"}}


@pytest.mark.parametrize("body", ["{broken", "[]", '{"value": NaN}'])
def test_corruption_discards_every_section(body):
    db = sqlite3.connect(":memory:")
    cache = SectionCache(db, clock=lambda: 10)
    cache.put("1", "header", {"name": "Synthetic"})
    db.execute("INSERT INTO profile_sections_v1 VALUES(?,?,?,?)", ("1", "body", 10, body))
    db.commit()
    assert cache.load("1") == {}
    assert db.execute("SELECT count(*) FROM profile_sections_v1").fetchone()[0] == 0


def test_discard_is_idempotent_and_scoped_to_profile():
    db = sqlite3.connect(":memory:")
    cache = SectionCache(db)
    cache.put("1", "header", {"name": "First"})
    cache.put("2", "header", {"name": "Second"})
    cache.discard("1")
    cache.discard("1")
    assert cache.load("1") == {}
    assert cache.load("2") == {"header": {"name": "Second"}}


def test_upsert_and_invalid_body_do_not_destroy_successful_sections():
    db = sqlite3.connect(":memory:")
    cache = SectionCache(db)
    cache.put("1", "body", {"value": 1})
    cache.put("1", "body", {"value": 2})
    with pytest.raises(ValueError):
        cache.put("1", "body", {"value": float("nan")})
    assert cache.load("1") == {"body": {"value": 2}}


def test_clock_rollback_invalidates_snapshot():
    db = sqlite3.connect(":memory:")
    cache = SectionCache(db, clock=lambda: 20)
    cache.put("1", "body", {"value": 1})
    assert SectionCache(db, clock=lambda: 10).load("1") == {}


@pytest.mark.parametrize("age", [0, -1, float("inf"), float("nan")])
def test_reject_invalid_ttl(age):
    with pytest.raises(ValueError):
        SectionCache(sqlite3.connect(":memory:"), max_age_seconds=age)


def profile_harness(cache, values, get):
    from types import SimpleNamespace

    from test_fast import requests

    from tigerbook_scraper.fast import DirectProfiles, observed_templates

    templates = observed_templates(requests(), "1")
    urls = {entry["url"].replace("{profile_id}", "1"): kind for kind, entry in templates.items()}

    async def request(url, headers=None):
        return await get(urls[url], values)

    return DirectProfiles(SimpleNamespace(get=request), templates, {"name"}, cache=cache)


def profile_values():
    from test_tigernet_fields import source

    values = source()
    values["topics"].update(page=1, total_items=0)
    return values


def test_direct_profile_retry_reuses_successes_after_fresh_base_check():
    import asyncio

    from tigerbook_scraper.errors import FetchError
    from tigerbook_scraper.models import ProfileRef

    async def run():
        cache = SectionCache(sqlite3.connect(":memory:"))
        values = profile_values()
        calls = []
        fail = [True]

        async def get(kind, responses):
            calls.append(kind)
            if kind == "topics" and fail[0]:
                # Let the other successful requests save their response bodies.
                await asyncio.sleep(0)
                raise FetchError("Synthetic interrupted request")
            return responses[kind]

        collector = profile_harness(cache, values, get)
        ref = ProfileRef("1", "https://example.test/users/1")
        with pytest.raises(FetchError):
            await collector.profile(ref)
        assert set(cache.load("1")) == {"base", "header", "body", "badges"}
        calls.clear()
        fail[0] = False
        result = await collector.profile(ref)
        assert calls == ["base", "topics"]
        assert result["Custom/Brand new field"] == "東京"
        assert "Custom/Admin field" not in result
        collector.discard("1")
        assert cache.load("1") == {}

    asyncio.run(run())


def test_direct_profile_base_change_invalidates_cached_sections():
    import asyncio

    from tigerbook_scraper.models import ProfileRef

    async def run():
        cache = SectionCache(sqlite3.connect(":memory:"))
        values = profile_values()
        for kind in ("base", "header", "body", "topics", "badges"):
            cache.put("1", kind, values[kind])
        values["base"]["name"] = "Changed"
        values["body"]["center"][0]["data"][0]["value"] = "Updated"
        calls = []

        async def get(kind, responses):
            calls.append(kind)
            return responses[kind]

        collector = profile_harness(cache, values, get)
        result = await collector.profile(ProfileRef("1", "https://example.test/users/1"))
        assert calls[0] == "base"
        assert sorted(calls) == ["badges", "base", "body", "header", "topics"]
        assert result["Profile/name"] == "Changed"
        assert result["Custom/Brand new field"] == "Updated"

    asyncio.run(run())


def test_direct_profile_invalid_extraction_discards_cached_bodies():
    import asyncio

    from tigerbook_scraper.errors import ExtractionError
    from tigerbook_scraper.models import ProfileRef

    async def run():
        cache = SectionCache(sqlite3.connect(":memory:"))
        values = profile_values()
        values["body"]["center"][0]["type"] = "unrecognized_synthetic_structure"

        async def get(kind, responses):
            return responses[kind]

        collector = profile_harness(cache, values, get)
        with pytest.raises(ExtractionError):
            await collector.profile(ProfileRef("1", "https://example.test/users/1"))
        assert cache.load("1") == {}

    asyncio.run(run())
