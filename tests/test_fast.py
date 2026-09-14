import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from test_tigernet_fields import source

from tigerbook_scraper.config import TARGET
from tigerbook_scraper.errors import (
    AccessBlocked,
    AuthenticationError,
    ConfigurationError,
    ExtractionError,
    FetchError,
)
from tigerbook_scraper.fast import (
    Client,
    DirectProfiles,
    SessionPool,
    Throttle,
    collect_direct,
    observed_templates,
    together,
)
from tigerbook_scraper.models import ProfileRef
from tigerbook_scraper.state import State


def requests():
    paths = {
        "base": "/private/frontoffice/users/profiles/1",
        "header": "/users/1/user_profiles/header_data",
        "body": "/users/99/users/1/data",
        "topics": "/users/99/users/1/followed_topics?page=1&per_page=3",
        "badges": "/users/1/badges.json",
    }
    return {
        key: {"url": TARGET + path, "method": "GET", "headers": {"accept": "application/json"}}
        for key, path in paths.items()
    }


def test_templates_only_use_observed_get_requests():
    templates = observed_templates(requests(), "1")
    assert templates["body"]["url"] == TARGET + "/users/99/users/{profile_id}/data"
    assert templates["topics"]["url"].startswith(TARGET + "/users/99/users/{profile_id}/")
    invalid = requests()
    invalid["base"]["url"] = "https://other.test/private/frontoffice/users/profiles/1"
    with pytest.raises(ExtractionError):
        observed_templates(invalid, "1")
    invalid = requests()
    invalid["body"]["method"] = "POST"
    with pytest.raises(ConfigurationError):
        observed_templates(invalid, "1")


def test_shared_gate_spaces_requests_and_honors_global_cooldown():
    async def run():
        clock = [0.0]

        async def sleep(seconds):
            clock[0] += seconds
            await asyncio.sleep(0)

        gate = Throttle(20, 40, clock=lambda: clock[0], sleep=sleep)
        await gate.wait()
        await gate.wait()
        assert clock[0] == 0.05
        for _ in range(100):
            gate.success()
        assert gate.rate == 22.0
        gate.failure()
        assert gate.rate == pytest.approx(17.6)
        gate.cooldown(10)
        gate.cooldown(10)
        await gate.wait()
        assert clock[0] >= 10.05 and gate.rate == pytest.approx(8.8)
        assert gate.throttles == 2 and gate.transient_failures == 1
        assert gate.rate_decreases == 2
        assert gate.starts == 3
        clock[0] = 31
        for _ in range(100):
            gate.success()
        assert gate.rate == pytest.approx(10.8)

    asyncio.run(run())


def test_throttle_burst_does_not_create_a_rolling_decrease_window():
    clock = [0.0]
    gate = Throttle(20, 40, clock=lambda: clock[0])
    gate.cooldown(1)
    assert gate.rate == 10
    clock[0] = 29
    gate.cooldown(1)
    assert gate.rate == 10
    clock[0] = 31
    gate.cooldown(1)
    assert gate.rate == 5


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status, self.url = status, TARGET + "/synthetic"
        self.body = json.dumps({"ok": True}) if body is None else body
        self.headers = {"content-type": "application/json", **(headers or {})}
        self.disposed = False

    async def text(self):
        return self.body

    async def dispose(self):
        self.disposed = True


class Gate:
    rate = 1.0
    ceiling = 1.0
    starts = throttles = 0
    transient_failures = 0
    rate_decreases = 0

    async def wait(self):
        self.starts += 1

    def success(self):
        pass

    def cooldown(self, delay):
        self.delay = delay
        self.throttles += 1

    def failure(self):
        self.transient_failures += 1


@pytest.mark.parametrize(
    "status,body,error",
    [
        (403, "denied", AccessBlocked),
        (401, "expired", AuthenticationError),
        (200, '<input type="password">', AuthenticationError),
        (200, "invalid-json", ExtractionError),
        (429, "limited", AccessBlocked),
    ],
)
def test_request_failures_are_safe_and_responses_released(status, body, error):
    async def run():
        response = Response(status, body, {"retry-after": "301"})

        async def get(*args, **kwargs):
            return response

        gate = Gate()
        with pytest.raises(error):
            await Client(SimpleNamespace(get=get), gate).get(TARGET + "/synthetic")
        assert response.disposed
        if status == 429:
            assert gate.delay >= 301

    asyncio.run(run())


