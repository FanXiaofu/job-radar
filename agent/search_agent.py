"""LLM 搜索 Agent：按关键词模板调用搜索 API，抓取落地页后交给抽取器处理。

作为定向爬虫的补充渠道，负责发现定向爬虫覆盖不到的招聘公告页面。
"""
import logging

import httpx

from config import settings
from crawler.base import USER_AGENT, RawItem

logger = logging.getLogger(__name__)

# 关键词模板：{role} 会被岗位方向替换
QUERY_TEMPLATES = [
    "{role} 校园招聘 2026届 公告",
    "秋招 {role} 招聘公告 投递",
    "央企 国企 {role} 校园招聘公告",
]

ROLES = ["算法工程师", "软件开发工程师", "AI应用工程师", "数据分析", "测试开发工程师"]


class SearchAgent:
    def __init__(self):
        self.provider = settings.search_provider
        self.api_key = settings.search_api_key

    def run(self, max_queries: int = 10) -> list[RawItem]:
        """执行一轮搜索，返回候选页面的 RawItem 列表（正文已抓取）。"""
        if not settings.search_enabled:
            logger.info("未配置搜索 API（SEARCH_PROVIDER/SEARCH_API_KEY），跳过搜索 Agent")
            return []
        items: list[RawItem] = []
        # 轮转取样：模板与岗位方向均匀组合，避免截断导致某组模板永不执行
        groups = [[tpl.format(role=r) for r in ROLES] for tpl in QUERY_TEMPLATES]
        queries: list[str] = []
        for i in range(max_queries):
            queries.append(groups[i % len(groups)][(i // len(groups)) % len(groups)])
        for q in queries:
            try:
                hits = self._search(q)
            except Exception as e:
                logger.error("搜索失败 [%s]: %s", q, e)
                continue
            for url, snippet in hits:
                body = self._fetch_page(url)
                if body:
                    items.append(RawItem(source="search", url=url,
                                         raw_text=f"{snippet}\n\n{body}", title=snippet[:80]))
        logger.info("搜索 Agent 完成：%d 个查询，候选页面 %d 个", len(queries), len(items))
        return items

    def _search(self, query: str) -> list[tuple[str, str]]:
        """调用配置的搜索服务商，返回 [(url, 标题或摘要)]。"""
        if self.provider == "bocha":
            return self._search_bocha(query)
        if self.provider == "tavily":
            return self._search_tavily(query)
        return []

    def _search_bocha(self, query: str) -> list[tuple[str, str]]:
        with httpx.Client(timeout=15) as c:
            resp = c.post("https://api.bochaai.com/v1/web-search",
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          json={"query": query, "count": 5, "summary": True})
            resp.raise_for_status()
            pages = resp.json().get("data", {}).get("webPages", {}).get("value", [])
            return [(p.get("url", ""), p.get("name", "")) for p in pages if p.get("url")]

    def _search_tavily(self, query: str) -> list[tuple[str, str]]:
        with httpx.Client(timeout=15) as c:
            resp = c.post("https://api.tavily.com/search",
                          json={"api_key": self.api_key, "query": query,
                                "max_results": 5, "include_domains": None})
            resp.raise_for_status()
            return [(r.get("url", ""), r.get("title", ""))
                    for r in resp.json().get("results", []) if r.get("url")]

    def _fetch_page(self, url: str) -> str | None:
        """抓取搜索命中的落地页正文（粗提取，精细结构化交给 LLM）。"""
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT},
                             timeout=settings.request_timeout, follow_redirects=True)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype:
                return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
            return text[:8000] if len(text) > 200 else None  # 过短页面视为无效
        except httpx.HTTPError as e:
            logger.debug("落地页抓取失败 %s: %s", url, e)
            return None
