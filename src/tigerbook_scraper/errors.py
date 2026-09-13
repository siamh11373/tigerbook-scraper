"""Safe, categorical errors. Never put response bodies or credentials in messages."""


class ScraperError(Exception):
    code = "scraper_error"


class ConfigurationError(ScraperError):
    code = "configuration_error"


class AuthenticationError(ScraperError):
    code = "authentication_required"


class InteractiveAuthenticationRequired(AuthenticationError):
    code = "interactive_authentication_required"


class AccessBlocked(ScraperError):
    code = "access_blocked"


class FetchError(ScraperError):
    code = "fetch_failed"


class ExtractionError(ScraperError):
    code = "unrecognized_profile"


class DiscoveryError(ScraperError):
    code = "discovery_incomplete"


class StateMismatch(ScraperError):
    code = "state_mismatch"
