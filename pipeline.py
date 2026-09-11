"""采集流水线：数据源 -> 原始留档 -> LLM 抽取 -> 分类 -> 去重 -> 入库。"""
import logging
import sqlite3

from db import repository
from db.database import get_conn, init_db

from agent.classifier import CompanyClassifier
from agent.dedup import is_duplicate
from agent.extractor import JobExtractor

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self):
        self.extractor = JobExtractor()
        self.classifier = CompanyClassifier()

    def run(self, sources: list) -> dict:
        """sources: 已实例化的 BaseSource 子类列表。返回本次运行统计。"""
        init_db()
        with get_conn() as conn:
            run_id = repository.start_run(conn)
        stats = {"total_raw": 0, "new_jobs": 0, "updated_jobs": 0,
                 "duplicates": 0, "errors": 0, "detail": ""}
        errors: list[str] = []
        all_items = []

        for source in sources:
            try:
                items = source.crawl()
                all_items.extend(items)
                logger.info("[%s] 采集 %d 条", source.name, len(items))
            except Exception as e:
                msg = f"{source.name} 采集失败: {e}"
                logger.exception(msg)
                errors.append(msg)

        stats["total_raw"] = len(all_items)
        with get_conn() as conn:
            repository.save_raw_items(conn, run_id, [
                {"source": it.source, "url": it.url, "raw_text": it.raw_text}
                for it in all_items])
        # 抽取与入库
        for item in all_items:
            try:
                self._process(item, stats)
            except Exception as e:
                stats["errors"] += 1
                errors.append(f"处理失败 {item.url[:60]}: {e}")
                logger.exception("处理条目失败: %s", item.url)

        stats["detail"] = "; ".join(errors[:20])
        status = "success" if not errors else ("partial" if stats["new_jobs"] + stats["updated_jobs"] else "failed")
        with get_conn() as conn:
            repository.finish_run(conn, run_id, status, stats)
        logger.info("流水线完成: %s", {k: v for k, v in stats.items() if k != "detail"})
        return stats

    def _process(self, item, stats: dict) -> None:
        if item.parsed:
            job = dict(item.parsed)  # 结构化接口直出，不走 LLM
        else:
            job = self.extractor.extract(item.raw_text)
        if not job:
            stats["errors"] += 1
            return
        job["source"] = item.source
        job["source_url"] = item.url

        company = job.get("company_name", "").strip()
        if not company or not job.get("title"):
            stats["errors"] += 1
            return

        category, cat_source, confidence = self.classifier.classify(
            company, default="central" if item.source == "iguopin" else "private")
        job["category"] = category
        job["content_hash"] = repository.make_hash(
            company, job.get("title", ""), job.get("location", ""), job.get("apply_url", ""))

        with get_conn() as conn:
            repository.upsert_company(conn, company, category, cat_source, confidence)
            existing_jobs = [dict(r) for r in conn.execute(
                "SELECT id, company_name, title, apply_url FROM jobs WHERE company_name = ?",
                (company,))]
            dup = is_duplicate(job, existing_jobs)
            if dup:
                stats["duplicates"] += 1
                repository.touch_job(conn, dup["id"], job)
                stats["updated_jobs"] += 1
            else:
                repository.insert_job(conn, job)
                stats["new_jobs"] += 1
