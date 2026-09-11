"""牛客网数据源：POST /np-api/u/job/square-search（校招/社招职位），公司名通过公司页解析。"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from config import settings
from crawler.base import USER_AGENT, BaseSource, RawItem

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.nowcoder.com/np-api/u/job/square-search"
COMPANY_PAGE_URL = "https://www.nowcoder.com/enterprise/{company_id}"
COMPANY_TITLE_RE = re.compile(r"^(.*?)(?:\d{4}年校招职位信息|校招职位信息|企业主页)")
_BJ_TZ = timezone(timedelta(hours=8))

# recruitType: 1=校招 3=社招（2=实习并入校招语义，暂不采集）
RECRUIT_TYPE_MAP = {1: "campus", 3: "social"}
RECRUIT_TYPES = ["1", "3"]

# 面向计算机/AI 方向的搜索关键词
KEYWORDS = ["算法", "后端开发", "前端开发", "人工智能", "数据分析", "测试开发", "客户端开发"]

MAX_PAGES_PER_QUERY = 3
PAGE_SIZE = 20


class NowcoderSource(BaseSource):
    name = "nowcoder"

    def __init__(self):
        super().__init__()
        self._company_names: dict[int, str] = {}  # 只缓存成功结果，失败可重试

    def crawl(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[int] = set()
        for recruit_type in RECRUIT_TYPES:
            for query in KEYWORDS:
                items += self._crawl_query(query, recruit_type, seen_ids)
        logger.info("[nowcoder] 共采集 %d 条", len(items))
        return items

    def _crawl_query(self, query: str, recruit_type: str, seen_ids: set[int]) -> list[RawItem]:
        items: list[RawItem] = []
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            try:
                data = self._request(query, page, recruit_type)
            except Exception as e:
                logger.error("[nowcoder] query=%s type=%s page=%d 请求失败: %s",
                             query, recruit_type, page, e)
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
                try:
                    items.append(self._to_item(job))
                except Exception as e:
                    # 单条数据异常（如时间戳格式错误）只丢弃该条，不毁整轮
                    logger.warning("[nowcoder] 条目解析失败 id=%s: %s", job_id, e)
            if page >= data.get("totalPage", 1):
                break
        return items

    def _request(self, query: str, page: int, recruit_type: str) -> dict:
        form = {"careerJobId": "", "jobCity": "", "page": str(page), "query": query,
                "random": "false", "recommend": "false", "recruitType": recruit_type,
                "salaryType": "2", "pageSize": str(PAGE_SIZE), "requestFrom": "1",
                "order": "0", "pageSource": "5001"}
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "Referer": "https://www.nowcoder.com/jobs/school/jobs"}
        payload = self.post(SEARCH_URL, form=form, headers=headers)
        if payload.get("code") != 0:
            raise RuntimeError(f"API 返回异常: {payload.get('code')} {payload.get('msg')}")
        return payload["data"]

    def _company_name(self, company_id: int) -> str:
        """公司名在职位接口中为 null，从公司 SSR 页面标题解析，只缓存成功结果。"""
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
        if name:
            self._company_names[company_id] = name
        self._throttle()
        return name

    @staticmethod
    def _ts_to_date(ts) -> str:
        """毫秒时间戳 -> 北京时间日期（截止时间按用户所处时区认知）。"""
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(int(ts) / 1000, tz=_BJ_TZ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            return ""

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
        jd = self._extract_jd(job.get("ext"))
        if jd:
            req_parts.append(jd[:300])
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

    @staticmethod
    def _extract_jd(ext) -> str:
        if isinstance(ext, dict):
            return ext.get("infos") or ext.get("requirements") or ""
        if isinstance(ext, str) and ext.strip().startswith("{"):
            try:
                data = json.loads(ext)
                return data.get("infos") or data.get("requirements") or ""
            except json.JSONDecodeError:
                return ""
        return ""
