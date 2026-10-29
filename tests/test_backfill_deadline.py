"""deadline 回填脚本测试：dry-run、写入、已有值不覆盖、幂等。

运行：python tests/test_backfill_deadline.py
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
from db.database import get_conn, init_db  # noqa: E402
from backfill_deadline import backfill  # noqa: E402


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


def _job(conn, title, requirements, deadline=""):
    url = f"https://example.com/{title}"
    repository.insert_job(conn, {
        "company_name": "测试公司",
        "title": title,
        "recruit_type": "campus",
        "category": "central",
        "requirements": requirements,
        "location": "北京",
        "deadline": deadline,
        "apply_url": url,
        "source": "fake",
        "source_url": url,
        "content_hash": repository.make_hash("测试公司", title, "北京", url),
    })


def test_backfill_deadline():
    with temp_db():
        with get_conn() as conn:
            _job(conn, "岗位A", "本科；报名截止 2026-12-31")
            _job(conn, "岗位B", "；投递截止 2026-11-30；JD")
            _job(conn, "岗位C", "没有截止日期")
            _job(conn, "岗位D", "报名截止 2026-10-01", deadline="2026-09-01")
            _job(conn, "岗位E", "报名截止 2126-10-28", deadline="2126-10-28")

            dry = backfill(conn, apply=False)
            assert dry == {"jobs": 2, "cleared": 1}, dry
            row = conn.execute(
                "SELECT deadline FROM jobs WHERE title = '岗位A'"
            ).fetchone()
            assert row["deadline"] == "", "dry-run 不应写入"

            applied = backfill(conn, apply=True)
            assert applied == {"jobs": 2, "cleared": 1}, applied
            rows = {r["title"]: r["deadline"] for r in conn.execute(
                "SELECT title, deadline FROM jobs")}
            assert rows["岗位A"] == "2026-12-31"
            assert rows["岗位B"] == "2026-11-30"
            assert rows["岗位C"] == ""
            assert rows["岗位D"] == "2026-09-01", "已有值不应被覆盖"
            assert rows["岗位E"] == "", "超过 5 年的哨兵值应清空"
            req_e = conn.execute(
                "SELECT requirements FROM jobs WHERE title = '岗位E'"
            ).fetchone()["requirements"]
            assert "2126" not in req_e, "哨兵日期文本也应清理"

            again = backfill(conn, apply=True)
            assert again == {"jobs": 0, "cleared": 0}, "脚本应可重复执行"
        print("test_backfill_deadline 通过")


if __name__ == "__main__":
    test_backfill_deadline()
    print("全部通过")
