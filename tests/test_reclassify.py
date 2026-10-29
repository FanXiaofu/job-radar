"""企业重分类脚本测试：临时 SQLite，不依赖网络和 LLM。

运行：python tests/test_reclassify.py
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
from reclassify_companies import reclassify  # noqa: E402


@contextmanager
def temp_db():
    old = (settings.db_path, settings.llm_api_key)
    with tempfile.TemporaryDirectory() as tmp:
        settings.db_path = Path(tmp) / "test.db"
        settings.llm_api_key = ""
        init_db()
        try:
            yield
        finally:
            settings.db_path, settings.llm_api_key = old


def _company(conn, name, category="unknown", source="default", confidence=0.3):
    now = now_str()
    conn.execute(
        """INSERT INTO companies
           (name, category, category_source, confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, category, source, confidence, now, now),
    )


def _job(conn, company, title):
    url = f"https://example.com/{title}"
    repository.insert_job(conn, {
        "company_name": company,
        "title": title,
        "recruit_type": "campus",
        "category": "unknown",
        "requirements": "",
        "location": "北京",
        "deadline": "",
        "apply_url": url,
        "source": "fake",
        "source_url": url,
        "content_hash": repository.make_hash(company, title, "北京", url),
    })


def test_reclassify_companies():
    with temp_db():
        with get_conn() as conn:
            _company(conn, "华为技术有限公司")
            _company(conn, "中国东方电气集团有限公司")
            _company(conn, "微软（中国）")
            _company(conn, "某不知名公司")
            _job(conn, "华为技术有限公司", "岗位A")
            _job(conn, "中国东方电气集团有限公司", "岗位B")
            _job(conn, "微软（中国）", "岗位C")
            _job(conn, "某不知名公司", "岗位D")

            dry = reclassify(conn, apply=False)
            assert dry["companies"] == 3, dry
            assert dry["jobs"] == 3, dry
            row = conn.execute(
                "SELECT category FROM companies WHERE name = '华为技术有限公司'"
            ).fetchone()
            assert row["category"] == "unknown", "dry-run 不应写入"

            applied = reclassify(conn, apply=True)
            assert applied["companies"] == 3, applied
            assert applied["jobs"] == 3, applied

            companies = {r["name"]: (r["category"], r["category_source"]) for r in conn.execute(
                "SELECT name, category, category_source FROM companies")}
            assert companies["华为技术有限公司"] == ("private", "list")
            assert companies["中国东方电气集团有限公司"] == ("central", "list")
            assert companies["微软（中国）"] == ("foreign", "list")
            assert companies["某不知名公司"] == ("unknown", "default")

            jobs = {r["title"]: r["category"] for r in conn.execute(
                "SELECT title, category FROM jobs")}
            assert jobs["岗位A"] == "private"
            assert jobs["岗位B"] == "central"
            assert jobs["岗位C"] == "foreign"
            assert jobs["岗位D"] == "unknown"

            again = reclassify(conn, apply=True)
            assert again["companies"] == 0 and again["jobs"] == 0, "脚本应可重复执行"
        print("test_reclassify_companies 通过")


if __name__ == "__main__":
    test_reclassify_companies()
    print("全部通过")
