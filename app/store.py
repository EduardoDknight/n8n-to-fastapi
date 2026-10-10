"""SQLite idempotency + audit log (stdlib only)."""
import json
import sqlite3
import threading
import time


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                idempotency_key TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                status TEXT NOT NULL,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, key TEXT NOT NULL, event TEXT NOT NULL, data TEXT
            );
            """
        )

    def claim(self, key: str) -> dict | None:
        """Atomically reserve a key. Returns the stored row if the key already existed."""
        with self._lock:
            try:
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO leads (idempotency_key, created_at, status) VALUES (?, ?, 'processing')",
                        (key, time.time()),
                    )
                return None
            except sqlite3.IntegrityError:
                status, result = self._conn.execute(
                    "SELECT status, result FROM leads WHERE idempotency_key = ?", (key,)
                ).fetchone()
                return {"status": status, "result": json.loads(result) if result else None}

    def complete(self, key: str, result: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE leads SET status = 'done', result = ? WHERE idempotency_key = ?", (json.dumps(result), key)
            )

    def release(self, key: str) -> None:
        """Drop a failed claim so the sender can retry with the same key."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM leads WHERE idempotency_key = ? AND status = 'processing'", (key,))

    def audit(self, key: str, event: str, **data) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit (ts, key, event, data) VALUES (?, ?, ?, ?)",
                (time.time(), key, event, json.dumps(data, default=str)),
            )

    def audit_events(self, key: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT event FROM audit WHERE key = ? ORDER BY id", (key,))
            return [r[0] for r in rows]
