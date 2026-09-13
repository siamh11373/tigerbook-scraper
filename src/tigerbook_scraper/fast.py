"""Concurrent collection through observed requests; authentication stays in a browser.

Session state and observed authorization headers exist only in memory. SQLite is
owned by the calling thread, with all async workers on the same event loop.
"""

import asyncio
import json
import random
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .adapter import target_url
from .config import TARGET
from .errors import (
    AccessBlocked,
    AuthenticationError,
    ConfigurationError,
    DiscoveryError,
    ExtractionError,
    FetchError,
)
from .fetch import login_response, retry_seconds
from .fields import from_mapping
from .models import ListingPage, ProfileRef
from .tigernet import page_url, response_kind
from .tigernet_fields import extract_profile

KINDS = {"base", "header", "body", "topics", "badges"}
HEADER_KEYS = {"name", "headline", "photo_url", "cover_picture_url"}


async def together(coroutines):
    """Cancel and drain remaining requests before propagating a fatal error."""
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def observed_templates(requests, profile_id):
    if set(requests) != KINDS:
        raise ConfigurationError("Fast collection requires all five observed profile requests.")
    result = {}
    for kind, request in requests.items():
        url = target_url(request["url"])
        if request["method"] != "GET" or response_kind(url, profile_id) != kind:
            raise ConfigurationError("A profile request does not match the observed GET interface.")
        parts = urlsplit(url)
        # Only profile-ID path segments are substituted, never arbitrary query values.
        path = re.sub(r"(/(?:users|profiles)/)\d+(?=/|$)", r"\1{profile_id}", parts.path)
        template = urlunsplit(parts._replace(path=path))
        if response_kind(template.replace("{profile_id}", "1"), "1") != kind:
            raise ConfigurationError("Could not establish the observed profile request template.")
        result[kind] = {"url": template, "headers": dict(request["headers"])}
    return result


def bootstrap(credentials, contract, *, allow_interactive, sample_size=3, progress=print):
    """Fresh browser login and small rendered reference; return only in-memory state."""
    from playwright.sync_api import sync_playwright

    from .auth import authenticate
    from .fetch import Fetcher
    from .tigernet import TigerNetAdapter

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not allow_interactive)
        context = browser.new_context()
        try:
            page = context.new_page()

            def login():
                return authenticate(page, credentials, allow_interactive=allow_interactive)

            login()
            adapter = TigerNetAdapter(page, Fetcher(context.request, TARGET, login), contract)
            listing = adapter.list_page(None)
            if not listing.profiles:
                raise DiscoveryError("No accessible profiles could establish fast collection.")
            references, base_keys, templates = [], set(), None
            for ref in listing.profiles[:sample_size]:
                fields = adapter.profile(ref)
                if not adapter.audit(ref, fields):
                    raise ExtractionError("Rendered startup reference did not verify identity.")
                references.append((ref, fields))
                base_keys.update(
                    key.removeprefix("Profile/")
                    for key, value in fields.items()
                    if key.startswith("Profile/")
                    and isinstance(value, str)
                    and key.removeprefix("Profile/") in HEADER_KEYS
                )
                current = observed_templates(adapter.last_requests, ref.id)
                if templates is not None and any(
                    current[key]["url"] != templates[key]["url"] for key in KINDS
                ):
                    raise ConfigurationError("Observed profile request routes were inconsistent.")
                templates = current
            progress("Browser reference captured. Checking direct requests before full collection.")
            return {
                "session": context.storage_state(),
                "templates": templates,
                "base_keys": base_keys,
                "references": references,
                "listing_total": listing.total,
                "user_agent": page.evaluate("navigator.userAgent"),
            }
        finally:
            context.close()
            browser.close()


class Throttle:
    """One shared request-start gate, with gradual ramp-up and global 429 cooldown."""

    def __init__(self, start=20.0, ceiling=40.0, *, clock=time.monotonic, sleep=asyncio.sleep):
        if not 0 < start <= ceiling <= 50:
            raise ConfigurationError("Request rates must satisfy 0 < start <= maximum <= 50.")
        self.ceiling, self.rate = ceiling, start
        self.clock, self.sleep = clock, sleep
        self.next_at = self.blocked_until = 0.0
        self.lock = asyncio.Lock()
        self.starts = self.successes = self.throttles = self.transient_failures = 0

    async def wait(self):
        async with self.lock:
            while (delay := max(self.next_at, self.blocked_until) - self.clock()) > 0:
                await self.sleep(delay)
            self.next_at = self.clock() + 1 / self.rate
            self.starts += 1

    def success(self):
        self.successes += 1
        if self.successes >= 2000:
            self.rate = min(self.ceiling, self.rate + 2)
            self.successes = 0

    def failure(self):
        self.transient_failures += 1
        self.successes = 0
        self.rate = max(0.25, self.rate * 0.8)

    def cooldown(self, seconds):
        self.throttles += 1
        self.successes = 0
        self.rate = max(min(0.25, self.ceiling), self.rate / 2)
        self.blocked_until = max(self.blocked_until, self.clock() + seconds)


