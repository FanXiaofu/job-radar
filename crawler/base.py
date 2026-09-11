"""爬虫基础设施：统一 HTTP 客户端、限速、重试，所有数据源 adapter 继承 BaseSource。"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


@dataclass
class RawItem:
    """采集层输出：结构化接口可直接填 parsed，非结构化文本交给 AI 层抽取。"""
    source: str
    url: str
    raw_text: str
    title: str = ""
    extras: dict = field(default_factory=dict)
    parsed: dict | None = None  # 已结构化的岗位数据，Pipeline 跳过 LLM 抽取


class BaseSource(ABC):
    name: str = "base"

    def __init__(self):
        self._last_request_at: float = 0.0

    def fetch(self, url: str, *, headers: dict | None = None) -> httpx.Response:
        """带限速与重试的 GET。重试耗尽后抛出最后一次异常，由调用方记录。"""
        merged = {"User-Agent": USER_AGENT, **(headers or {})}
        for attempt in range(1, settings.max_retries + 2):
            self._throttle()
            try:
                resp = httpx.get(url, headers=merged, timeout=settings.request_timeout,
                                 follow_redirects=True)
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as e:
                logger.warning("[%s] GET %s 失败（第 %d 次）: %s", self.name, url, attempt, e)
                if attempt > settings.max_retries:
                    raise
                time.sleep(2 * attempt)

    def post(self, url: str, *, json_body: dict | None = None,
             form: dict | None = None, headers: dict | None = None) -> dict:
        """带限速与重试的 POST，返回 JSON。API 型数据源统一走这里。"""
        merged = {"User-Agent": USER_AGENT, **(headers or {})}
        for attempt in range(1, settings.max_retries + 2):
            self._throttle()
            try:
                resp = httpx.post(url, json=json_body, data=form, headers=merged,
                                  timeout=settings.request_timeout)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("[%s] POST %s 失败（第 %d 次）: %s", self.name, url, attempt, e)
                if attempt > settings.max_retries:
                    raise
                time.sleep(2 * attempt)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < settings.request_delay:
            time.sleep(settings.request_delay - elapsed)
        self._last_request_at = time.monotonic()

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @abstractmethod
    def crawl(self) -> list[RawItem]:
        """抓取一轮，返回原始条目列表。单个条目失败应记录日志并跳过，不让整轮失败。"""
