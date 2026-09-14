from types import SimpleNamespace

import pytest

from tigerbook_scraper.chrome import CoolingAdapter
from tigerbook_scraper.errors import AccessBlocked, RateLimited
from tigerbook_scraper.fetch import Fetcher, Pacer


class State:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def note(self, key, value):
        self.values[key] = value

    def counts(self):
        return {"complete": 202, "pending": 100, "failed": 0}


def setup():
    state, events, now = State(), [], [1000.0]

    def sleep(seconds):
        events.append(("sleep", seconds))
        now[0] += seconds

    adapter = CoolingAdapter(
        None,
        state,
        pause=lambda: events.append(("pause", now[0])),
        sleep=sleep,
        clock=lambda: now[0],
        progress=lambda _: None,
    )
    return adapter, state, events, now


def test_server_wait_and_retry_preserve_operation_result():
    adapter, state, events, now = setup()
    calls = []

    def operation():
        calls.append(now[0])
        if len(calls) == 1:
            raise RateLimited(450)
        return {"late field": ["東京", "second record"]}

    assert adapter.call(operation) == {"late field": ["東京", "second record"]}
    assert calls == [1000, 1450]
    assert events[0][0] == "pause"
    assert state.get("chrome_last_throttle")["retry_after_seconds"] == 450
    assert state.get("chrome_cooldown_until") == 0


def test_repeated_rejections_stop_and_leave_durable_deadline():
    adapter, state, _, now = setup()
    calls = []

    def reject():
        calls.append(now[0])
        raise RateLimited()

    with pytest.raises(AccessBlocked):
        adapter.call(reject)
    assert calls == [1000, 1300, 1900]
    assert state.get("chrome_cooldown_until") == 3100
    resumed, _, events, resumed_time = setup()
    resumed.state = state
    resumed.call(lambda: events.append(("request", resumed_time[0])))
    assert events[-1] == ("request", 3100)


def test_interrupt_during_pause_keeps_deadline():
    adapter, state, _, _ = setup()

    def interrupt(_):
        raise KeyboardInterrupt

    adapter.sleep = interrupt
    with pytest.raises(KeyboardInterrupt):
        adapter.call(lambda: (_ for _ in ()).throw(RateLimited(600)))
    assert state.get("chrome_cooldown_until") == 1600


def test_fetcher_yields_first_429_and_disposes_response():
    disposed, calls = [], []
    response = SimpleNamespace(
        status=429,
        url="https://example.test/data",
        headers={"retry-after": "600"},
        text=lambda: "",
        dispose=lambda: disposed.append(True),
    )
    request = SimpleNamespace(get=lambda *a, **kw: (calls.append(True), response)[1])
    fetcher = Fetcher(
        request, "https://example.test", lambda: None, stop_on_throttle=True, pacer=Pacer(0)
    )
    with pytest.raises(RateLimited) as caught:
        fetcher.get("https://example.test/data")
    assert caught.value.retry_after == 600
    assert calls == [True] and disposed == [True]


@pytest.mark.parametrize("location", ["navigation", "profile_data"])
def test_browser_throttling_yields_to_global_cooldown(browser, location):
    from tigerbook_scraper.config import TARGET
    from tigerbook_scraper.models import ProfileRef
    from tigerbook_scraper.tigernet import TigerNetAdapter

    context = browser.new_context()
    rejections = []

    def serve(route):
        if location == "profile_data" and route.request.url == TARGET + "/users/1":
            route.fulfill(
                content_type="text/html",
                body=(
                    '<body>Synthetic<script>fetch("/private/frontoffice/users/profiles/1")'
                    "</script></body>"
                ),
            )
        else:
            rejections.append(True)
            route.fulfill(status=429, headers={"Retry-After": "720"}, body="limited")

    context.route("**/*", serve)
    fetcher = Fetcher(
        context.request,
        TARGET,
        lambda: pytest.fail("Unexpected renewal"),
        stop_on_throttle=True,
        pacer=Pacer(0),
    )
    adapter = TigerNetAdapter(context.new_page(), fetcher, {})
    with pytest.raises(RateLimited) as caught:
        adapter.profile(ProfileRef("1", TARGET + "/users/1"))
    assert caught.value.retry_after == 720
    assert rejections == [True]
    context.close()


@pytest.mark.parametrize(
    "args",
    [
        ["--request-rate", "0"],
        ["--request-rate", "6"],
        ["--request-rate", "6", "--benchmark", "100"],
        ["--request-rate", "4", "--benchmark", "20"],
        ["--benchmark", "20", "--limit", "15"],
        ["--benchmark", "0"],
    ],
)
def test_invalid_benchmark_rejected_before_credentials(args):
    from tigerbook_scraper.chrome import main

    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
