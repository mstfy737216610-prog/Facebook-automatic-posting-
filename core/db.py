"""قاعدة بيانات فيسبوك المنفصلة - لا تتداخل مع مشروع تويتر/تلجرام إطلاقًا."""
import sqlite3
import json
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "db" / "facebook_memory.db"
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT UNIQUE,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    niche TEXT DEFAULT 'general',      -- masters | phd | services | general ...
    members INTEGER DEFAULT 0,
    account_id TEXT,                   -- الحساب الذي اكتشفها
    status TEXT DEFAULT 'new',         -- new | approved | excluded | joined
    discovered_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,                   -- مفتاح المنشور في المكتبة
    niche TEXT NOT NULL,               -- لأي فئة: masters, phd...
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    media_paths TEXT DEFAULT '[]',
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    niche TEXT NOT NULL,
    post_id INTEGER REFERENCES posts(id),
    status TEXT DEFAULT 'pending',     -- pending | publishing | done | failed
    target_group TEXT,
    error TEXT,
    run_at REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS publish_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    group_url TEXT,
    post_id INTEGER,
    success INTEGER NOT NULL,
    error TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    username TEXT,
    proxy TEXT,
    enabled INTEGER DEFAULT 1,
    status TEXT DEFAULT 'stopped',
    last_error TEXT,
    created_at REAL NOT NULL
);
"""


def get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return _local.conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def q(sql, params=(), one=False):
    conn = get_conn()
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    conn.commit()
    if one:
        return rows[0] if rows else None
    return rows


def add_group(url, name=None, members=0, niche="general", account_id=None, group_id=None):
    try:
        q("INSERT INTO groups (group_id, url, name, niche, members, account_id, discovered_at) VALUES (?,?,?,?,?,?,?)",
          (group_id, url, name, niche, members, account_id, time.time()))
        return True
    except sqlite3.IntegrityError:
        return False


def add_post(key, niche, title, text, media_paths=None):
    q("""INSERT INTO posts (key, niche, title, text, media_paths, created_at) VALUES (?,?,?,?,?,?)
         ON CONFLICT(key) DO UPDATE SET title=excluded.title, text=excluded.text, media_paths=excluded.media_paths""",
      (key, niche, title, text, json.dumps(media_paths or [], ensure_ascii=False), time.time()))


def add_schedule(account_id, niche, post_id, target_group, run_at):
    q("INSERT INTO schedules (account_id, niche, post_id, target_group, run_at, created_at) VALUES (?,?,?,?,?,?)",
      (account_id, niche, post_id, target_group, run_at, time.time()))


def save_account(acc):
    q("""INSERT INTO accounts (id, label, username, proxy, enabled, created_at) VALUES (?,?,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET label=excluded.label, username=excluded.username,
             proxy=excluded.proxy, enabled=excluded.enabled""",
      (acc["id"], acc.get("label", ""), acc.get("username"), acc.get("proxy"),
       1 if acc.get("enabled", True) else 0, time.time()))


def get_accounts():
    return [dict(r) for r in q("SELECT * FROM accounts")]


def log_publish(account_id, group_url, post_id, success, error=None):
    q("INSERT INTO publish_log (account_id, group_url, post_id, success, error, created_at) VALUES (?,?,?,?,?,?)",
      (account_id, group_url, post_id, 1 if success else 0, error, time.time()))
