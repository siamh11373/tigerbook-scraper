"""Small authenticated inspection saved only to the ignored local output directory."""

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from .auth import origin
from .config import TARGET
from .errors import AuthenticationError

SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_token",
    "session_token",
    "password",
    "client_secret",
    "authorization",
    "authenticity_token",
    "csrf_token",
}


def contains_secret(value):
    """Diagnostic captures must not retain token-service payloads."""
    if isinstance(value, dict):
        return any(
            str(key).lower() in SECRET_KEYS or contains_secret(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_secret(item) for item in value)
    return False


def inspect_directory(page, directory_url: str, output: Path, *, settle_ms=3000) -> None:
    output.mkdir(parents=True, exist_ok=True)
    responses = []
    summary = {"stages": [], "profile_samples": 0}

    def capture(response):
        if len(responses) >= 40 or origin(response.url) != TARGET:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        if any(
            part in urlsplit(response.url).path.lower() for part in ("login", "auth", "session")
        ):
            return
        if SECRET_KEYS.intersection(key.lower() for key in parse_qs(urlsplit(response.url).query)):
            return
        try:
            body = response.body()
            if len(body) <= 2_000_000:
                data = json.loads(body)
                if contains_secret(data):
                    return
                responses.append(
                    {
                        "url": response.url,
                        "method": response.request.method,
                        "status": response.status,
                        "data": data,
                    }
                )
        except Exception:
            # Inspection is diagnostic; do not expose response data through exception messages.
            return

    def save_stage(name, started):
        if origin(page.url) != TARGET or page.locator('input[type="password"]').count():
            raise AuthenticationError("Inspection returned to an unauthenticated page.")
        (output / f"{name}.html").write_text(page.content(), encoding="utf-8")
        (output / f"{name}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        response_file = "responses.json" if name == "directory" else f"{name}-responses.json"
        (output / response_file).write_text(
            json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        page.screenshot(path=str(output / f"{name}.png"), full_page=True)
        summary["stages"].append(
            {
                "name": name,
                "seconds": time.monotonic() - started,
                "captured_json_responses": len(responses),
            }
        )
        (output / "inspection-summary.json").write_text(json.dumps(summary, indent=2))

    page.on("response", capture)
    try:
        started = time.monotonic()
        page.goto(directory_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(settle_ms)
        save_stage("directory", started)
        # This path shape and these links were observed in the authenticated listing.
        urls = []
        for href in page.locator("a[href]").evaluate_all("links => links.map(a => a.href)"):
            parsed = urlsplit(href)
            if origin(href) == TARGET and re.fullmatch(r"/users/\d+", parsed.path):
                canonical = urljoin(TARGET, parsed.path)
                if canonical not in urls:
                    urls.append(canonical)
        samples = [urls[i] for i in sorted({0, len(urls) // 2, len(urls) - 1})] if urls else []
        next_page = page.get_by_role("button", name="Next page", exact=True)
        if next_page.count() == 1 and next_page.is_enabled():
            page.wait_for_timeout(1000)
            responses.clear()
            started = time.monotonic()
            with page.expect_response(
                lambda r: urlsplit(r.url).path == "/frontoffice/api/users", timeout=30_000
            ):
                next_page.click()
            page.wait_for_timeout(settle_ms)
            save_stage("directory-page-2", started)
        for number, url in enumerate(samples, 1):
            page.wait_for_timeout(1000)
            responses.clear()
            started = time.monotonic()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(settle_ms)
            summary["profile_samples"] = number
            save_stage(f"profile-{number}", started)
    finally:
        page.remove_listener("response", capture)
