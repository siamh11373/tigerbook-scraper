"""Small authenticated inspection saved only to the ignored local output directory."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from .auth import origin
from .config import TARGET


def inspect_directory(page, directory_url: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    responses = []

    def capture(response):
        if len(responses) >= 20 or origin(response.url) != TARGET:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        if any(
            part in urlsplit(response.url).path.lower() for part in ("login", "auth", "session")
        ):
            return
        try:
            body = response.body()
            if len(body) <= 2_000_000:
                responses.append(
                    {"url": response.url, "status": response.status, "data": json.loads(body)}
                )
        except Exception:
            # Inspection is diagnostic; do not expose response data through exception messages.
            return

    page.on("response", capture)
    try:
        page.goto(directory_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3000)
        (output / "directory.html").write_text(page.content(), encoding="utf-8")
        (output / "directory.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        (output / "responses.json").write_text(
            json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        page.screenshot(path=str(output / "directory.png"), full_page=True)
    finally:
        page.remove_listener("response", capture)