class Client:
    def __init__(self, request, throttle, workers=8):
        self.request, self.throttle = request, throttle
        self.slots = asyncio.Semaphore(workers)

    async def get(self, url, headers=None):
        from playwright.async_api import Error as PlaywrightError

        url = target_url(url)
        for attempt in range(4):
            response = None
            delay = 2**attempt + random.random()
            try:
                async with self.slots:
                    await self.throttle.wait()
                    response = await self.request.get(
                        url,
                        headers=headers or {"accept": "application/json"},
                        timeout=30_000,
                        max_redirects=0,
                    )
                    status = response.status
                    body = await response.text()
                    if status == 401 or 300 <= status < 400 or login_response(response.url, body):
                        raise AuthenticationError("Direct-request session needs browser renewal.")
                    if status == 403:
                        raise AccessBlocked(
                            "Server denied direct-request access; collection stopped."
                        )
                    if status == 429 or 500 <= status < 600:
                        requested = retry_seconds(response.headers.get("retry-after"))
                        if requested is not None:
                            delay = max(delay, requested)
                        if status == 429:
                            self.throttle.cooldown(delay)
                        else:
                            self.throttle.failure()
                        if delay > 300 or (status == 429 and attempt == 3):
                            raise AccessBlocked("Server throttling requires a later resume.")
                        if attempt == 3:
                            raise FetchError("Server errors persisted after bounded retries.")
                    elif not 200 <= status < 300:
                        raise FetchError(f"Profile request failed with HTTP {status}.")
                    else:
                        if "json" not in response.headers.get("content-type", ""):
                            raise ExtractionError("Observed data request did not return JSON.")
                        try:
                            value = json.loads(body)
                        except ValueError:
                            raise ExtractionError("Observed response was not valid JSON.") from None
                        self.throttle.success()
                        return value
            except PlaywrightError:
                self.throttle.failure()
                if attempt == 3:
                    raise FetchError("Network operation failed after bounded retries.") from None
            finally:
                if response is not None:
                    await response.dispose()
            await asyncio.sleep(delay)
        raise FetchError("Direct-request attempts exhausted.")


class DirectProfiles:
    def __init__(self, client, templates, base_keys):
        self.client, self.templates, self.base_keys = client, templates, base_keys

    async def profile(self, ref):
        if not ref.id.isdecimal():
            raise ExtractionError("Observed TigerNet profile ID must be numeric.")
        kinds = sorted(KINDS)
        urls = {key: self.templates[key]["url"].replace("{profile_id}", ref.id) for key in kinds}
        values = await together(
            self.client.get(urls[key], self.templates[key]["headers"]) for key in kinds
        )
        payloads = dict(zip(kinds, values, strict=True))
        if not all(isinstance(value, dict) for value in values):
            raise ExtractionError("An observed profile response changed its object structure.")
        if str(payloads["base"].get("id")) != ref.id:
            raise ExtractionError("Direct profile identity does not match the discovered ID.")
        topics, records, seen = payloads["topics"], [], set()
        try:
            number = int(parse_qs(urlsplit(urls["topics"]).query)["page"][0])
        except (KeyError, ValueError):
            raise ExtractionError("No observed community page parameter exists.") from None
        total = topics.get("total_items")
        while True:
            if (
                not isinstance(topics, dict)
                or topics.get("page") != number
                or type(total) is not int
                or total < 0
                or topics.get("total_items") != total
                or not isinstance(topics.get("topics"), list)
            ):
                raise ExtractionError("Community pagination changed structure or population.")
            before = len(seen)
            for record in topics["topics"]:
                if not isinstance(record, dict) or type(record.get("id")) is not int:
                    raise ExtractionError("Community record has no stable ID.")
                if record["id"] not in seen:
                    seen.add(record["id"])
                    records.append(record)
            if not topics.get("has_next_page"):
                if len(records) != total:
                    raise ExtractionError("Community records do not reconcile with their total.")
                break
            if len(seen) == before or len(seen) >= total:
                raise ExtractionError("Community pagination stalled.")
            number += 1
            topics = await self.client.get(
                page_url(urls["topics"], number), self.templates["topics"]["headers"]
            )
        payloads["topics"] = {**payloads["topics"], "topics": records, "has_next_page": False}
        return from_mapping(
            extract_profile(
                **payloads,
                rendered_text="",
                rendered_html="",
                visible_base_keys=self.base_keys,
            )
        )


