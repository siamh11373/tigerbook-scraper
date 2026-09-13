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
        # Body/community routes contain both the signed-in viewer ID and target
        # profile ID. Preserve the viewer ID and replace only the observed target.
        patterns = {
            "base": rf"(/profiles/){re.escape(profile_id)}$",
            "header": rf"(/users/){re.escape(profile_id)}(?=/user_profiles/header_data$)",
            "body": rf"(/users/\d+/users/){re.escape(profile_id)}(?=/data$)",
            "topics": rf"(/users/\d+/users/){re.escape(profile_id)}(?=/followed_topics$)",
            "badges": rf"(/users/){re.escape(profile_id)}(?=/badges\.json$)",
        }
        path, replacements = re.subn(patterns[kind], r"\1{profile_id}", parts.path, count=1)
        if replacements != 1:
            raise ConfigurationError("Could not isolate the target profile ID in a request route.")
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
            references, base_keys, templates, skipped = [], set(), None, 0
            for ref in listing.profiles:
                if len(references) >= sample_size:
                    break
                try:
                    fields = adapter.profile(ref)
                    if not adapter.audit(ref, fields):
                        raise ExtractionError("Rendered startup reference did not verify identity.")
                    current = observed_templates(adapter.last_requests, ref.id)
                    if templates is not None and any(
                        current[key]["url"] != templates[key]["url"] for key in KINDS
                    ):
                        raise ConfigurationError(
                            "Observed profile request routes were inconsistent."
                        )
                except (ConfigurationError, ExtractionError, FetchError):
                    skipped += 1
                    progress("Skipped one incompatible startup profile; trying the next result.")
                    continue
                references.append((ref, fields))
                base_keys.update(
                    key.removeprefix("Profile/")
                    for key, value in fields.items()
                    if key.startswith("Profile/")
                    and isinstance(value, str)
                    and key.removeprefix("Profile/") in HEADER_KEYS
                )
                templates = current
            if not references:
                raise ExtractionError(
                    "No profile on the first directory page established a usable request shape."
                )
            progress("Browser reference captured. Checking direct requests before full collection.")
            return {
                "session": context.storage_state(),
                "templates": templates,
                "base_keys": base_keys,
                "references": references,
                "listing_total": listing.total,
                "user_agent": page.evaluate("navigator.userAgent"),
                "startup_profiles_skipped": skipped,
            }
        finally:
            context.close()
            browser.close()


class Throttle:
    """One shared request-start gate, with gradual ramp-up and global 429 cooldown."""

    def __init__(self, start=2.0, ceiling=6.0, *, clock=time.monotonic, sleep=asyncio.sleep):
        if not 0 < start <= ceiling <= 50:
            raise ConfigurationError("Request rates must satisfy 0 < start <= maximum <= 50.")
        self.ceiling, self.rate = ceiling, start
        self.clock, self.sleep = clock, sleep
        self.next_at = self.blocked_until = 0.0
        self.throttle_decrease_until = self.transient_decrease_until = 0.0
        self.lock = asyncio.Lock()
        self.starts = self.successes = self.throttles = self.transient_failures = 0
        self.rate_decreases = 0

    async def wait(self):
        async with self.lock:
            while (delay := max(self.next_at, self.blocked_until) - self.clock()) > 0:
                await self.sleep(delay)
            self.next_at = self.clock() + 1 / self.rate
            self.starts += 1

    def success(self):
        self.successes += 1
        if self.successes >= 100 and self.clock() >= self.throttle_decrease_until:
            self.rate = min(self.ceiling, self.rate + 2)
            self.successes = 0

    def failure(self):
        self.transient_failures += 1
        self.successes = 0
        now = self.clock()
        if now >= self.transient_decrease_until:
            self.rate = max(0.25, self.rate * 0.8)
            self.transient_decrease_until = now + 5
            self.rate_decreases += 1

    def cooldown(self, seconds):
        self.throttles += 1
        self.successes = 0
        now = self.clock()
        if now >= self.throttle_decrease_until:
            self.rate = max(min(0.25, self.ceiling), self.rate / 2)
            self.rate_decreases += 1
            self.throttle_decrease_until = now + max(30, seconds)
        # Responses already in flight belong to the same throttling event. They
        # extend the shared pause without repeatedly halving the rate.
        self.blocked_until = max(self.blocked_until, now + seconds)


