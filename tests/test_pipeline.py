"""流水线集成测试：临时 SQLite + 假数据源，不依赖网络和 LLM。

运行：python tests/test_pipeline.py
"""
import logging
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 失败用例会触发 pipeline 的 logger.exception，测试输出只保留断言结果
logging.getLogger("pipeline").setLevel(logging.CRITICAL)

from config import settings  # noqa: E402
from crawler.base import BaseSource, RawItem  # noqa: E402
from db import repository  # noqa: E402
from db.database import get_conn, init_db  # noqa: E402
from pipeline import Pipeline  # noqa: E402


@contextmanager
def temp_db():
    old = (settings.db_path, settings.llm_api_key, settings.search_provider,
           settings.search_api_key)
    with tempfile.TemporaryDirectory() as tmp:
        settings.db_path = Path(tmp) / "test.db"
        # 测试固定走“无 LLM、无搜索”的路径，避免本机 .env 影响断言
        settings.llm_api_key = ""
        settings.search_provider = "none"
        settings.search_api_key = ""
        init_db()
        try:
            yield
        finally:
            (settings.db_path, settings.llm_api_key, settings.search_provider,
             settings.search_api_key) = old


class FakeSource(BaseSource):
    name = "fake"

    def __init__(self, items=None, error=None):
        super().__init__()
        self.items = items or []
        self.error = error

    def crawl(self) -> list[RawItem]:
        if self.error:
            raise self.error
        return self.items


def _item(company="测试公司", title="后端工程师", location="",
          url="https://example.com/a", deadline="2026-12-31"):
    return RawItem(
        source="fake",
        url=url,
        raw_text="raw",
        title=title,
        parsed={
            "company_name": company,
            "title": title,
            "recruit_type": "campus",
            "requirements": "本科以上",
            "location": location,
            "apply_url": url,
            "deadline": deadline,
        },
    )


def test_pipeline_metrics_and_enrichment():
    """新岗位、重复补字段、缺企业名三类条目应分别计数。"""
    with temp_db():
        source = FakeSource([
            _item(location="", url="https://example.com/a"),
            _item(location="北京", url="https://example.com/b"),
            _item(location="北京", url="https://example.com/d"),
            _item(company="", title="", url="https://example.com/c"),
        ])
        stats = Pipeline().run([source])

        assert stats["total_raw"] == 4, stats
        assert stats["new_jobs"] == 1, stats
        assert stats["duplicates"] == 2, stats
        assert stats["updated_jobs"] == 1, stats
        assert stats["errors"] == 1, stats

        with get_conn() as conn:
            jobs = conn.execute("SELECT * FROM jobs").fetchall()
            assert len(jobs) == 1, "重复岗位不应重复入库"
            assert jobs[0]["location"] == "北京", "重复条目应补齐空字段"
            assert jobs[0]["deadline"] == "2026-12-31", "结构化 deadline 应入库"
            assert jobs[0]["category"] == "unknown", "未命中名录/LLM 的企业应为未分类"

            company = conn.execute(
                "SELECT category, category_source FROM companies WHERE name = '测试公司'"
            ).fetchone()
            assert company["category"] == "unknown"
            assert company["category_source"] == "default"

            run = conn.execute("SELECT * FROM crawl_runs").fetchone()
            assert run["status"] == "partial", dict(run)
            assert run["total_raw"] == 4
            assert run["new_jobs"] == 1
            assert run["duplicates"] == 2
            assert run["updated_jobs"] == 1
            assert run["errors"] == 1
            assert run["finished_at"] is not None
            assert run["started_at"] <= run["finished_at"]

            raw_count = conn.execute("SELECT COUNT(*) c FROM raw_items").fetchone()["c"]
            assert raw_count == 4
        print("test_pipeline_metrics_and_enrichment 通过")


def test_pipeline_source_failure_records_failed_run():
    """数据源失败也必须留下 failed 记录，不能只写日志。"""
    with temp_db():
        stats = Pipeline().run([FakeSource(error=RuntimeError("boom"))])

        assert stats["errors"] >= 1, stats
        assert stats["new_jobs"] == 0, stats
        with get_conn() as conn:
            run = conn.execute("SELECT * FROM crawl_runs").fetchone()
            assert run["status"] == "failed", dict(run)
            assert run["total_raw"] == 0
            assert run["finished_at"] is not None
            assert "boom" in (run["detail"] or "")
            assert conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 0
        print("test_pipeline_source_failure_records_failed_run 通过")


def test_pipeline_rejects_invalid_deadline():
    """非法日期和超过 5 年的哨兵值都不应进入数据库。"""
    with temp_db():
        Pipeline().run([FakeSource([
            _item(title="岗位A", url="https://example.com/a", deadline="not-a-date"),
            _item(title="岗位B", url="https://example.com/b", deadline="2126-10-28"),
        ])])
        with get_conn() as conn:
            jobs = conn.execute("SELECT deadline FROM jobs ORDER BY title").fetchall()
            assert [j["deadline"] for j in jobs] == ["", ""]
        print("test_pipeline_rejects_invalid_deadline 通过")


def test_pipeline_empty_source_marks_failed():
    """空采集不是成功：必须标记 failed，避免接口变更后静默无数据。"""
    with temp_db():
        stats = Pipeline().run([FakeSource([])])

        assert stats["total_raw"] == 0, stats
        assert stats["errors"] == 1, stats
        with get_conn() as conn:
            run = conn.execute("SELECT * FROM crawl_runs").fetchone()
            assert run["status"] == "failed", dict(run)
            assert "未采集到任何条目" in (run["detail"] or "")
        print("test_pipeline_empty_source_marks_failed 通过")


def test_pipeline_unexpected_exception_marks_failed():
    """处理阶段异常应回滚计数并把运行记录标为 failed。"""
    with temp_db():
        original = repository.save_raw_items

        def boom(*args, **kwargs):
            raise RuntimeError("db save boom")

        repository.save_raw_items = boom
        try:
            try:
                Pipeline().run([FakeSource([_item()])])
            except RuntimeError as exc:
                assert "db save boom" in str(exc)
            else:
                raise AssertionError("应向上抛出处理异常")
        finally:
            repository.save_raw_items = original

        with get_conn() as conn:
            run = conn.execute("SELECT * FROM crawl_runs").fetchone()
            assert run["status"] == "failed", dict(run)
            assert run["finished_at"] is not None
            assert "db save boom" in (run["detail"] or "")
            assert run["new_jobs"] == 0
            assert run["duplicates"] == 0
            assert run["updated_jobs"] == 0
        print("test_pipeline_unexpected_exception_marks_failed 通过")


if __name__ == "__main__":
    test_pipeline_metrics_and_enrichment()
    test_pipeline_source_failure_records_failed_run()
    test_pipeline_rejects_invalid_deadline()
    test_pipeline_empty_source_marks_failed()
    test_pipeline_unexpected_exception_marks_failed()
    print("全部通过")
