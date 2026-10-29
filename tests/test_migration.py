"""旧库迁移测试：补 deadline 列和索引，不丢已有数据。

运行：python tests/test_migration.py
"""
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from db.database import get_conn, init_db  # noqa: E402

OLD_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    title TEXT NOT NULL,
    recruit_type TEXT,
    category TEXT,
    requirements TEXT,
    location TEXT,
    apply_url TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
"""


@contextmanager
def old_db():
    old_path = settings.db_path
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript(OLD_SCHEMA)
        conn.execute(
            """INSERT INTO jobs
               (company_name, title, recruit_type, category, requirements, location,
                apply_url, source, source_url, content_hash, first_seen, last_seen)
               VALUES ('旧公司', '旧岗位', 'campus', 'central', '', '北京',
                       '', 'fake', '', 'old-hash', '2026-01-01', '2026-01-01')"""
        )
        conn.commit()
        conn.close()

        settings.db_path = path
        init_db()
        try:
            yield path
        finally:
            settings.db_path = old_path


def test_deadline_migration():
    with old_db():
        with get_conn() as conn:
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
            assert "deadline" in columns
            indexes = {r["name"] for r in conn.execute("PRAGMA index_list(jobs)")}
            assert "idx_jobs_deadline" in indexes

            row = conn.execute(
                "SELECT company_name, deadline FROM jobs"
            ).fetchone()
            assert row["company_name"] == "旧公司", "迁移不应丢数据"
            assert row["deadline"] is None
        print("test_deadline_migration 通过")


if __name__ == "__main__":
    test_deadline_migration()
    print("全部通过")