async def collect_direct(
    state, client, profiles, contract, *, limit=None, workers=8, progress=print
):
    started, initial = time.monotonic(), state.counts()["complete"]
    counts = state.counts()
    last_notice = 0.0
    consecutive_failures = 0

    def notice(force=False):
        nonlocal last_notice
        elapsed = time.monotonic() - started
        if not force and elapsed - last_notice < 10:
            return
        last_notice = elapsed
        completed = counts["complete"] - initial
        rate = completed / max(elapsed, 0.001)
        total = state.get("total:discovery")
        eta = (
            f"; projected remaining {(total - counts['complete']) / rate / 3600:.1f}h"
            if total and rate
            else ""
        )
        progress(
            f"Discovered {counts['discovered']}; completed {counts['complete']}; "
            f"failed {counts['failed']}; {rate:.2f} profiles/s; "
            f"request rate now {client.throttle.rate:g}/{client.throttle.ceiling:g}/s; "
            f"429s {client.throttle.throttles}{eta}"
        )
        state.note(
            "benchmark",
            {
                "new_profiles": completed,
                "elapsed_seconds": elapsed,
                "request_starts": client.throttle.starts,
                "http_429_count": client.throttle.throttles,
                "transient_request_failures": client.throttle.transient_failures,
                "current_requests_per_second": client.throttle.rate,
                "maximum_requests_per_second": client.throttle.ceiling,
                "interpretation": "includes discovery and collection; excludes browser startup",
            },
        )

    async def discover(phase):
        while not state.checkpoint(phase)["done"]:
            cursor = state.checkpoint(phase)["cursor"]
            url = target_url(cursor or contract["listing_url"])
            value = await client.get(url)
            try:
                query = parse_qs(urlsplit(url).query)
                number, size = int(query["page"][0]), int(query["per_page"][0])
                total, users = value["total_items"], value["users"]
                if (
                    type(total) is not int
                    or total < 0
                    or not isinstance(users, list)
                    or size < 1
                    or number < 1
                    or len(users) > size
                    or any(type(user.get("id")) is not int for user in users)
                ):
                    raise ValueError
                more = number * size < total
                refs = tuple(ProfileRef(str(u["id"]), f"{TARGET}/users/{u['id']}") for u in users)
                if more and not refs:
                    raise ValueError
            except (ValueError, TypeError, KeyError, AttributeError):
                raise DiscoveryError("The observed listing changed structure.") from None
            state.save_page(
                phase,
                cursor,
                ListingPage(
                    refs,
                    page_url(url, number + 1) if more else None,
                    total,
                    False,
                ),
            )
            counts.update(state.counts())
            notice()
            if limit is not None and counts["discovered"] >= limit:
                return

    async def pending():
        iterator = iter(state.pending())
        budget = None if limit is None else max(0, limit - counts["complete"])

        # Reserve limit slots before awaiting so concurrent completions cannot overshoot.
        async def worker():
            nonlocal budget, consecutive_failures
            while budget is None or budget > 0:
                ref = next(iterator, None)
                if ref is None:
                    return
                if budget is not None:
                    budget -= 1
                state.attempt(ref.id)
                try:
                    fields = await profiles.profile(ref)
                    state.complete(ref.id, fields)
                    counts["complete"] += 1
                    consecutive_failures = 0
                except (FetchError, ExtractionError) as error:
                    state.fail(ref.id, error.code)
                    counts["failed"] += 1
                    if budget is not None:
                        budget += 1
                    consecutive_failures += 1
                    if consecutive_failures >= 10:
                        raise ExtractionError(
                            "Ten consecutive profiles failed; inspect before resuming."
                        ) from None
                counts["pending"] -= 1
                notice()

        await together(worker() for _ in range(workers))

    try:
        for phase in ("discovery", "reconciliation"):
            if limit is not None and counts["complete"] >= limit:
                break
            # Enumerate first to shorten the window in which last-activity sorting drifts.
            await discover(phase)
            await pending()
        state.note("field_fidelity_verified", False)
    finally:
        notice(force=True)


