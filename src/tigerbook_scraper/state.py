import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .errors import DiscoveryError, StateMismatch
from .models import Fields, ListingPage, ProfileRef


def now() -> str:
    return datetime.now(UTC).isoformat()


class State:
    """One database is one target/account/scope run, with transactional checkpoints."""

    def __init__(self, path: Path, identity: dict | None = None):
        if identity is None and not path.is_file():
            raise StateMismatch("No saved run exists for this scope.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS profiles(
                id TEXT PRIMARY KEY, url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                fields TEXT, error TEXT, fetched_at TEXT);
            CREATE TABLE IF NOT EXISTS pages(
                phase TEXT NOT NULL, token TEXT NOT NULL, next_token TEXT,
                PRIMARY KEY(phase, token));
            CREATE TABLE IF NOT EXISTS membership(
                phase TEXT NOT NULL, id TEXT NOT NULL REFERENCES profiles(id),
                PRIMARY KEY(phase, id));
        """)
        stored = self.get("identity")
        if stored is None:
            if identity is None:
                self.close()
                raise StateMismatch("Saved run has no valid identity.")
            with self.db:
                self.set("identity", {**identity, "schema": 1})
                self.set("started_at", now())
        elif identity is not None and stored != {**identity, "schema": 1}:
            self.close()
            raise StateMismatch("Saved run belongs to a different account, target, or scope.")
        elif stored.get("schema") != 1:
            self.close()
            raise StateMismatch("Unsupported state schema.")

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value) -> None:
        self.db.execute(
            "INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, allow_nan=False)),
        )

    def note(self, key: str, value) -> None:
        with self.db:
            self.set(key, value)

    def checkpoint(self, phase: str) -> dict:
        return self.get(f"checkpoint:{phase}", {"cursor": None, "done": False})

    def save_page(self, phase: str, cursor: str | None, page: ListingPage) -> None:
        token = json.dumps(cursor)
        if self.db.execute(
            "SELECT 1 FROM pages WHERE phase=? AND token=?", (phase, token)
        ).fetchone():
            raise DiscoveryError("Pagination repeated an already committed page.")
        if page.next_cursor is not None:
            next_token = json.dumps(page.next_cursor)
            if (
                next_token == token
                or self.db.execute(
                    "SELECT 1 FROM pages WHERE phase=? AND token=?", (phase, next_token)
                ).fetchone()
            ):
                raise DiscoveryError("Pagination continuation forms a loop.")
        refs = {ref.id: ref for ref in page.profiles}
        if any(not ref.id or not ref.url for ref in refs.values()):
            raise DiscoveryError("A discovered profile has no stable identifier or URL.")
        with self.db:
            before = self.membership_count(phase)
            for ref in refs.values():
                self.db.execute(
                    "INSERT INTO profiles(id,url) VALUES(?,?) "
                    "ON CONFLICT(id) DO UPDATE SET url=excluded.url",
                    (ref.id, ref.url),
                )
                self.db.execute("INSERT OR IGNORE INTO membership VALUES(?,?)", (phase, ref.id))
            if page.next_cursor is not None and self.membership_count(phase) == before:
                raise DiscoveryError("Pagination made no progress despite claiming another page.")
            if page.total is not None:
                previous = self.get(f"total:{phase}")
                if previous is not None and previous != page.total:
                    self.set("source_changed", True)
                self.set(f"total:{phase}", page.total)
            self.set(
                f"exhaustive:{phase}", self.get(f"exhaustive:{phase}", True) and page.exhaustive
            )
            self.db.execute("INSERT INTO pages VALUES(?,?,?)", (phase, token, page.next_cursor))
            self.set(
                f"checkpoint:{phase}",
                {
                    "cursor": page.next_cursor,
                    "done": page.next_cursor is None,
                },
            )

    def membership_count(self, phase: str) -> int:
        return self.db.execute(
            "SELECT count(*) FROM membership WHERE phase=?", (phase,)
        ).fetchone()[0]

    def counts(self) -> dict[str, int]:
        result = {key: 0 for key in ("pending", "complete", "failed")}
        result.update(
            {
                r[0]: r[1]
                for r in self.db.execute("SELECT status,count(*) FROM profiles GROUP BY status")
            }
        )
        result["discovered"] = sum(result.values())
        return result

    def pending(self):
        for row in self.db.execute(
            "SELECT id,url FROM profiles WHERE status='pending' ORDER BY id"
        ):
            yield ProfileRef(row[0], row[1])

    def retry_failed(self) -> None:
        with self.db:
            self.db.execute("UPDATE profiles SET status='pending' WHERE status='failed'")

    def attempt(self, profile_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE profiles SET attempts=attempts+1 WHERE id=?", (profile_id,))

    def complete(self, profile_id: str, fields: Fields) -> None:
        value = json.dumps(fields, ensure_ascii=False, allow_nan=False)
        with self.db:
            self.db.execute(
                "UPDATE profiles SET fields=?,status='complete',error=NULL,fetched_at=? WHERE id=?",
                (value, now(), profile_id),
            )

    def fail(self, profile_id: str, code: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE profiles SET status='failed',error=? WHERE id=?", (code, profile_id)
            )

    def records(self):
        for row in self.db.execute(
            "SELECT id,url,fields FROM profiles WHERE status='complete' ORDER BY id"
        ):
            yield row[0], row[1], json.loads(row[2])

    def membership_differences(self) -> int:
        return self.db.execute("""
            SELECT count(*) FROM (
              SELECT id FROM membership GROUP BY id HAVING count(DISTINCT phase) != 2
            )
        """).fetchone()[0]

    def close(self) -> None:
        self.db.close()
