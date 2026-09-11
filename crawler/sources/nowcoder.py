"""牛客网数据源：POST /np-api/u/job/square-search（校招/社招职位），公司名通过公司页解析。"""
import logging
import re
from datetime import datetime, timezone

import httpx

from config import settings
from crawler.base import USER_AGENT, BaseSource, RawItem

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.nowcoder.com/np-api/u/job/square-search"
COMPANY_PAGE_URL = "https://www.nowcoder.com/enterprise/{company_id}"
COMPANY_TITLE_RE = re.compile(r"^(.*?)(?:\d{4}年校招职位信息|校招职位信息|企业主页)")

# recruitType: 1=校招 2=实习 3=社招
RECRUIT_TYPE_MAP = {1: "campus", 2: "campus", 3: "social"}

# 面向计算机/AI 方向的搜索关键词
KEYWORDS = ["算法", "后端开发", "前端开发", "人工智能", "数据分析", "测试开发", "客户端开发"]

MAX_PAGES_PER_QUERY = 5
PAGE_SIZE = 20


class NowcoderSource(BaseSource):
    name = "nowcoder"

    def __init__(self):
        super().__init__()
        self._company_names: dict[int, str] = {}

    def crawl(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[int] = set()
        for query in KEYWORDS:
            items += self._crawl_query(query, seen_ids)
        logger.info("[nowcoder] 共采集 %d 条", len(items))
        return items

    def _crawl_query(self, query: str, seen_ids: set[int]) -> list[RawItem]:
        items: list[RawItem] = []
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            try:
                data = self._request(query, page)
            except Exception as e:
                logger.error("[nowcoder] query=%s page=%d 请求失败: %s", query, page, e)
                break
            rows = data.get("datas") or []
            if not rows:
                break
            for row in rows:
                job = row.get("data") or {}
                job_id = job.get("id")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                items.append(self._to_item(job))
            if page >= data.get("totalPage", 1):
                break
        return items

    def _request(self, query: str, page: int) -> dict:
        form = {"careerJobId": "", "jobCity": "", "page": str(page), "query": query,
                "random": "false", "recommend": "false", "recruitType": "1",
                "salaryType": "2", "pageSize": str(PAGE_SIZE), "requestFrom": "1",
                "order": "0", "pageSource": "5001"}
        headers = {"User-Agent": USER_AGENT,
                   "Content-Type": "application/x-www-form-urlencoded",
                   "Referer": "https://www.nowcoder.com/jobs/school/jobs"}
        resp = httpx.post(SEARCH_URL, data=form, headers=headers,
                          timeout=settings.request_timeout)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"API 返回异常: {payload.get('code')} {payload.get('msg')}")
        self._throttle()
        return payload["data"]

    def _company_name(self, company_id: int) -> str:
        """公司名在职位接口中为 null，从公司 SSR 页面标题解析，结果进程内缓存。"""
        if company_id in self._company_names:
            return self._company_names[company_id]
        name = ""
        url = COMPANY_PAGE_URL.format(company_id=company_id)
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT},
                             timeout=settings.request_timeout, follow_redirects=True)
            m = re.search(r"<title>([^<]*)</title>", resp.text)
            if m:
                tm = COMPANY_TITLE_RE.match(m.group(1).strip())
                name = (tm.group(1) if tm else m.group(1)).strip(" -_|")
        except httpx.HTTPError as e:
            logger.warning("[nowcoder] 公司页获取失败 %s: %s", url, e)
        self._company_names[company_id] = name
        self._throttle()
        return name

    @staticmethod
    def _ts_to_date(ts) -> str:
        if not ts:
            return ""
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    def _to_item(self, job: dict) -> RawItem:
        company_id = job.get("company_id") or job.get("companyId")
        company = self._company_name(company_id) if company_id else ""
        cities = "、".join(str(c) for c in (job.get("jobCityList") or []))
        salary = job.get("salaryShow") or ""
        deadline = self._ts_to_date(job.get("deliverEnd"))
        req_parts = [p for p in [salary, job.get("eduLevel"), job.get("graduationYear")] if p]
        if deadline:
            req_parts.append(f"投递截止 {deadline}")
        # ext 内含完整 JD（infos/requirements），优先使用
        ext = job.get("ext")
        try:
            jd = ""
            if isinstance(ext, dict):
                jd = (ext.get("infos") or ext.get("requirements") or "")
            elif isinstance(ext, str) and ext.strip().startswith("{"):
                import json
                jd = json.loads(ext)
                jd = jd.get("infos") or jd.get("requirements") or ""
            if jd:
                req_parts.append(str(jd)[:300])
        except Exception:
            pass
        recruit_type = RECRUIT_TYPE_MAP.get(job.get("recruitType"), "social")
        source_url = COMPANY_PAGE_URL.format(company_id=company_id) if company_id else ""
        external = job.get("redirectExternalUrl")
        parsed = {
            "company_name": company,
            "title": (job.get("jobName") or "").strip(),
            "recruit_type": recruit_type,
            "requirements": "；".join(str(p) for p in req_parts),
            "location": cities,
            "apply_url": external if isinstance(external, str) and external.startswith("http") else "",
            "deadline": deadline,
        }
        return RawItem(source=self.name, url=source_url,
                       raw_text=f"{parsed['title']} {parsed['requirements']} {cities}",
                       title=parsed["title"], parsed=parsed)
