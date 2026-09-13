import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        # All test traffic must be fulfilled by routes. Unexpected real traffic fails.
        browser = playwright.chromium.launch(proxy={"server": "http://127.0.0.1:9"})
        yield browser
        browser.close()
