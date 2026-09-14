"""Hybrid adapter using interfaces observed in the local authenticated inspection."""

import json
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError

from .adapter import SiteAdapter, target_url
from .config import TARGET
from .errors import (
    AccessBlocked,
    AuthenticationError,
    DiscoveryError,
    ExtractionError,
    FetchError,
    RateLimited,
)
from .fetch import login_response, retry_seconds
from .models import ListingPage, ProfileRef
from .tigernet_fields import extract_profile


def page_url(url, number):
    parts = urlsplit(target_url(url))
    query = parse_qs(parts.query, keep_blank_values=True)
    if "page" not in query:
        raise DiscoveryError("No observed page parameter exists for this response.")
    query["page"] = [str(number)]
    return urlunsplit(parts._replace(query=urlencode(query, doseq=True)))


def response_kind(url, profile_id):
    if not url.startswith(TARGET + "/"):
        return None
    path = urlsplit(url).path
    pid = re.escape(profile_id)
    patterns = {
        "base": rf"/private/frontoffice/users/profiles/{pid}",
        "header": rf"/users/{pid}/user_profiles/header_data",
        "body": rf"/users/\d+/users/{pid}/data",
        "topics": rf"/users/\d+/users/{pid}/followed_topics",
        "badges": rf"/users/{pid}/badges\.json",
    }
    return next((kind for kind, pattern in patterns.items() if re.fullmatch(pattern, path)), None)


def all_topics(first, url, fetcher):
    records, seen = [], set()
    value = first
    total = value.get("total_items")
    expected_page = int(parse_qs(urlsplit(url).query)["page"][0])
    while True:
        if value.get("page") != expected_page or value.get("total_items") != total:
            raise ExtractionError("Community pagination changed while collecting the profile.")
        if not isinstance(value.get("topics"), list) or type(total) is not int:
            raise ExtractionError("Unrecognized community listing.")
        before = len(seen)
        for record in value["topics"]:
            identity = record.get("id")
            if type(identity) is not int:
                raise ExtractionError("Community record has no stable ID.")
            if identity not in seen:
                seen.add(identity)
                records.append(record)
        if not value.get("has_next_page"):
            if len(records) != total:
                raise ExtractionError("Community count does not reconcile.")
            return {**first, "topics": records, "has_next_page": False}
        if len(seen) == before or len(seen) >= total:
            raise ExtractionError("Community pagination stalled or contradicted its total.")
        expected_page += 1
        body, kind = fetcher.get(page_url(url, expected_page))
        if "json" not in kind:
            raise ExtractionError("Community request did not return structured data.")
        try:
            value = json.loads(body)
        except ValueError:
            raise ExtractionError("Community response was not valid JSON.") from None