def test_request_operation_has_caller_side_timeout():
    async def run():
        async def never_returns(*args, **kwargs):
            await asyncio.Event().wait()

        gate = Gate()
        client = Client(
            SimpleNamespace(get=never_returns),
            gate,
            attempts=1,
            operation_timeout=0.01,
        )
        with pytest.raises(FetchError, match="timed out"):
            await client.get(TARGET + "/synthetic")
        assert gate.transient_failures == 1

    asyncio.run(run())


def test_response_body_and_disposal_cannot_stall_request():
    class SlowResponse(Response):
        async def text(self):
            await asyncio.Event().wait()

        async def dispose(self):
            await asyncio.Event().wait()

    async def run():
        response = SlowResponse()

        async def get(*args, **kwargs):
            return response

        with pytest.raises(FetchError, match="timed out"):
            await Client(
                SimpleNamespace(get=get),
                Gate(),
                attempts=1,
                operation_timeout=0.01,
                disposal_timeout=0.01,
            ).get(TARGET + "/synthetic")

    asyncio.run(run())


def test_direct_profiles_preserve_sections_and_complete_community_pages():
    async def run():
        values = source()
        templates = observed_templates(requests(), "1")
        data = {
            entry["url"].replace("{profile_id}", "1"): values[kind]
            for kind, entry in templates.items()
        }
        data[templates["topics"]["url"].replace("{profile_id}", "1")] = {
            "topics": [{"id": 1}],
            "page": 1,
            "total_items": 2,
            "has_next_page": True,
        }
        calls = []

        async def get(url, headers=None):
            calls.append(url)
            if parse_qs(urlsplit(url).query).get("page") == ["2"]:
                return {"topics": [{"id": 2}], "page": 2, "total_items": 2, "has_next_page": False}
            return data[url]

        profiles = DirectProfiles(SimpleNamespace(get=get), templates)
        result = await profiles.profile(ProfileRef("1", TARGET + "/users/1"))
        assert result["Profile/name"] == "Synthetic"
        assert result["Custom/Brand new field"] == "東京"
        assert "Custom/Admin field" not in result
        assert [record["id"] for record in result["Profile/Alumni Communities"]] == [1, 2]
        assert len(calls) == 6
        values["base"]["id"] = 2
        with pytest.raises(ExtractionError, match="identity"):
            await profiles.profile(ProfileRef("1", TARGET + "/users/1"))

    asyncio.run(run())


def test_session_pool_partitions_profiles_with_shared_safety_limits():
    async def run():
        visited = [[], []]

        class Profiles:
            def __init__(self, index):
                self.index = index

            async def profile(self, ref):
                visited[self.index].append(ref.id)
                return {"Name": "Synthetic"}

        throttle = SimpleNamespace(starts=3, throttles=1, rate=2.0, ceiling=40.0)
        slots = SimpleNamespace()
        clients = [
            SimpleNamespace(
                get=lambda *_args, **_kwargs: None,
                throttle=throttle,
                slots=slots,
            )
            for _ in range(2)
        ]
        pool = SessionPool(clients, [Profiles(0), Profiles(1)])
        for profile_id in ("1", "2", "3", "4"):
            await pool.profile(ProfileRef(profile_id, TARGET + "/users/" + profile_id))
        assert visited == [["2", "4"], ["1", "3"]]
        assert pool.throttle is throttle
        assert pool.throttle.starts == 3
        assert pool.throttle.throttles == 1
        assert pool.throttle.rate == 2
        assert pool.throttle.ceiling == 40

    asyncio.run(run())


def test_session_pool_rejects_separate_rate_or_worker_limits():
    profiles = [SimpleNamespace(), SimpleNamespace()]
    throttle = SimpleNamespace()
    slots = SimpleNamespace()
    with pytest.raises(ConfigurationError, match="rate"):
        SessionPool(
            [
                SimpleNamespace(throttle=SimpleNamespace(), slots=slots),
                SimpleNamespace(throttle=SimpleNamespace(), slots=slots),
            ],
            profiles,
        )
    with pytest.raises(ConfigurationError, match="slot"):
        SessionPool(
            [
                SimpleNamespace(throttle=throttle, slots=SimpleNamespace()),
                SimpleNamespace(throttle=throttle, slots=SimpleNamespace()),
            ],
            profiles,
        )


