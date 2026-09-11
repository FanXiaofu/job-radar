"""SQLite 存取层：建表、连接、常用查询。全部使用参数化查询。

时间口径：全库统一存北京时间（Asia/Shanghai），与调度时区、用户认知一致。
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from config import settings

_lock = threading.Lock()
_BJ_TZ = timezone(timedelta(hours=8))

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT,               -- central=央国企 / private=民企 / foreign=外企
    category_source TEXT,        -- list=名录匹配 / llm=模型判断 / default=兜底
    confidence REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    title TEXT NOT NULL,
    recruit_type TEXT,           -- campus=校招 / social=社招
    category TEXT,               -- 冗余自 companies，便于筛选
    requirements TEXT,
    location TEXT,
    apply_url TEXT,
    source TEXT NOT NULL,        -- iguopin / nowcoder / search
    source_url TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);
CREATE INDEX IF NOT EXISTS idx_jobs_recruit_type ON jobs(recruit_type);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT DEFAULT 'running',  -- running / success / partial / failed
    total_raw INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    updated_jobs INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    raw_text TEXT,
    created_at TEXT NOT NULL
);
"""


def now_str() -> str:
    """当前北京时间，全库统一时间戳口径。"""
    return datetime.now(_BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, get_conn() as conn:
        # WAL：APScheduler 后台线程写 + uvicorn 线程池读并发时避免锁等待
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.executescript(SCHEMA)
