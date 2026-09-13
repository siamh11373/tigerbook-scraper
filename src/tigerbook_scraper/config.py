import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigurationError

TARGET = "https://tigernet.princeton.edu"


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)

    @property
    def account_key(self) -> str:
        return hashlib.sha256(self.username.strip().casefold().encode()).hexdigest()


def load_credentials(path: Path) -> Credentials:
    username, password = os.getenv("TIGERNET_USERNAME"), os.getenv("TIGERNET_PASSWORD")
    if username is not None or password is not None:
        if not username or not password:
            raise ConfigurationError("Set both TIGERNET_USERNAME and TIGERNET_PASSWORD.")
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            username, password = value.get("username"), value.get("password")
        except (OSError, ValueError, AttributeError):
            raise ConfigurationError(
                "Configure environment credentials or an ignored credentials.local.json file."
            ) from None
    if not isinstance(username, str) or not username.strip():
        raise ConfigurationError("A nonempty TigerNet username is required.")
    if not isinstance(password, str) or not password:
        raise ConfigurationError("A nonempty TigerNet password is required.")
    return Credentials(username.strip(), password)


def scope_name(limit: int | None) -> str:
    if limit is not None and limit <= 0:
        raise ConfigurationError("--limit must be positive.")
    return "full" if limit is None else f"sample-{limit}"