class Client:
    def __init__(
        self,
        request,
        throttle,
        workers=8,
        *,
        slots=None,
        attempts=4,
        operation_timeout=35,
        disposal_timeout=5,
    ):
        self.request, self.throttle = request, throttle
        self.slots = asyncio.Semaphore(workers) if slots is None else slots
        self.attempts = attempts
        self.operation_timeout = operation_timeout
        self.disposal_timeout = disposal_timeout

    async def get(self, url, headers=None):
        from playwright.async_api import Error as PlaywrightError

        url = target_url(url)
        for attempt in range(self.attempts):
            response = None
            delay = 2**attempt + random.random()
            try:
                async with self.slots:
                    await self.throttle.wait()
                    async with asyncio.timeout(self.operation_timeout):
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
                        if delay > 300 or (status == 429 and attempt == self.attempts - 1):
                            raise AccessBlocked("Server throttling requires a later resume.")
                        if attempt == self.attempts - 1:
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
                if attempt == self.attempts - 1:
                    raise FetchError("Network operation failed after bounded retries.") from None
            except TimeoutError:
                self.throttle.failure()
                if attempt == self.attempts - 1:
                    raise FetchError("Request operation timed out after bounded retries.") from None
            finally:
                if response is not None:
                    try:
                        async with asyncio.timeout(self.disposal_timeout):
                            await response.dispose()
                    except (TimeoutError, PlaywrightError):
                        pass
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


class SessionPool:
    """Share safety limits while assigning each profile to one session."""

    def __init__(self, clients, profiles):
        self.clients = tuple(clients)
        self.profiles = tuple(profiles)
        if not self.clients or len(self.clients) != len(self.profiles):
            raise ConfigurationError("Each authenticated client needs one profile source.")
        if len({id(client.throttle) for client in self.clients}) != 1:
            raise ConfigurationError("Authenticated clients must share one request-rate limit.")
        if len({id(client.slots) for client in self.clients}) != 1:
            raise ConfigurationError("Authenticated clients must share one request-slot limit.")
        self.throttle = self.clients[0].throttle

    async def get(self, url, headers=None):
        return await self.clients[0].get(url, headers)

    async def profile(self, ref):
        return await self.profiles[int(ref.id) % len(self.profiles)].profile(ref)


def stabilize_base_keys(setups, saved=None):
    """Apply one fixed visible-header field set to every authenticated session."""
    stable = (
        set(saved) & HEADER_KEYS
        if saved is not None
        else set().union(*(item["base_keys"] for item in setups))
    )
    for item in setups:
        item["base_keys"] = set(stable)
    return stable


