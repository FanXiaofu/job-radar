"""国聘网数据源：POST /api/jobs/v1/recom-job，返回结构化岗位，直接产出 parsed 条目。"""
import logging

from config import settings
from crawler.base import USER_AGENT, BaseSource, RawItem

logger = logging.getLogger(__name__)

API_URL = "https://gp-api.iguopin.com/api/jobs/v1/recom-job"
JOB_DETAIL_URL = "https://www.iguopin.com/job/detail/{job_id}"
PAGE_SIZE = 20

# 面向计算机/AI 方向的搜索关键词；None 表示默认推荐池
KEYWORDS = ["算法", "软件开发", "人工智能", "数据分析", "测试开发", None]

MAX_PAGES_PER_QUERY = 3


class IguopinSource(BaseSource):
    name = "iguopin"

    def crawl(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[str] = set()  # 跨关键词共享，避免重复条目虚增统计
        for keyword in KEYWORDS:
            items += self._crawl_keyword(keyword, seen_ids)
        logger.info("[iguopin] 共采集 %d 条", len(items))
        return items

    def _crawl_keyword(self, keyword: str | None, seen_ids: set[str]) -> list[RawItem]:
        items: list[RawItem] = []
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            try:
                data = self._request(keyword, page)
            except Exception as e:
                logger.error("[iguopin] keyword=%s page=%d 请求失败: %s", keyword, page, e)
                break
            job_list = data.get("list") or []
            if not job_list:
                break
            for job in job_list:
                job_id = job.get("job_id")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                items.append(self._to_item(job))
            total = data.get("total") or 0
            page_size = data.get("page_size") or PAGE_SIZE
            if total and page * page_size >= total:
                break
        return items

    def _request(self, keyword: str | None, page: int) -> dict:
        search: dict = {"page": page, "page_size": PAGE_SIZE}
        if keyword:
            search["keyword"] = keyword
        body = {"search": search,
                "recom": {"update_time": True, "company_nature": True, "hot_job": True}}
        headers = {"version": "5.2.300", "Origin": "https://www.iguopin.com",
                   "Referer": "https://www.iguopin.com/job"}
        payload = self.post(API_URL, json_body=body, headers=headers)
        if payload.get("code") != 200:
            raise RuntimeError(f"API 返回异常: {payload.get('code')} {payload.get('msg')}")
        return payload["data"]

    def _to_item(self, job: dict) -> RawItem:
        detail_url = JOB_DETAIL_URL.format(job_id=job.get("job_id", ""))
        recruit_raw = (job.get("nature_cn") or job.get("recruitment_type_cn") or "")
        recruit_type = "campus" if ("校" in recruit_raw or "实习" in recruit_raw) else "social"
        locations = "、".join(
            d.get("area_cn") or d.get("address") or ""
            for d in (job.get("district_list") or []))
        requirements = "；".join(filter(None, [
            job.get("category_cn"), job.get("education_cn"),
            job.get("experience_cn")]))
        contents = (job.get("contents") or "").strip()
        deadline = (job.get("end_time") or "")[:10]
        if deadline:
            requirements += f"（报名截止 {deadline}）"
        parsed = {
            "company_name": (job.get("company_name") or "").strip(),
            "title": (job.get("job_name") or "").strip(),
            "recruit_type": recruit_type,
            "requirements": requirements or contents[:300],
            "location": locations,
            "apply_url": detail_url,
            "deadline": deadline,
        }
        return RawItem(source=self.name, url=detail_url,
                       raw_text=contents or requirements, title=parsed["title"],
                       parsed=parsed)
