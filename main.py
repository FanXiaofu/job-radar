"""秋招雷达入口。

用法：
    python main.py serve   # 启动 Web + 每日定时采集（默认 09:00）
    python main.py crawl   # 立即执行一轮采集
"""
import argparse
import logging
import sys
from pathlib import Path

from config import settings, PROJECT_ROOT
from db.database import init_db

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")],
)
logger = logging.getLogger("main")


def build_sources():
    """注册所有数据源；单个源导入失败不影响其他源。"""
    from crawler.sources import registry
    return registry.get_sources()


def run_crawl() -> None:
    from pipeline import Pipeline
    sources = build_sources()
    if not sources:
        logger.error("没有可用的数据源")
        return
    Pipeline().run(sources)


def run_serve() -> None:
    import threading

    import uvicorn
    from apscheduler.schedulers.background import BackgroundScheduler

    from db import repository

    # 空库自动首采（后台线程）：应对容器平台数据盘重置后的冷启动
    if repository.count_jobs()["total"] == 0:
        logger.info("数据库为空，后台线程先执行首轮采集，Web 服务不阻塞")
        threading.Thread(target=run_crawl, daemon=True, name="first-crawl").start()

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(run_crawl, "cron",
                      hour=settings.schedule_hour, minute=settings.schedule_minute,
                      id="daily_crawl", max_instances=1,
                      misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    logger.info("定时采集已启动：每天 %02d:%02d", settings.schedule_hour, settings.schedule_minute)
    uvicorn.run("app.main:app", host=settings.web_host, port=settings.web_port)


def main() -> None:
    parser = argparse.ArgumentParser(description="秋招雷达")
    parser.add_argument("command", choices=["serve", "crawl"], help="serve=Web+定时任务, crawl=立即采集")
    args = parser.parse_args()
    init_db()
    if args.command == "crawl":
        run_crawl()
    else:
        run_serve()


if __name__ == "__main__":
    sys.exit(main())