class TigerNetAdapter(SiteAdapter):
    def __init__(self, page, fetcher, contract):
        super().__init__(page, fetcher, contract)
        self.field_coverage_verified = bool(contract.get("field_coverage_evidence"))
        self.last_audit = None
        # Ephemeral observations for the optional direct-request collector. Never
        # persist request headers: they may contain authentication material.
        self.last_requests = {}

    def list_page(self, cursor):
        url = target_url(cursor or self.contract["listing_url"])
        body, kind = self.fetcher.get(url)
        try:
            data = json.loads(body)
            query = parse_qs(urlsplit(url).query)
            number, size = int(query["page"][0]), int(query["per_page"][0])
            total, users = data["total_items"], data["users"]
            if "json" not in kind or type(total) is not int or not isinstance(users, list):
                raise ValueError
            if number < 1 or size < 1 or total < 0 or len(users) > size:
                raise ValueError
            if any(type(user.get("id")) is not int for user in users):
                raise ValueError
            refs = tuple(ProfileRef(str(u["id"]), f"{TARGET}/users/{u['id']}") for u in users)
            more = number * size < total
            if more and not users:
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DiscoveryError("The observed directory response changed structure.") from None
        # Last-seen ordering and filter semantics are still unproven for exhaustive coverage.
        return ListingPage(refs, page_url(url, number + 1) if more else None, total, False)

    def profile(self, ref):
        renewed = False
        for attempt in range(self.fetcher.attempts):
            captured, failures, observed_requests = {}, [], {}

            def pace(route, _request=None, *, failures=failures):
                if failures and self.fetcher.stop_on_throttle:
                    route.abort()
                    return
                # Export image/link URLs from the profile structures and DOM;
                # downloading their binary content adds no fields to the CSV.
                if route.request.resource_type in ("image", "media", "font"):
                    route.abort()
                    return
                if response_kind(route.request.url, ref.id):
                    self.fetcher.pacer.wait()
                route.fallback()

            def capture(
                response, captured=captured, failures=failures, observed_requests=observed_requests
            ):
                kind = response_kind(response.url, ref.id)
                if kind is None:
                    return
                try:
                    if response.status != 200:
                        status = response.status
                        if status in (301, 302, 303, 307, 308):
                            status = 401
                        failures.append((status, response.headers.get("retry-after")))
                        return
                    text = response.text()
                    if login_response(response.url, text):
                        failures.append((401, None))
                        return
                    captured[kind] = (json.loads(text), response.url)
                    observed_requests[kind] = {
                        "url": response.url,
                        "method": response.request.method,
                        "headers": {
                            key: value
                            for key, value in response.request.all_headers().items()
                            if key
                            in (
                                "accept",
                                "authorization",
                                "x-csrf-token",
                                "x-xsrf-token",
                                "x-requested-with",
                            )
                        },
                    }
                except (PlaywrightError, ValueError):
                    failures.append((502, None))

            self.page.route("**/*", pace)
            self.page.on("response", capture)
            try:
                self._navigate(ref.url)
                deadline = time.monotonic() + 45
                while len(captured) < 5 and not failures and time.monotonic() < deadline:
                    self.page.wait_for_timeout(100)
                rendered_text = self.page.locator("body").inner_text()
                rendered_html = self.page.content()
            finally:
                self.page.remove_listener("response", capture)
                self.page.unroute("**/*", pace)
            if any(status == 403 for status, _ in failures):
                raise AccessBlocked("Profile data access was denied.")
            if self.fetcher.stop_on_throttle and any(status == 429 for status, _ in failures):
                waits = [retry_seconds(value) for status, value in failures if status == 429]
                raise RateLimited(
                    max((value for value in waits if value is not None), default=None)
                )
            if any(status == 401 for status, _ in failures):
                if renewed:
                    raise AuthenticationError("Profile session renewal failed.")
                self.fetcher.reauthenticate()
                renewed = True
                continue
            if any(400 <= status < 500 and status != 429 for status, _ in failures):
                raise ExtractionError("A required profile response was unavailable.")
            if failures or len(captured) != 5:
                waits = [retry_seconds(value) or 0 for _, value in failures]
                delay = max([2**attempt, *waits])
                limited = any(status == 429 for status, _ in failures)
                if delay > 300 or (limited and attempt == self.fetcher.attempts - 1):
                    raise AccessBlocked("Profile throttling requires a later resume.")
                if attempt == self.fetcher.attempts - 1:
                    raise FetchError("Required profile responses did not complete after retries.")
                self.page.wait_for_timeout(delay * 1000)
                continue
            payloads = {key: value[0] for key, value in captured.items()}
            if str(payloads["base"].get("id")) != ref.id:
                raise ExtractionError("Profile response identity does not match its URL.")
            payloads["topics"] = all_topics(payloads["topics"], captured["topics"][1], self.fetcher)
            fields = extract_profile(
                **payloads, rendered_text=rendered_text, rendered_html=rendered_html
            )
            name = payloads["base"].get("name")
            self.last_audit = (ref.id, fields, bool(name and name in rendered_text))
            self.last_requests = observed_requests
            return fields
        raise AuthenticationError("Profile session could not be established.")

    def audit(self, ref, fields):
        return self.last_audit == (ref.id, fields, True)