def test_pending_workers_obey_limit_and_resume_without_duplicates(tmp_path):
    async def run():
        state = State(
            tmp_path / "run.sqlite",
            {
                "target": TARGET,
                "account": "synthetic",
                "scope": "fast-sample-3",
                "limit": 3,
            },
        )

        async def get(url):
            return {"users": [{"id": i} for i in range(1, 5)], "total_items": 4}

        active, maximum, visited = 0, 0, []

        async def profile(ref):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            visited.append(ref.id)
            active -= 1
            return {"Name": "Synthetic"}

        client = SimpleNamespace(get=get, throttle=Gate())
        contract = {"listing_url": TARGET + "/frontoffice/api/users?page=1&per_page=4"}
        await collect_direct(
            state,
            client,
            SimpleNamespace(profile=profile),
            contract,
            limit=3,
            workers=2,
            progress=lambda _: None,
        )
        assert state.counts()["complete"] == 3 and state.counts()["pending"] == 1
        assert maximum == 2
        await collect_direct(
            state,
            client,
            SimpleNamespace(profile=profile),
            contract,
            limit=3,
            workers=2,
            progress=lambda _: None,
        )
        assert len(visited) == 3
        assert not state.get("field_fidelity_verified")
        state.close()

    asyncio.run(run())


def test_fatal_error_cancels_other_work():
    async def run():
        cancelled = []

        async def blocked():
            await asyncio.sleep(0)
            raise AccessBlocked("Synthetic denial")

        async def waiting():
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.append(True)

        with pytest.raises(AccessBlocked):
            await together([blocked(), waiting()])
        assert cancelled == [True]

    asyncio.run(run())


def test_profile_extraction_failures_do_not_stop_remaining_queue(tmp_path):
    async def run():
        state = State(
            tmp_path / "run.sqlite",
            {
                "target": TARGET,
                "account": "synthetic",
                "scope": "fast-full",
                "limit": None,
            },
        )

        async def get(_url):
            return {"users": [{"id": i} for i in range(1, 13)], "total_items": 12}

        async def profile(ref):
            if ref.id != "12":
                raise ExtractionError("Synthetic incompatible profile")
            return {"Name": "Synthetic"}

        await collect_direct(
            state,
            SimpleNamespace(get=get, throttle=Gate()),
            SimpleNamespace(profile=profile),
            {"listing_url": TARGET + "/frontoffice/api/users?page=1&per_page=12"},
            workers=1,
            progress=lambda _: None,
        )
        assert state.counts() == {"pending": 0, "complete": 1, "failed": 11, "discovered": 12}
        assert list(state.records())[0][0] == "12"
        state.close()

    asyncio.run(run())