async def collect_direct(
    state, client, profiles, contract, *, limit=None, workers=8, progress=print
):
    started = time.monotonic()
    collection_started = None
    collection_initial = state.counts()["complete"]
    counts = state.counts()
    last_notice = 0.0

    def notice(force=False):
        nonlocal last_notice
        elapsed = time.monotonic() - (collection_started or started)
        if not force and elapsed - last_notice < 10:
            return
        last_notice = elapsed
        completed = counts["complete"] - collection_initial
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
                "rate_decreases": client.throttle.rate_decreases,
                "current_requests_per_second": client.throttle.rate,
                "maximum_requests_per_second": client.throttle.ceiling,
                "phase": "extraction" if collection_started is not None else "discovery",
                "interpretation": (
                    "profile timing begins when extraction starts; browser startup is excluded"
                ),
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
        nonlocal collection_started, collection_initial
        if collection_started is None:
            collection_started = time.monotonic()
            collection_initial = counts["complete"]
        iterator = iter(state.pending())
        budget = None if limit is None else max(0, limit - counts["complete"])

        # Reserve limit slots before awaiting so concurrent completions cannot overshoot.
        async def worker():
            nonlocal budget
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
                except (FetchError, ExtractionError) as error:
                    state.fail(ref.id, error.code)
                    counts["failed"] += 1
                    if budget is not None:
                        budget += 1
                counts["pending"] -= 1
                notice()

        await together(worker() for _ in range(workers))

    stop_heartbeat = asyncio.Event()

    async def heartbeat():
        while True:
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=10)
                return
            except TimeoutError:
                counts.update(state.counts())
                notice(force=True)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        for phase in ("discovery", "reconciliation"):
            if limit is not None and counts["complete"] >= limit:
                break
            # Enumerate first to shorten the window in which last-activity sorting drifts.
            await discover(phase)
            await pending()
        state.note("field_fidelity_verified", False)
    finally:
        stop_heartbeat.set()
        await heartbeat_task
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
    start_rate=2.0,
    ceiling=6.0,
    progress=print,
):
    from playwright.async_api import async_playwright

    setups = setup if isinstance(setup, list) else [setup]
    async with async_playwright() as playwright:
        requests = []
        try:
            for item in setups:
                requests.append(
                    await playwright.request.new_context(
                        storage_state=item["session"], user_agent=item.get("user_agent")
                    )
                )
            shared_throttle = Throttle(start_rate, ceiling)
            shared_slots = asyncio.Semaphore(workers)
            clients = [
                Client(
                    request,
                    shared_throttle,
                    workers,
                    slots=shared_slots,
                )
                for request in requests
            ]
            profile_sources = [
                DirectProfiles(client, item["templates"], item["base_keys"])
                for client, item in zip(clients, setups, strict=True)
            ]
            pool = SessionPool(clients, profile_sources)
            comparison_mismatches = 0
            comparisons = 0
            for profiles, item in zip(profile_sources, setups, strict=True):
                for ref, expected in item["references"]:
                    comparisons += 1
                    try:
                        actual = await profiles.profile(ref)
                    except (FetchError, ExtractionError):
                        comparison_mismatches += 1
                        continue

                    # Base header fields are deliberately fixed from startup observations;
                    # labelled sections, memberships, badges and repeated records must agree.
                    def core(fields):
                        return {
                            key: value
                            for key, value in fields.items()
                            if not key.startswith("Profile/")
                            or key
                            in (
                                "Profile/introduction",
                                "Profile/Alumni Communities",
                                "Profile/Badges",
                            )
                        }

                    if core(actual) != core(expected):
                        comparison_mismatches += 1
            state.note("direct_browser_comparisons", comparisons)
            state.note("direct_browser_mismatches", comparison_mismatches)
            state.note(
                "startup_profiles_skipped",
                sum(item.get("startup_profiles_skipped", 0) for item in setups),
            )
            state.note("browser_sessions", len(setups))
            if comparison_mismatches:
                progress(
                    "Startup comparison found profile differences; continuing with local failure "
                    "tracking and a partial completion report."
                )
            state.note("fixed_base_fields", sorted(setups[0]["base_keys"]))
            state.note("field_fidelity_verified", False)
            effective = dict(contract)
            effective["listing_url"] = state.get("fast_listing_url")
            if effective["listing_url"] is None:
                effective["listing_url"] = await choose_listing(
                    pool,
                    contract["listing_url"],
                    setups[0].get("listing_total"),
                    {ref.id for ref, _ in setups[0]["references"]},
                )
                state.note("fast_listing_url", effective["listing_url"])
            size = parse_qs(urlsplit(effective["listing_url"]).query)["per_page"][0]
            progress(f"Observed listing page size for this run: {size}.")
            progress(
                "Direct-request comparison passed. Enumerating and collecting the requested scope."
            )
            # Each profile fans out to five base requests. Keep the profile queue
            # close to the request-slot capacity instead of enqueuing 5x more work.
            profile_workers = max(1, (workers + len(KINDS) - 1) // len(KINDS))
            await collect_direct(
                state,
                pool,
                pool,
                effective,
                limit=limit,
                workers=profile_workers,
                progress=progress,
            )
        finally:
            await asyncio.gather(
                *(request.dispose() for request in requests), return_exceptions=True
            )


def collect_fast(
    state,
    credentials,
    contract,
    *,
    allow_interactive=False,
    limit=None,
    workers=32,
    start_rate=2.0,
    ceiling=6.0,
    browser_sessions=1,
    progress=print,
):
    if contract.get("mode") != "tigernet":
        raise ConfigurationError("Fast mode requires the observed TigerNet contract.")
    if (
        not 1 <= workers <= 32
        or not 1 <= browser_sessions <= 2
        or not 0 < start_rate <= ceiling <= 50
    ):
        raise ConfigurationError(
            "Use 1–32 workers, 1–2 sessions, and rates where 0 < start <= maximum <= 50."
        )
    state.note("blocker", None)
    state.retry_failed()
    state.note("collection_mode", "direct_requests_fixed_header")
    state.note("field_fidelity_verified", False)
    previous_renewal = None
    while True:
        setups = []
        try:
            for number in range(browser_sessions):
                progress(f"Authenticating browser session {number + 1} of {browser_sessions}.")
                sample_size = min(3, limit) if number == 0 and limit is not None else 3
                if number > 0:
                    sample_size = 1
                item = bootstrap(
                    credentials,
                    contract,
                    allow_interactive=allow_interactive,
                    sample_size=sample_size,
                    progress=progress,
                )
                setups.append(item)
            stabilize_base_keys(setups, state.get("fixed_base_fields"))
            asyncio.run(
                session_run(
                    state,
                    setups,
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
            for item in setups:
                item.clear()
