"""采集流水线：数据源 -> 原始留档 -> （结构化直出 | LLM 抽取）-> 分类 -> 去重 -> 入库。"""
import logging

from db import repository
from db.database import get_conn, init_db

from agent.classifier import CompanyClassifier
from agent.dedup import is_duplicate
from agent.extractor import JobExtractor
from agent.search_agent import SearchAgent

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http://", "https://")
# 入库必需字段，缺失时补空串，避免 SQL 绑定参数缺失
REQUIRED_FIELDS = ("company_name", "title", "recruit_type", "category",
                   "requirements", "location", "apply_url", "source", "source_url")


class Pipeline:
    def __init__(self):
        self.extractor = JobExtractor()
        self.classifier = CompanyClassifier()

    def run(self, sources: list) -> dict:
        """sources: 已实例化的 BaseSource 子类列表。返回本次运行统计。"""
        init_db()
        stats = {"total_raw": 0, "new_jobs": 0, "duplicates": 0, "errors": 0, "detail": ""}
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

        # 搜索 Agent 作为补充渠道：需要 LLM（落地页为非结构化文本）
        if settings_search_enabled():
            try:
                found = SearchAgent().run()
                all_items.extend(found)
                logger.info("[search] 补充候选 %d 条", len(found))
            except Exception as e:
                msg = f"搜索 Agent 失败: {e}"
                logger.exception(msg)
                errors.append(msg)

        stats["total_raw"] = len(all_items)
        with get_conn() as conn:
            run_id = repository.start_run(conn)
            repository.save_raw_items(conn, run_id, [
                {"source": it.source, "url": it.url, "raw_text": it.raw_text}
                for it in all_items])
            # 同一连接处理全部条目，避免几百次连接/提交开销
            for item in all_items:
                try:
                    self._process(conn, item, stats, errors)
                except Exception as e:
                    stats["errors"] += 1
                    errors.append(f"处理失败 {item.url[:60]}: {e}")
                    logger.exception("处理条目失败: %s", item.url)

        stats["detail"] = "; ".join(errors[:20])
        has_output = stats["new_jobs"] + stats["duplicates"] > 0
        status = "success" if not errors else ("partial" if has_output else "failed")
        with get_conn() as conn:
            repository.finish_run(conn, run_id, status, stats)
        logger.info("流水线完成: %s", {k: v for k, v in stats.items() if k != "detail"})
        return stats

    def _process(self, conn, item, stats: dict, errors: list) -> None:
        if item.parsed:
            job = dict(item.parsed)  # 结构化接口直出，不走 LLM
        else:
            job = self.extractor.extract(item.raw_text)
        if not job:
            stats["errors"] += 1
            return
        job["source"] = item.source
        job["source_url"] = item.url or ""

        company = (job.get("company_name") or "").strip()
        if not company or not (job.get("title") or "").strip():
            stats["errors"] += 1
            errors.append(f"缺少企业名或岗位名，丢弃: {item.source} {item.url[:60]}")
            return

        # 分类缓存：高置信度结果直接复用，未命中才走分类器（省 LLM 调用）
        cached = repository.get_company_category(conn, company)
        if cached and cached["confidence"] >= 0.5:
            category, cat_source, confidence = cached["category"], "cache", cached["confidence"]
        else:
            category, cat_source, confidence = self.classifier.classify(
                company, default="central" if item.source == "iguopin" else "private")
            repository.upsert_company(conn, company, category, cat_source, confidence)
        job["category"] = category

        # apply_url 白名单校验，杜绝 javascript: 等异常协议进入展示层
        apply_url = (job.get("apply_url") or "").strip()
        if apply_url and not apply_url.lower().startswith(ALLOWED_SCHEMES):
            apply_url = ""
        job["apply_url"] = apply_url
        job["content_hash"] = repository.make_hash(
            company, job.get("title", ""), job.get("location", ""), apply_url)
        for f in REQUIRED_FIELDS:
            job.setdefault(f, "")

        # 第一层：content_hash 精确去重（唯一索引，撞车说明完全同源同岗）
        existing = repository.find_job_by_hash(conn, job["content_hash"])
        if existing is None:
            # 第二层：同企业内 URL 归一化 + 标题相似度模糊去重
            existing_jobs = [dict(r) for r in conn.execute(
                "SELECT id, company_name, title, apply_url FROM jobs WHERE company_name = ?",
                (company,))]
            existing = is_duplicate(job, existing_jobs)
        if existing:
            stats["duplicates"] += 1
            repository.touch_job(conn, existing["id"], job)
        else:
            repository.insert_job(conn, job)
            stats["new_jobs"] += 1


def settings_search_enabled() -> bool:
    from config import settings
    return settings.search_enabled and settings.llm_enabled