async def choose_listing(client, original, total, sample_ids):
    """Try a larger value of the observed page-size parameter; verify before using it."""
    parts = urlsplit(target_url(original))
    query = parse_qs(parts.query, keep_blank_values=True)
    if "page" not in query or "per_page" not in query:
        return original
    query.update(page=["1"], per_page=["100"])
    candidate = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
    try:
        value = await client.get(candidate)
    except (FetchError, ExtractionError):
        return original
    # Access blocking/authentication errors propagate; a probe never bypasses them.
    if not isinstance(value, dict) or value.get("total_items") != total:
        return original
    users = value.get("users")
    if (
        not isinstance(users, list)
        or type(total) is not int
        or len(users) != min(100, total)
        or any(not isinstance(user, dict) or type(user.get("id")) is not int for user in users)
    ):
        return original
    ids = {str(user["id"]) for user in users}
    if len(ids) != len(users) or not sample_ids.issubset(ids):
        return original
    if value.get("page", 1) != 1 or value.get("per_page", 100) != 100:
        return original
    return candidate


async def session_run(
    state,
    setup,
    contract,
    *,
    limit=None,
    workers=32,
    start_rate=20.0,
    ceiling=40.0,
    progress=print,
):
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        request = await playwright.request.new_context(
            storage_state=setup["session"], user_agent=setup.get("user_agent")
        )
        try:
            throttle = Throttle(start_rate, ceiling)
            client = Client(request, throttle, workers)
            profiles = DirectProfiles(client, setup["templates"], setup["base_keys"])
            for ref, expected in setup["references"]:
                actual = await profiles.profile(ref)

                # Base header fields are deliberately fixed from startup observations;
                # labelled sections, memberships, badges and repeated records must agree.
                def core(fields):
                    return {
                        key: value
                        for key, value in fields.items()
                        if not key.startswith("Profile/")
                        or key
                        in ("Profile/introduction", "Profile/Alumni Communities", "Profile/Badges")
                    }

                if core(actual) != core(expected):
                    raise ExtractionError(
                        "Direct-request startup comparison disagreed with browser data."
                    )
            state.note("direct_browser_comparisons", len(setup["references"]))
            state.note("fixed_base_fields", sorted(setup["base_keys"]))
            state.note("field_fidelity_verified", False)
            effective = dict(contract)
            effective["listing_url"] = state.get("fast_listing_url")
            if effective["listing_url"] is None:
                effective["listing_url"] = await choose_listing(
                    client,
                    contract["listing_url"],
                    setup.get("listing_total"),
                    {ref.id for ref, _ in setup["references"]},
                )
                state.note("fast_listing_url", effective["listing_url"])
            size = parse_qs(urlsplit(effective["listing_url"]).query)["per_page"][0]
            progress(f"Observed listing page size for this run: {size}.")
            progress(
                "Direct-request comparison passed. Enumerating and collecting the requested scope."
            )
            await collect_direct(
                state, client, profiles, effective, limit=limit, workers=workers, progress=progress
            )
        finally:
            await request.dispose()


def collect_fast(
    state,
    credentials,
    contract,
    *,
    allow_interactive=False,
    limit=None,
    workers=32,
    start_rate=20.0,
    ceiling=40.0,
    progress=print,
):
    if contract.get("mode") != "tigernet":
        raise ConfigurationError("Fast mode requires the observed TigerNet contract.")
    if not 1 <= workers <= 32 or not 0 < start_rate <= ceiling <= 50:
        raise ConfigurationError("Use 1–32 workers and rates where 0 < start <= maximum <= 50.")
    state.note("blocker", None)
    state.retry_failed()
    state.note("collection_mode", "direct_requests_fixed_header")
    state.note("field_fidelity_verified", False)
    previous_renewal = None
    while True:
        setup = bootstrap(
            credentials,
            contract,
            allow_interactive=allow_interactive,
            sample_size=min(3, limit) if limit is not None else 3,
            progress=progress,
        )
        # Keep the selected supplemental header fields stable across resumed runs.
        if state.get("fixed_base_fields") is not None:
            setup["base_keys"] = set(state.get("fixed_base_fields")) & HEADER_KEYS
        try:
            asyncio.run(
                session_run(
                    state,
                    setup,
                    contract,
                    limit=limit,
                    workers=workers,
                    start_rate=start_rate,
                    ceiling=ceiling,
                    progress=progress,
                )
            )
            return
        except AuthenticationError:
            counts = state.counts()
            mark = (counts["discovered"], counts["complete"])
            if previous_renewal == mark:
                raise AuthenticationError(
                    "Direct requests remained unauthenticated after renewal."
                ) from None
            previous_renewal = mark
            progress(
                "Session expired. Reopening the normal browser login; saved records are retained."
            )
        finally:
            setup.clear()
