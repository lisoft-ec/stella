"""SQLite storage: counted events, pending deliveries per sink, key/value state."""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE NOT NULL,
    ts TEXT NOT NULL,
    direction TEXT NOT NULL,
    data TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sink TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try REAL NOT NULL DEFAULT 0,
    last_error TEXT,
    delivered REAL,
    PRIMARY KEY (event_id, sink)
);
CREATE INDEX IF NOT EXISTS deliveries_pending ON deliveries(sink, delivered, event_id);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._db.close()

    # -- events -----------------------------------------------------------
    def add_event(self, event, sinks=()):
        """Store an event and queue it for each sink name. Returns its row id."""
        with self._lock:
            cur = self._db.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT INTO events (uid, ts, direction, data, created) VALUES (?, ?, ?, ?, ?)",
                    (event["uid"], event["ts"], event["direction"], json.dumps(event), time.time()))
                event_id = cur.lastrowid
                for sink in sinks:
                    cur.execute("INSERT INTO deliveries (event_id, sink) VALUES (?, ?)", (event_id, sink))
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
            return event_id

    def events(self, since_id=0, limit=100):
        with self._lock:
            rows = self._db.execute(
                "SELECT id, data FROM events WHERE id > ? ORDER BY id DESC LIMIT ?",
                (int(since_id), int(limit))).fetchall()
        return [dict(json.loads(r["data"]), id=r["id"]) for r in rows]

    def pending(self, sink, limit=50, now=None):
        """Undelivered events for ``sink`` whose retry time has come, oldest first."""
        now = time.time() if now is None else now
        with self._lock:
            rows = self._db.execute(
                "SELECT e.id, e.data, d.attempts FROM deliveries d JOIN events e ON e.id = d.event_id "
                "WHERE d.sink = ? AND d.delivered IS NULL AND d.next_try <= ? "
                "ORDER BY e.id LIMIT ?", (sink, now, int(limit))).fetchall()
        return [(r["id"], json.loads(r["data"]), r["attempts"]) for r in rows]

    def pending_count(self, sink=None):
        query = "SELECT COUNT(*) FROM deliveries WHERE delivered IS NULL"
        args = ()
        if sink:
            query += " AND sink = ?"
            args = (sink,)
        with self._lock:
            return self._db.execute(query, args).fetchone()[0]

    def mark_delivered(self, event_id, sink):
        with self._lock:
            self._db.execute(
                "UPDATE deliveries SET delivered = ?, last_error = NULL WHERE event_id = ? AND sink = ?",
                (time.time(), event_id, sink))

    def mark_failed(self, event_id, sink, error, retry_in):
        with self._lock:
            self._db.execute(
                "UPDATE deliveries SET attempts = attempts + 1, last_error = ?, next_try = ? "
                "WHERE event_id = ? AND sink = ?",
                (str(error)[:500], time.time() + retry_in, event_id, sink))

    def prune(self, keep_days=90):
        """Delete old events whose deliveries are all done (or that had none)."""
        limit = time.time() - keep_days * 86400
        with self._lock:
            self._db.execute(
                "DELETE FROM events WHERE created < ? AND id NOT IN "
                "(SELECT event_id FROM deliveries WHERE delivered IS NULL)", (limit,))

    # -- key/value state --------------------------------------------------
    def get(self, key, default=None):
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value)))
