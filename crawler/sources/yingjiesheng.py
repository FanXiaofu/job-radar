"""应届生求职网数据源：解析 /deadline/ 的全职网申截止日期表。

页面真实编码是 GBK（响应头写成 UTF-8），所以按 GB18030 解码。
表格里 tr.clock 表示一个截止日期，后续带 /job-*.html 的行是公司校园招聘公告。
详情页有 JS 反爬，这里只解析列表页，投递链接直接指向公告页。
"""
import logging
import re
from urllib.parse import urljoin

from crawler.base import BaseSource, RawItem

logger = logging.getLogger(__name__)

BASE_URL = "https://www.yingjiesheng.com"
DEADLINE_URL = f"{BASE_URL}/deadline/"
JOB_HREF_RE = re.compile(r"^/job-\d+-\d+-\d+\.html$")
DATE_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
LOCATION_RE = re.compile(r"^【([^】]+)】\s*(.*)$")
CAMPUS_RE = re.compile(r"(20\d{2}校园招聘.*)$")


class YingjieshengSource(BaseSource):
    name = "yingjiesheng"

    def crawl(self) -> list[RawItem]:
        resp = self.fetch(DEADLINE_URL)
        html = resp.content.decode("gb18030", errors="replace")
        items = self._parse_page(html)
        logger.info("[yingjiesheng] 共采集 %d 条", len(items))
        return items

    def _parse_page(self, html: str) -> list[RawItem]:
        soup = self.soup(html)
        table = soup.find("table", class_="jobul")
        if table is None:
            logger.warning("[yingjiesheng] 未找到 jobul 表格")
            return []

        items: list[RawItem] = []
        deadline = ""
        seen: set[str] = set()
        for tr in table.find_all("tr"):
            classes = tr.get("class") or []
            if "clock" in classes:
                match = DATE_RE.search(tr.get_text(" ", strip=True))
                if match:
                    deadline = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                continue

            link = tr.find("a", href=JOB_HREF_RE)
            if not link:
                continue
            href = link.get("href", "")
            if href in seen:
                continue
            text = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
            parsed = self._parse_item(text, href, deadline)
            if not parsed:
                continue
            seen.add(href)
            raw_text = f"{text}；截止 {deadline}" if deadline else text
            items.append(RawItem(source=self.name, url=urljoin(BASE_URL, href),
                                 raw_text=raw_text, title=parsed["title"], parsed=parsed))
        return items

    @staticmethod
    def _parse_item(text: str, href: str, deadline: str) -> dict | None:
        text = text.strip()
        if not text:
            return None

        location = ""
        match = LOCATION_RE.match(text)
        if match:
            location = match.group(1).strip()
            body = match.group(2).strip()
        else:
            body = text

        campus = CAMPUS_RE.search(body)
        if campus:
            company = body[:campus.start()].strip()
            title = campus.group(1).strip()
        else:
            company = body
            title = "校园招聘"

        if not company:
            return None
        requirements = text + (f"；截止 {deadline}" if deadline else "")
        return {
            "company_name": company,
            "title": title,
            "recruit_type": "campus",
            "requirements": requirements,
            "location": location,
            "apply_url": urljoin(BASE_URL, href),
            "deadline": deadline,
        }
