"""分类回填脚本测试：临时 SQLite，不依赖网络和 LLM。

运行：python tests/test_backfill.py
"""
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from config import settings  # noqa: E402
from db import repository  # noqa: E402
from db.database import get_conn, init_db, now_str  # noqa: E402
from backfill_unknown_category import backfill  # noqa: E402


@contextmanager
def temp_db():
    old_path = settings.db_path
    with tempfile.TemporaryDirectory() as tmp:
        settings.db_path = Path(tmp) / "test.db"
        init_db()
        try:
            yield
        finally:
            settings.db_path = old_path


def _company(conn, name, category, source, confidence):
    now = now_str()
    conn.execute(
        """INSERT INTO companies
           (name, category, category_source, confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, category, source, confidence, now, now),
    )


def _job(conn, company, title, category):
    url = f"https://example.com/{title}"
    repository.insert_job(conn, {
        "company_name": company,
        "title": title,
        "recruit_type": "campus",
        "category": category,
        "requirements": "",
        "location": "北京",
        "deadline": "",
        "apply_url": url,
        "source": "fake",
        "source_url": url,
        "content_hash": repository.make_hash(company, title, "北京", url),
    })


def test_backfill_unknown_category():
    with temp_db():
        with get_conn() as conn:
            _company(conn, "默认央国企", "central", "default", 0.3)
            _company(conn, "名录央国企", "central", "list", 1.0)
            _company(conn, "LLM民企", "private", "llm", 0.7)
            _company(conn, "已未分类", "unknown", "default", 0.3)
            _job(conn, "默认央国企", "岗位A", "central")
            _job(conn, "名录央国企", "岗位B", "central")
            _job(conn, "LLM民企", "岗位C", "private")
            _job(conn, "已未分类", "岗位D", "unknown")

            dry = backfill(conn, apply=False)
            assert dry == {"companies": 1, "jobs": 1}, dry
            row = conn.execute(
                "SELECT category FROM companies WHERE name = '默认央国企'"
            ).fetchone()
            assert row["category"] == "central", "dry-run 不应写入"

            applied = backfill(conn, apply=True)
            assert applied == {"companies": 1, "jobs": 1}, applied

            rows = {r["name"]: r["category"] for r in conn.execute(
                "SELECT name, category FROM companies")}
            assert rows["默认央国企"] == "unknown"
            assert rows["名录央国企"] == "central"
            assert rows["LLM民企"] == "private"
            assert rows["已未分类"] == "unknown"

            jobs = {r["title"]: r["category"] for r in conn.execute(
                "SELECT title, category FROM jobs")}
            assert jobs["岗位A"] == "unknown"
            assert jobs["岗位B"] == "central"
            assert jobs["岗位C"] == "private"
            assert jobs["岗位D"] == "unknown"

            again = backfill(conn, apply=True)
            assert again == {"companies": 0, "jobs": 0}, "脚本应可重复执行"
        print("test_backfill_unknown_category 通过")


if __name__ == "__main__":
    test_backfill_unknown_category()
    print("全部通过")
