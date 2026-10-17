"""SQLite store: accounts, projects, api keys, usage + health."""
from __future__ import annotations
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterable

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    email       TEXT PRIMARY KEY,
    password_ref TEXT,          -- vault handle / label; never the secret itself
    recovery    TEXT,
    status      TEXT DEFAULT 'new',   -- new|logged_in|keys_created|banned|error
    created_at  REAL,
    updated_at  REAL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT,
    project_id  TEXT UNIQUE,
    project_num TEXT,
    status      TEXT DEFAULT 'new',  -- new|created|api_enabled|error
    created_at  REAL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT UNIQUE,
    email       TEXT,
    project_id  TEXT,
    key_type    TEXT DEFAULT 'auth',
    model_scope TEXT,
    status      TEXT DEFAULT 'active',  -- active|quota|invalid|disabled
    rpd_used    INTEGER DEFAULT 0,
    last_used   REAL,
    last_error  TEXT,
    created_at  REAL
);
CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT,
    model       TEXT,
    ts          REAL,
    ok          INTEGER,
    http_status INTEGER,
    latency_ms  INTEGER,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_key ON usage(key);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
CREATE INDEX IF NOT EXISTS idx_keys_status ON api_keys(status);
"""


class Store:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self._init()

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _init(self):
        with self.conn() as c:
            c.executescript(SCHEMA)

    # ---- accounts ----
    def upsert_account(self, email: str, password_ref: str = "", recovery: str = "",
                       status: str = "new", note: str = "") -> None:
        now = time.time()
        with self.conn() as c:
            c.execute(
                """INSERT INTO accounts(email,password_ref,recovery,status,created_at,updated_at,note)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(email) DO UPDATE SET
                     password_ref=excluded.password_ref, recovery=excluded.recovery,
                     status=excluded.status, updated_at=excluded.updated_at, note=excluded.note""",
                (email, password_ref, recovery, status, now, now, note),
            )

    def set_account_status(self, email: str, status: str, note: str = "") -> None:
        with self.conn() as c:
            c.execute("UPDATE accounts SET status=?, note=?, updated_at=? WHERE email=?",
                      (status, note, time.time(), email))

    def accounts(self, status: str | None = None) -> list[sqlite3.Row]:
        with self.conn() as c:
            if status:
                return c.execute("SELECT * FROM accounts WHERE status=? ORDER BY created_at", (status,)).fetchall()
            return c.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()

    # ---- projects ----
    def add_project(self, email: str, project_id: str, project_num: str = "",
                    status: str = "created") -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO projects(email,project_id,project_num,status,created_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(project_id) DO UPDATE SET status=excluded.status""",
                (email, project_id, project_num, status, time.time()),
            )

    def projects(self, email: str | None = None) -> list[sqlite3.Row]:
        with self.conn() as c:
            if email:
                return c.execute("SELECT * FROM projects WHERE email=? ORDER BY id", (email,)).fetchall()
            return c.execute("SELECT * FROM projects ORDER BY id").fetchall()

    # ---- keys ----
    def add_key(self, key: str, email: str = "", project_id: str = "",
                key_type: str = "auth", model_scope: str = "") -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO api_keys(key,email,project_id,key_type,model_scope,status,created_at)
                   VALUES(?,?,?,?,?,'active',?)
                   ON CONFLICT(key) DO NOTHING""",
                (key, email, project_id, key_type, model_scope, time.time()),
            )

    def set_key_status(self, key: str, status: str, error: str = "") -> None:
        with self.conn() as c:
            c.execute("UPDATE api_keys SET status=?, last_error=? WHERE key=?",
                      (status, error, key))

    def bump_key(self, key: str, ok: bool, http_status: int = 0, detail: str = "") -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE api_keys SET rpd_used=rpd_used+1, last_used=?, last_error=? WHERE key=?",
                (time.time(), "" if ok else detail[:500], key),
            )

    def active_keys(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT key FROM api_keys WHERE status='active' ORDER BY rpd_used ASC, last_used ASC"
            ).fetchall()
            return [r["key"] for r in rows]

    def all_keys(self) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()

    def keys_table(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    # ---- usage ----
    def log_usage(self, key: str, model: str, ok: bool, http_status: int,
                  latency_ms: int, detail: str = "") -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO usage(key,model,ts,ok,http_status,latency_ms,detail)
                   VALUES(?,?,?,?,?,?,?)""",
                (key, model, time.time(), 1 if ok else 0, http_status, latency_ms, detail[:500]),
            )

    def stats(self) -> dict[str, Any]:
        with self.conn() as c:
            out: dict[str, Any] = {}
            out["accounts"] = c.execute("SELECT COUNT(*) n FROM accounts").fetchone()["n"]
            for s in ("new", "logged_in", "keys_created", "banned", "error"):
                out[f"accounts_{s}"] = c.execute(
                    "SELECT COUNT(*) n FROM accounts WHERE status=?", (s,)).fetchone()["n"]
            out["keys_total"] = c.execute("SELECT COUNT(*) n FROM api_keys").fetchone()["n"]
            for s in ("active", "quota", "invalid", "disabled"):
                out[f"keys_{s}"] = c.execute(
                    "SELECT COUNT(*) n FROM api_keys WHERE status=?", (s,)).fetchone()["n"]
            out["projects"] = c.execute("SELECT COUNT(*) n FROM projects").fetchone()["n"]
            out["req_total"] = c.execute("SELECT COUNT(*) n FROM usage").fetchone()["n"]
            out["req_ok"] = c.execute("SELECT COUNT(*) n FROM usage WHERE ok=1").fetchone()["n"]
            out["req_429"] = c.execute("SELECT COUNT(*) n FROM usage WHERE http_status=429").fetchone()["n"]
            return out

    def export_keys_jsonl(self, path) -> int:
        keys = self.keys_table()
        with open(path, "w", encoding="utf-8") as f:
            for k in keys:
                f.write(json.dumps(k) + "\n")
        return len(keys)


def load_accounts_jsonl(path) -> list[dict]:
    import os
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
