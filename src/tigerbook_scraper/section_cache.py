"""Private, short-lived response bodies for interrupted profile collection.

Construct only after State has validated the account/target/scope identity. The
cache belongs in that same ignored database, never in fixtures or public output.
Call load once before fetching a profile, save each successful JSON object, then
discard after the assembled record is committed. Headers and cookies are not
part of this interface. Cached bodies are private source data, not export data;
normal field privacy filtering must still run when assembling a profile.
"""

import json
import math
import sqlite3
import time
from collections.abc import Callable


class SectionCache:
    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        max_age_seconds: float = 3600,
        clock: Callable[[], float] = time.time,
    ):
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("Section cache age must be finite and positive.")
        self.db, self.max_age_seconds, self.clock = db, max_age_seconds, clock
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS profile_sections_v1(
                    profile_id TEXT NOT NULL,
                    section TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    body TEXT NOT NULL,
                    PRIMARY KEY(profile_id, section)
                )
            """)

    def load(self, profile_id: str) -> dict[str, dict]:
        """Load one coherent retry snapshot; expire every section together.

        Freshness bounds reuse, not source snapshot consistency. The directory
        may change while either a fresh or resumed profile is being fetched.
        """
        rows = self.db.execute(
            "SELECT section,fetched_at,body FROM profile_sections_v1 WHERE profile_id=?",
            (profile_id,),
        ).fetchall()
        current = self.clock()
        result = {}
        try:
            for section, fetched_at, body in rows:
                age = current - fetched_at
                if not math.isfinite(age) or age < 0 or age >= self.max_age_seconds:
                    raise ValueError("Expired response section.")
                value = json.loads(body, parse_constant=_invalid_constant)
                if not isinstance(value, dict):
                    raise ValueError("Invalid response section.")
                result[section] = value
        except (ValueError, TypeError, OverflowError, RecursionError):
            self.discard(profile_id)
            return {}
        return result

    def put(self, profile_id: str, section: str, body: dict) -> None:
        """Commit one successful response body, preserving other sections."""
        if not profile_id or not section or not isinstance(body, dict):
            raise ValueError("Response sections need an ID, key, and JSON object.")
        value = json.dumps(body, ensure_ascii=False, allow_nan=False)
        with self.db:
            self.db.execute(
                "INSERT INTO profile_sections_v1 VALUES(?,?,?,?) "
                "ON CONFLICT(profile_id,section) DO UPDATE SET "
                "fetched_at=excluded.fetched_at,body=excluded.body",
                (profile_id, section, self.clock(), value),
            )

    def discard(self, profile_id: str) -> None:
        """Delete all cached sections after record commit or invalid extraction."""
        with self.db:
            self.db.execute("DELETE FROM profile_sections_v1 WHERE profile_id=?", (profile_id,))


def _invalid_constant(value: str):
    raise ValueError("Invalid JSON constant in cached response.")
