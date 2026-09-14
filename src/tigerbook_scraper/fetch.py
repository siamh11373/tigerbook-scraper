import math
import random
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError

from .errors import AccessBlocked, AuthenticationError, FetchError, RateLimited


def retry_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        return max(0, result) if math.isfinite(result) else None
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return max(0, (date - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def login_response(url: str, body: str) -> bool:
    path = urlsplit(url).path.rstrip("/").lower()
    return (
        path.endswith(("/login", "/signin", "/sign-in"))
        or bool(re.search(r"<input\b[^>]*type\s*=\s*['\"]password['\"]", body, re.I))
        or ('name="password"' in body and 'name="username"' in body)
        or ("central authentication service" in body.lower() and "password" in body.lower())
    )


class Pacer:
    def __init__(self, interval=1.0, *, sleep=time.sleep, clock=time.monotonic):
        self.interval, self.sleep, self.clock = interval, sleep, clock
        self.next_at = 0.0

    def wait(self):
        self.sleep(max(0, self.next_at - self.clock()))
        self.next_at = self.clock() + self.interval


class Fetcher:
    def __init__(
        self,
        request,
        target: str,
        reauthenticate,
        *,
        pacer=None,
        attempts=4,
        stop_on_throttle=False,
    ):
        self.request, self.target = request, urlsplit(target)
        self.reauthenticate = reauthenticate
        self.pacer = pacer or Pacer()
        self.attempts = attempts
        self.stop_on_throttle = stop_on_throttle

    def get(self, url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != (self.target.scheme, self.target.netloc):
            raise FetchError("Refusing a data request outside the configured target.")
        renewed = False
        original_url = url
        visited = {url}
        failures = 0
        while failures < self.attempts:
            self.pacer.wait()
            response = None
            delay = None
            try:
                response = self.request.get(url, timeout=30_000, max_redirects=0)
                status = response.status
                body = response.text()
                content_type = response.headers.get("content-type", "")
                if status in (301, 302, 303, 307, 308):
                    destination = urljoin(url, response.headers.get("location", ""))
                    redirect = urlsplit(destination)
                    if (redirect.scheme, redirect.netloc) == (
                        self.target.scheme,
                        self.target.netloc,
                    ) and not login_response(destination, ""):
                        if destination in visited or len(visited) >= 6:
                            raise FetchError(
                                "Data request redirects repeated or exceeded the limit."
                            )
                        visited.add(destination)
                        url = destination
                        continue
                if status in (401, 301, 302, 303, 307, 308) or login_response(response.url, body):
                    if renewed:
                        raise AuthenticationError("Session could not be renewed unattended.")
                    self.reauthenticate()
                    renewed = True
                    url = original_url
                    visited = {url}
                    continue
                if status == 403:
                    raise AccessBlocked("The server denied access. Collection stopped.")
                if status == 429 or 500 <= status < 600:
                    delay = retry_seconds(response.headers.get("retry-after"))
                    if status == 429 and self.stop_on_throttle:
                        raise RateLimited(delay)
                    if delay is not None and delay > 300:
                        raise AccessBlocked("Server requests a long pause; resume later.")
                    failures += 1
                    if failures == self.attempts:
                        if status == 429:
                            raise AccessBlocked("Rate limiting persisted after bounded retries.")
                        raise FetchError("Server errors persisted after bounded retries.")
                elif not 200 <= status < 300:
                    raise FetchError(f"Profile request failed with HTTP {status}.")
                else:
                    return body, content_type
            except PlaywrightError:
                failures += 1
                if failures == self.attempts:
                    raise FetchError("Network operation failed after bounded retries.") from None
            finally:
                if response is not None:
                    response.dispose()
            self.pacer.sleep(delay if delay is not None else 2 ** (failures - 1) + random.random())
        raise FetchError("Request attempts exhausted.")
