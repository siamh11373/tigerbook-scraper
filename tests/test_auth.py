import pytest

from tigerbook_scraper.auth import authenticate
from tigerbook_scraper.config import Credentials
from tigerbook_scraper.errors import AuthenticationError, InteractiveAuthenticationRequired

FORM = """<form method="post" action="/cas/login">
<input name="username"><input name="password" type="password">
<input name="execution" type="hidden" value="synthetic-state">
<button type="submit">LOGIN</button></form>"""


@pytest.mark.parametrize("outcome", ["success", "mfa", "invalid"])
def test_observed_cas_form_with_synthetic_network(browser, outcome):
    context = browser.new_context()
    submissions = []

    def route(request):
        url = request.request.url
        if url == "https://tigernet.princeton.edu/login":
            request.fulfill(
                content_type="text/html",
                body='<script>location.replace("https://fed.princeton.edu/cas/login")</script>',
            )
        elif url == "https://fed.princeton.edu/cas/login":
            if request.request.method == "POST":
                submissions.append(request.request.post_data)
                if outcome == "success":
                    request.fulfill(
                        content_type="text/html",
                        body='<script>location.replace("https://tigernet.princeton.edu/feed")</script>',
                    )
                else:
                    request.fulfill(
                        content_type="text/html",
                        body=("Check your device" if outcome == "mfa" else "Invalid credentials"),
                    )
            else:
                request.fulfill(content_type="text/html", body=FORM)
        elif url == "https://tigernet.princeton.edu/feed":
            request.fulfill(
                content_type="text/html", body='<a href="/synthetic-directory">Alumni Directory</a>'
            )
        else:
            request.abort()

    context.route("**/*", route)
    page = context.new_page()
    if outcome == "success":
        assert authenticate(page, Credentials("synthetic", "test-only"), timeout=3) == (
            "https://tigernet.princeton.edu/synthetic-directory"
        )
    else:
        error = InteractiveAuthenticationRequired if outcome == "mfa" else AuthenticationError
        with pytest.raises(error):
            authenticate(page, Credentials("synthetic", "test-only"), timeout=3)
    assert len(submissions) == 1
    assert "execution=synthetic-state" in submissions[0]
    context.close()


def test_valid_sso_renewal_does_not_require_another_credential_form(browser):
    context = browser.new_context()
    context.route(
        "**/*",
        lambda route: route.fulfill(
            content_type="text/html",
            body='<a href="/synthetic-directory">Alumni Directory</a>',
        ),
    )
    assert authenticate(context.new_page(), Credentials("synthetic", "test-only"), timeout=3) == (
        "https://tigernet.princeton.edu/synthetic-directory"
    )
    context.close()


def test_form_action_cannot_send_credentials_to_unexpected_origin(browser):
    context = browser.new_context()

    def route(request):
        if request.request.url.startswith("https://tigernet.princeton.edu/"):
            request.fulfill(
                content_type="text/html",
                body='<script>location.replace("https://fed.princeton.edu/cas/login")</script>',
            )
        else:
            assert request.request.method == "GET"
            request.fulfill(
                content_type="text/html",
                body=FORM.replace(
                    'action="/cas/login"', 'action="https://unexpected.test/collect"'
                ),
            )

    context.route("**/*", route)
    with pytest.raises(AuthenticationError, match="submission origin"):
        authenticate(context.new_page(), Credentials("synthetic", "test-only"), timeout=3)
    context.close()


@pytest.mark.parametrize("complete", [True, False])
def test_attended_mfa_waits_for_user_and_has_a_deadline(browser, complete):
    context = browser.new_context()
    context.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body="Check your device")
    )
    page = context.new_page()
    notices = []

    def user_handoff(message):
        notices.append(message)
        if complete:
            # Simulate a user completing MFA, not an automated MFA approval.
            page.set_content('<a href="/synthetic-directory">Alumni Directory</a>')

    if complete:
        assert (
            authenticate(
                page,
                Credentials("synthetic", "test-only"),
                allow_interactive=True,
                timeout=0.1,
                interactive_timeout=1,
                progress=user_handoff,
            )
            == "https://tigernet.princeton.edu/synthetic-directory"
        )
    else:
        with pytest.raises(InteractiveAuthenticationRequired, match="allowed wait"):
            authenticate(
                page,
                Credentials("synthetic", "test-only"),
                allow_interactive=True,
                timeout=0.1,
                interactive_timeout=0.3,
                progress=user_handoff,
            )
    assert len(notices) == 1
    context.close()
