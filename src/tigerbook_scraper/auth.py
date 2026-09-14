"""Browser authentication using the publicly observed TigerNet CAS form."""

import re
import time
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError

from .config import TARGET, Credentials
from .errors import AuthenticationError, InteractiveAuthenticationRequired

CAS_ORIGIN = "https://fed.princeton.edu"
DIRECTORY_NAME = re.compile(r"^Alumni Directory(?: Search)?$", re.I)
CHALLENGE = re.compile(
    r"verify your identity|check your device|approve.{0,30}(sign.in|duo)|"
    r"enter.{0,20}verification code|use.{0,15}(passkey|security key)|"
    r"two.factor authentication|multi.factor authentication",
    re.I,
)
HUMAN_CHALLENGE = re.compile(
    r"verify you are human|verifying you are human|checking your browser|"
    r"performing security verification|additional verification required",
    re.I,
)


def origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def authenticate(
    page,
    credentials: Credentials,
    *,
    timeout=45.0,
    allow_interactive=False,
    interactive_timeout=300.0,
    progress=print,
) -> str:
    """Return a candidate directory URL; the adapter must verify protected content.

    A new browser context is required on process startup. During renewal, CAS may
    reuse its still-valid SSO session without displaying the credential form.
    """
    try:
        page.goto(f"{TARGET}/login", wait_until="domcontentloaded", timeout=30_000)
        submitted = False
        waiting_for_user = False
        deadline = time.monotonic() + timeout

        def handle_challenge():
            nonlocal waiting_for_user, deadline
            if not allow_interactive:
                raise InteractiveAuthenticationRequired(
                    "Authentication requires an MFA interaction."
                )
            if not waiting_for_user:
                waiting_for_user = True
                deadline = time.monotonic() + interactive_timeout
                page.bring_to_front()
                progress(
                    "Complete the human verification or MFA in the browser or on your device. "
                    f"Waiting up to {interactive_timeout:g} seconds; do not enter codes in chat."
                )

        while time.monotonic() < deadline:
            if any(
                urlsplit(frame.url).hostname
                and urlsplit(frame.url).hostname.endswith(".duosecurity.com")
                for frame in page.frames
            ):
                handle_challenge()
                page.wait_for_timeout(250)
                continue
            try:
                text = page.locator("body").inner_text(timeout=1500)
            except PlaywrightError:
                time.sleep(0.25)
                continue
            if CHALLENGE.search(text) or HUMAN_CHALLENGE.search(text):
                handle_challenge()
                page.wait_for_timeout(250)
                continue
            if re.search(
                r"invalid credentials|authentication failed|incorrect password|"
                r"credentials.{0,20}(invalid|incorrect)",
                text,
                re.I,
            ):
                raise AuthenticationError("CAS rejected the login attempt.")
            if origin(page.url) == TARGET:
                links = page.get_by_role("link", name=DIRECTORY_NAME)
                for link in links.all():
                    if link.is_visible():
                        href = link.get_attribute("href")
                        url = urljoin(page.url, href or "")
                        if (
                            href
                            and origin(url) == TARGET
                            and not urlsplit(url).path.endswith("login")
                        ):
                            return url
            username = page.locator('input[name="username"]')
            if not submitted and username.count() and username.is_visible():
                if origin(page.url) != CAS_ORIGIN:
                    raise AuthenticationError(
                        "The credential form is not on the verified CAS origin."
                    )
                action = page.locator('input[name="password"]').evaluate(
                    "input => input.form ? input.form.action : null"
                )
                if not action or origin(action) != CAS_ORIGIN:
                    raise AuthenticationError(
                        "The credential form has an unexpected submission origin."
                    )
                method = page.locator('input[name="password"]').evaluate(
                    "input => input.form.method.toLowerCase()"
                )
                if method != "post":
                    raise AuthenticationError("The credential form no longer submits by POST.")
                username.fill(credentials.username)
                page.locator('input[name="password"]').fill(credentials.password)
                page.get_by_role("button", name=re.compile(r"^login$", re.I)).click(timeout=15_000)
                submitted = True
            # Let the synchronous browser dispatcher handle navigation and frames.
            page.wait_for_timeout(250)
        if waiting_for_user:
            raise InteractiveAuthenticationRequired(
                "Manual authentication did not complete within the allowed wait."
            )
        raise AuthenticationError("An authenticated directory link could not be verified.")
    except PlaywrightError:
        # Playwright error messages can contain filled values, request URLs, or page text.
        raise AuthenticationError("The browser could not complete the observed CAS flow.") from None
