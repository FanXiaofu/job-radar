"""Web 路由测试：临时 SQLite + FastAPI TestClient，不依赖网络。

运行：python tests/test_web.py
"""
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from db import repository  # noqa: E402
from db.database import days_ago_str, get_conn, init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@contextmanager
def temp_db():
    old_path = settings.db_path
    old_lazy = settings.lazy_crawl_enabled
    settings.lazy_crawl_enabled = False
    with tempfile.TemporaryDirectory() as tmp:
        settings.db_path = Path(tmp) / "test.db"
        init_db()
        try:
            yield
        finally:
            settings.db_path = old_path
            settings.lazy_crawl_enabled = old_lazy


def _seed_job(company="测试央企", title="算法工程师", category="central",
              location="北京", apply_url="https://example.com/apply", deadline=""):
    with get_conn() as conn:
        repository.insert_job(conn, {
            "company_name": company,
            "title": title,
            "recruit_type": "campus",
            "category": category,
            "requirements": "硕士以上",
            "location": location,
            "deadline": deadline,
            "apply_url": apply_url,
            "source": "fake",
            "source_url": "https://example.com/job",
            "content_hash": repository.make_hash(company, title, location, apply_url),
        })


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_web_routes():
    with temp_db():
        _seed_job()
        client = _client()

        health = client.get("/health")
        assert health.status_code == 200, health.text
        assert health.json()["jobs"] == 1, health.json()
        assert health.json()["status"] == "ok"

        index = client.get("/")
        assert index.status_code == 200, index.text
        assert "算法工程师" in index.text
        assert "测试央企" in index.text

        assert client.get("/", params={"category": "central"}).status_code == 200
        assert client.get("/", params={"recruit_type": "campus"}).status_code == 200
        assert client.get("/", params={"keyword": "%"}).status_code == 200
        assert client.get("/", params={"page": -1}).status_code == 200

        xss = client.get("/", params={"keyword": "<script>alert(1)</script>"})
        assert xss.status_code == 200
        assert "<script>alert(1)</script>" not in xss.text, "关键词必须被转义"
        assert "&lt;script&gt;" in xss.text
        print("test_web_routes 通过")


def test_web_stale_filter():
    """默认只显示近期岗位，勾选后显示历史岗位，/health 同时返回两个口径。"""
    with temp_db():
        _seed_job(company="近期公司", title="近期岗位", category="central",
                  apply_url="https://example.com/recent")
        _seed_job(company="历史公司", title="历史岗位", category="central",
                  apply_url="https://example.com/old")
        with get_conn() as conn:
            conn.execute("UPDATE jobs SET last_seen = ? WHERE title = ?",
                         (days_ago_str(60), "历史岗位"))

        client = _client()
        index = client.get("/")
        assert index.status_code == 200
        assert "近期公司" in index.text
        assert "历史公司" not in index.text, "默认不应显示过期岗位"

        history = client.get("/", params={"include_stale": "1"})
        assert history.status_code == 200
        assert "历史公司" in history.text
        assert "近期公司" in history.text

        health = client.get("/health").json()
        assert health["jobs"] == 1, health
        assert health["jobs_total"] == 2, health
        print("test_web_stale_filter 通过")


def test_web_deadline_filter():
    """截止日期展示、只看未截止、按截止日期排序。"""
    with temp_db():
        soon = days_ago_str(-10)[:10]
        later = days_ago_str(-20)[:10]
        past = days_ago_str(5)[:10]
        _seed_job(company="未来公司A", title="未来岗位A", category="central",
                  apply_url="https://example.com/a", deadline=soon)
        _seed_job(company="未来公司B", title="未来岗位B", category="central",
                  apply_url="https://example.com/b", deadline=later)
        _seed_job(company="过期公司", title="过期岗位", category="central",
                  apply_url="https://example.com/c", deadline=past)
        _seed_job(company="无截止公司", title="无截止岗位", category="central",
                  apply_url="https://example.com/d", deadline="")

        client = _client()
        index = client.get("/")
        assert index.status_code == 200
        assert soon in index.text and later in index.text
        assert "过期公司" in index.text and "无截止公司" in index.text

        open_only = client.get("/", params={"open_only": "1"})
        assert open_only.status_code == 200
        assert "未来公司A" in open_only.text
        assert "未来公司B" in open_only.text
        assert "无截止公司" in open_only.text
        assert "过期公司" not in open_only.text, "只看未截止应隐藏已过期岗位"

        rows, total = repository.list_jobs(None, None, None, open_only=True, sort="deadline")
        assert total == 3, total
        deadlines = [r["deadline"] for r in rows if r["deadline"]]
        assert deadlines == sorted(deadlines), deadlines
        print("test_web_deadline_filter 通过")


def test_web_unknown_category():
    """未分类企业应有独立标签和筛选项，不能被当成央国企。"""
    with temp_db():
        _seed_job(company="未知公司", title="未知岗位", category="unknown",
                  apply_url="https://example.com/unknown")
        client = _client()

        index = client.get("/")
        assert index.status_code == 200
        assert "未分类" in index.text

        unknown = client.get("/", params={"category": "unknown"})
        assert unknown.status_code == 200
        assert "未知岗位" in unknown.text

        central = client.get("/", params={"category": "central"})
        assert central.status_code == 200
        assert "未知岗位" not in central.text, "未分类岗位不应出现在央国企筛选里"
        print("test_web_unknown_category 通过")


def test_web_daily_crawl_notice(monkeypatch):
    """首次访问触发补采时，页面应提示后台更新。"""
    with temp_db():
        _seed_job()
        import app.main as web

        monkeypatch.setattr(web, "maybe_crawl_daily", lambda: True)
        client = TestClient(web.app)
        index = client.get("/")
        assert index.status_code == 200
        assert "正在后台更新岗位" in index.text
        print("test_web_daily_crawl_notice 通过")


if __name__ == "__main__":
    test_web_routes()
    test_web_stale_filter()
    test_web_deadline_filter()
    test_web_unknown_category()
    print("全部通过")