def test_inflight_request_cap_is_shared_across_profiles():
    async def run():
        active, maximum = 0, 0

        async def get(*args, **kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1
            return Response()

        client = Client(SimpleNamespace(get=get), Gate(), workers=2)
        results = await together(client.get(TARGET + "/synthetic") for _ in range(10))
        assert maximum == 2 and len(results) == 10

    asyncio.run(run())


def test_fast_header_cannot_bypass_contact_privacy():
    from tigerbook_scraper.tigernet_fields import extract_profile

    values = source()
    values["base"]["email"] = "synthetic@example.test"
    fields = extract_profile(**values, visible_base_keys={"name", "email"})
    assert "Profile/email" not in fields
    assert fields["Profile/name"] == "Synthetic"


@pytest.mark.parametrize("returned,accepted", [(100, True), (18, False)])
def test_larger_page_probe_requires_server_to_honor_size(returned, accepted):
    from tigerbook_scraper.fast import choose_listing

    async def run():
        async def get(url):
            assert parse_qs(urlsplit(url).query)["per_page"] == ["100"]
            return {"users": [{"id": i} for i in range(1, returned + 1)], "total_items": 105}

        original = TARGET + "/frontoffice/api/users?page=1&per_page=18"
        result = await choose_listing(SimpleNamespace(get=get), original, 105, {"1", "2"})
        assert (result != original) is accepted

    asyncio.run(run())


def test_repeated_session_failure_stops_and_clears_ephemeral_setup(tmp_path, monkeypatch):
    from tigerbook_scraper import fast

    state = State(
        tmp_path / "run.sqlite",
        {
            "target": TARGET,
            "account": "synthetic",
            "scope": "fast-full",
            "limit": None,
        },
    )
    setups = []

    def bootstrap(*args, **kwargs):
        value = {"session": "synthetic-session"}
        setups.append(value)
        return value

    async def fail(*args, **kwargs):
        raise AuthenticationError("Synthetic expiry")

    monkeypatch.setattr(fast, "bootstrap", bootstrap)
    monkeypatch.setattr(fast, "session_run", fail)
    with pytest.raises(AuthenticationError, match="renewal"):
        fast.collect_fast(state, None, {"mode": "tigernet"}, progress=lambda _: None)
    assert len(setups) == 2 and setups == [{}, {}]
    assert state.get("collection_mode") == "direct_requests_dynamic_header"
    assert state.get("base_field_strategy") == "per_profile_permitted_header_values"
    state.close()


def test_fixed_header_checkpoint_is_marked_mixed_when_resumed(tmp_path, monkeypatch):
    from tigerbook_scraper import fast

    state = State(
        tmp_path / "run.sqlite",
        {
            "target": TARGET,
            "account": "synthetic",
            "scope": "fast-full",
            "limit": None,
        },
    )
    state.note("collection_mode", "direct_requests_fixed_header")

    def stop(*args, **kwargs):
        raise AuthenticationError("Synthetic expiry")

    monkeypatch.setattr(fast, "bootstrap", stop)
    with pytest.raises(AuthenticationError):
        fast.collect_fast(state, None, {"mode": "tigernet"}, progress=lambda _: None)
    assert state.get("collection_mode") == "direct_requests_fixed_then_dynamic_header"
    assert (
        state.get("base_field_strategy")
        == "author_verified_fixed_then_per_profile_permitted_header_values"
    )
    state.close()


def test_full_run_reconciles_and_fetches_only_new_ids(tmp_path):
    async def run():
        state = State(
            tmp_path / "run.sqlite",
            {
                "target": TARGET,
                "account": "synthetic",
                "scope": "fast-full",
                "limit": None,
            },
        )
        pages = iter(
            [
                {"users": [{"id": 1}, {"id": 2}], "total_items": 2},
                {"users": [{"id": 2}, {"id": 3}], "total_items": 3},
                {"users": [{"id": 1}], "total_items": 3},
            ]
        )
        visited = []

        async def get(url):
            return next(pages)

        async def profile(ref):
            visited.append(ref.id)
            return {"Name": "Synthetic"}

        await collect_direct(
            state,
            SimpleNamespace(get=get, throttle=Gate()),
            SimpleNamespace(profile=profile),
            {"listing_url": TARGET + "/frontoffice/api/users?page=1&per_page=2"},
            workers=2,
            progress=lambda _: None,
        )
        assert sorted(visited) == ["1", "2", "3"]
        assert state.counts()["complete"] == 3
        assert state.checkpoint("discovery")["done"] and state.checkpoint("reconciliation")["done"]
        assert state.membership_differences() == 1
        state.close()

    asyncio.run(run())


def test_full_run_resumes_after_auth_failure_without_refetching_success(tmp_path):
    async def run():
        state = State(
            tmp_path / "run.sqlite",
            {
                "target": TARGET,
                "account": "synthetic",
                "scope": "fast-full",
                "limit": None,
            },
        )
        visited = []

        async def get(url):
            return {"users": [{"id": 1}, {"id": 2}], "total_items": 2}

        async def profile(ref):
            visited.append(ref.id)
            if visited == ["1", "2"]:
                raise AuthenticationError("Synthetic expiry")
            return {"Name": "Synthetic"}

        args = (
            state,
            SimpleNamespace(get=get, throttle=Gate()),
            SimpleNamespace(profile=profile),
            {"listing_url": TARGET + "/frontoffice/api/users?page=1&per_page=2"},
        )
        with pytest.raises(AuthenticationError):
            await collect_direct(*args, workers=1, progress=lambda _: None)
        assert state.counts()["complete"] == 1 and state.counts()["pending"] == 1
        await collect_direct(*args, workers=1, progress=lambda _: None)
        assert visited == ["1", "2", "2"]
        assert state.counts()["complete"] == 2 and state.membership_differences() == 0
        state.close()

    asyncio.run(run())
