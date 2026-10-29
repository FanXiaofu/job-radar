"""采集调度：CLI、定时任务、首次访问懒更新共用，带并发锁。"""
import logging
import threading

from config import settings
from db import repository
from db.database import get_conn, now_str

logger = logging.getLogger("crawl_service")
_crawl_lock = threading.Lock()


def build_sources():
    """注册所有数据源；单个源导入失败不影响其他源。"""
    from crawler.sources import registry
    return registry.get_sources()


def has_running_crawl() -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM crawl_runs WHERE status = 'running' LIMIT 1"
        ).fetchone()
    return row is not None


def needs_daily_crawl(stats: dict, running: bool, today: str) -> bool:
    """判断是否需要补一轮：空库、今天没有成功记录、或今天记录失败。"""
    if running:
        return False
    if not stats.get("total"):
        return True
    last = stats.get("last_run") or {}
    if not last:
        return True
    finished = (last.get("finished_at") or "")[:10]
    return finished != today or last.get("status") not in ("success", "partial")


def run_crawl() -> bool:
    """执行一轮采集；已有采集在跑时直接跳过，返回是否真正执行。"""
    if not _crawl_lock.acquire(blocking=False):
        logger.info("已有采集在运行，跳过本轮")
        return False
    try:
        from pipeline import Pipeline

        sources = build_sources()
        if not sources:
            logger.error("没有可用的数据源")
            return False
        Pipeline().run(sources)
        return True
    finally:
        _crawl_lock.release()


def maybe_crawl_daily() -> bool:
    """首次访问时检查；返回 True 表示页面应提示“后台更新中”。"""
    if not settings.lazy_crawl_enabled:
        return False
    if has_running_crawl():
        return True
    stats = repository.count_jobs(include_stale=True)
    if not needs_daily_crawl(stats, False, now_str()[:10]):
        return False
    logger.info("当天还没有成功采集，启动后台采集")
    threading.Thread(target=run_crawl, daemon=True, name="daily-crawl").start()
    return True
