"""Site integration is activated only after authenticated discovery supplies a contract.

No TigerNet directory endpoint or private profile selector is guessed here. Contracts
are the site-specific parser configuration established during authenticated inspection.
"""

import json
import random
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError

from .auth import origin
from .config import TARGET
from .errors import (
    AccessBlocked,
    AuthenticationError,
    ConfigurationError,
    DiscoveryError,
    ExtractionError,
    FetchError,
    RateLimited,
)
from .fetch import login_response, retry_seconds
from .fields import from_mapping, from_pairs
from .models import ListingPage, ProfileRef


def at(value, path: list[str]):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ExtractionError("Observed source structure has changed.")
        value = value[key]
    return value


def target_url(value: str, base=TARGET) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtractionError("Source did not supply a profile or continuation URL.")
    result = urljoin(base, value)
    if origin(result) != TARGET:
        raise ExtractionError("Source URL points outside the approved TigerNet origin.")
    return urlsplit(result)._replace(fragment="").geturl()


def load_contract(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigurationError(
            "Authenticated inspection is required: no verified site contract exists. "
            "Use --inspect after configuring credentials; do not invent endpoints or selectors."
        ) from None
    if not isinstance(value, dict) or value.get("target") != TARGET:
        raise ConfigurationError("The site contract does not describe the approved target.")
    if value.get("mode") not in ("json", "dom", "tigernet") or not value.get("evidence"):
        raise ConfigurationError("A site contract must record its mode and observation evidence.")
    if type(value.get("exhaustive", False)) is not bool:
        raise ConfigurationError("The exhaustive flag must be a boolean, supported by evidence.")
    if value.get("exhaustive") and not value.get("enumeration_evidence"):
        raise ConfigurationError("Exhaustive discovery requires documented enumeration evidence.")
    if value["mode"] == "tigernet":
        target_url(value.get("listing_url"))
        return value
    required = {"listing_url", "audit"}
    required |= (
        {"records_path", "id_path", "url_path", "next_path", "total_path", "profile_path"}
        if value["mode"] == "json"
        else {"cards", "profile_link", "next_link", "total"}
    )
    if not required.issubset(value):
        raise ConfigurationError("The verified site contract is missing parser configuration.")
    target_url(value["listing_url"])
    return value


class SiteAdapter:
    def __init__(self, page, fetcher, contract: dict):
        self.page, self.fetcher, self.contract = page, fetcher, contract

    def _navigate(self, url: str):
        url = target_url(url)
        renewed, failures = False, 0
        while failures < self.fetcher.attempts:
            self.fetcher.pacer.wait()
            delay = None
            try:
                response = self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                if response is None:
                    raise FetchError("Browser navigation returned no response.")
                status = response.status
                if (
                    origin(self.page.url) != TARGET
                    or status == 401
                    or login_response(self.page.url, self.page.content())
                ):
                    if renewed:
                        raise AuthenticationError("Rendered content remains unauthenticated.")
                    self.fetcher.reauthenticate()
                    renewed = True
                    continue
                if status == 403:
                    raise AccessBlocked("The server denied access. Collection stopped.")
                if status == 429 or status >= 500:
                    delay = retry_seconds(response.headers.get("retry-after"))
                    if status == 429 and self.fetcher.stop_on_throttle:
                        raise RateLimited(delay)
                    if delay is not None and delay > 300:
                        raise AccessBlocked("Server requests a long pause; resume later.")
                    failures += 1
                    if failures == self.fetcher.attempts:
                        if status == 429:
                            raise AccessBlocked("Browser rate limiting persisted.")
                        raise FetchError("Browser server errors persisted.")
                elif not 200 <= status < 300:
                    raise FetchError(f"Browser request failed with HTTP {status}.")
                else:
                    return
            except PlaywrightError:
                failures += 1
                if failures == self.fetcher.attempts:
                    raise FetchError("Browser network attempts exhausted.") from None
            self.page.wait_for_timeout(
                1000 * (delay if delay is not None else 2 ** (failures - 1) + random.random())
            )

    def list_page(self, cursor: str | None) -> ListingPage:
        c = self.contract
        url = target_url(cursor or c["listing_url"])
        if c["mode"] == "json":
            body, kind = self.fetcher.get(url)
            if "json" not in kind:
                raise DiscoveryError("Expected the observed structured directory response.")
            try:
                value = json.loads(body)
                records = at(value, c["records_path"])
                next_url = at(value, c["next_path"])
                total = at(value, c["total_path"])
                if not isinstance(records, list) or not isinstance(total, int) or total < 0:
                    raise ValueError
                refs = tuple(
                    ProfileRef(str(at(r, c["id_path"])), target_url(at(r, c["url_path"])))
                    for r in records
                )
                if any(ref.id in ("", "None") for ref in refs):
                    raise ValueError
                continuation = None if next_url is None else target_url(next_url, url)
            except (ValueError, TypeError, ExtractionError):
                raise DiscoveryError(
                    "Structured listing no longer matches its observed contract."
                ) from None
            return ListingPage(refs, continuation, total, bool(c.get("exhaustive", False)))
        self._navigate(url)
        try:
            self.page.locator(c["total"]).wait_for(state="visible", timeout=15_000)
            text = self.page.locator(c["total"]).inner_text()
        except PlaywrightError:
            raise DiscoveryError("The observed directory structure was not found.") from None
        # The contract identifies a count-only element; never guess which page number is a total.
        try:
            total = int(text.strip().replace(",", ""))
        except ValueError:
            raise DiscoveryError("Directory total is not the observed count-only value.") from None
        refs = []
        for card in self.page.locator(c["cards"]).all():
            link = card.locator(c["profile_link"])
            href = link.get_attribute("href")
            profile_url = target_url(href, url)
            # A verified canonical URL is the stable identity in DOM mode.
            refs.append(ProfileRef(profile_url, profile_url))
        next_link = self.page.locator(c["next_link"])
        next_url = None
        if next_link.count() and next_link.first.is_visible():
            disabled = next_link.first.get_attribute("aria-disabled") == "true"
            if not disabled:
                next_url = target_url(next_link.first.get_attribute("href"), url)
        return ListingPage(tuple(refs), next_url, total, bool(c.get("exhaustive", False)))

    def _dom_fields(self, ref: ProfileRef) -> dict:
        c = self.contract["audit"]
        self._navigate(ref.url)
        root = self.page.locator(c["root"])
        try:
            root.wait_for(state="visible", timeout=15_000)
        except PlaywrightError:
            raise ExtractionError("The observed profile structure was not found.") from None
        pairs = []
        for section in root.locator(c["sections"]).all():
            if not section.is_visible():
                continue
            heading = section.locator(c["heading"]).inner_text()
            for row in section.locator(c["rows"]).all():
                if not row.is_visible():
                    continue
                label = row.locator(c["label"]).inner_text()
                value = row.locator(c["value"])
                extracted = value.evaluate("""el => {
                    const text = el.innerText;
                    const links = [...el.querySelectorAll('a[href]')].map(a => a.href);
                    const images = [...el.querySelectorAll('img[src]')].map(i => i.src);
                    return links.length || images.length ? {text, links, images} : text;
                }""")
                pairs.append((heading, label, extracted))
        return from_pairs(pairs)

    def profile(self, ref: ProfileRef) -> dict:
        if self.contract["mode"] == "dom":
            return self._dom_fields(ref)
        body, kind = self.fetcher.get(ref.url)
        if "json" not in kind:
            raise ExtractionError("Profile URL did not return the observed structured data.")
        try:
            return from_mapping(at(json.loads(body), self.contract["profile_path"]))
        except ValueError:
            raise ExtractionError("Profile response is not valid JSON.") from None

    def audit(self, ref: ProfileRef, fields: dict) -> bool:
        # Repeating a parser is only a consistency check. Independent inspection
        # evidence must first establish that its structures cover all permitted fields.
        return bool(self.contract.get("field_coverage_evidence")) and (
            self._dom_fields(ref) == fields
        )
