"""懒更新判断测试：不启动真实采集、不访问网络。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawl_service import needs_daily_crawl  # noqa: E402

TODAY = "2026-10-30"


def test_needs_daily_crawl():
    assert needs_daily_crawl({"total": 0, "last_run": None}, False, TODAY)
    assert needs_daily_crawl({"total": 5, "last_run": None}, False, TODAY)
    assert needs_daily_crawl(
        {"total": 5, "last_run": {"finished_at": "2026-10-29 10:00:00", "status": "success"}},
        False, TODAY,
    )
    assert not needs_daily_crawl(
        {"total": 5, "last_run": {"finished_at": "2026-10-30 10:00:00", "status": "success"}},
        False, TODAY,
    )
    assert not needs_daily_crawl(
        {"total": 5, "last_run": {"finished_at": "2026-10-30 10:00:00", "status": "partial"}},
        False, TODAY,
    )
    assert needs_daily_crawl(
        {"total": 5, "last_run": {"finished_at": "2026-10-30 10:00:00", "status": "failed"}},
        False, TODAY,
    )
    assert not needs_daily_crawl(
        {"total": 5, "last_run": {"finished_at": "2026-10-30 10:00:00", "status": "success"}},
        True, TODAY,
    )
