from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
from playwright.sync_api import Error as PlaywrightError

from tigerbook_scraper.errors import AccessBlocked, AuthenticationError, FetchError
from tigerbook_scraper.fetch import Fetcher, Pacer, retry_seconds


class Response:
    def __init__(self, status=200, body='{"name":"synthetic"}', headers=None):
        self.status, self.body = status, body
        self.headers = headers or {"content-type": "application/json"}
        self.url = "https://example.test/profile/1"
        self.disposed = False

    def text(self):
        return self.body

    def dispose(self):
        self.disposed = True


class Request:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def client(responses):
    sleeps, auth = [], []
    request = Request(responses)
    fetch = Fetcher(
        request,
        "https://example.test",
        lambda: auth.append(True),
        pacer=Pacer(sleep=sleeps.append, clock=lambda: 0),
    )
    return fetch, sleeps, auth, request


def test_rate_limit_waits_and_disposes():
    limited = Response(429, headers={"retry-after": "7"})
    success = Response()
    fetch, sleeps, _, _ = client([limited, success])
    assert fetch.get(success.url)[0] == success.body
    assert 7 in sleeps
    assert limited.disposed and success.disposed


def test_login_page_with_200_renews_once():
    login = Response(200, '<input name="username"><input name="password">')
    fetch, _, auth, _ = client([login, Response()])
    fetch.get(login.url)
    assert len(auth) == 1
    assert login.disposed


def test_reauthentication_is_bounded():
    first, second = Response(401), Response(401)
    fetch, _, auth, _ = client([first, second])
    with pytest.raises(AuthenticationError):
        fetch.get(first.url)
    assert len(auth) == 1
    assert first.disposed and second.disposed


def test_network_failure_retries():
    fetch, _, _, request = client([PlaywrightError("synthetic timeout"), Response()])
    fetch.get("https://example.test/profile/1")
    assert request.calls == 2


@pytest.mark.parametrize(
    "status,error,count",
    [(403, AccessBlocked, 1), (404, FetchError, 1), (429, AccessBlocked, 4), (503, FetchError, 4)],
)
def test_permanent_and_exhausted_failures(status, error, count):
    responses = [Response(status) for _ in range(count)]
    fetch, _, _, request = client(responses)
    with pytest.raises(error):
        fetch.get(responses[0].url)
    assert request.calls == count
    assert all(r.disposed for r in responses)


def test_external_data_request_rejected():
    fetch, _, _, request = client([])
    with pytest.raises(FetchError):
        fetch.get("https://untrusted.test/profile")
    assert request.calls == 0


def test_retry_date_and_invalid_values():
    assert retry_seconds("nonsense") is None
    assert retry_seconds("-1") == 0
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=90))
    assert 88 <= retry_seconds(future) <= 90
    assert retry_seconds("NaN") is None
    assert retry_seconds("inf") is None


def test_canonical_redirect_does_not_trigger_authentication():
    redirect = Response(301, headers={"location": "/profile/1/"})
    fetch, _, auth, request = client([redirect, Response()])
    fetch.get(redirect.url)
    assert request.calls == 2 and not auth
    assert redirect.disposed


def test_redirect_loop_is_bounded():
    redirect = Response(302, headers={"location": "/profile/1"})
    fetch, _, auth, request = client([redirect])
    with pytest.raises(FetchError):
        fetch.get(redirect.url)
    assert request.calls == 1 and not auth


def test_single_quoted_password_form_is_auth_failure():
    form = Response(200, "<input type='password' name='secret'>")
    fetch, _, auth, _ = client([form, Response()])
    fetch.get(form.url)
    assert len(auth) == 1
