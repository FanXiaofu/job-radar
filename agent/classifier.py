"""企业类型分类：内置名录精确匹配优先，未命中走 LLM，均带来源与置信度。

category 取值：central=央国企 / private=民企 / foreign=外企
"""
import logging
from pathlib import Path

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

# 名录文件：每行一个企业名，# 开头为注释
LIST_DIR = Path(__file__).parent / "lists"


def _load_list(filename: str) -> list[str]:
    path = LIST_DIR / filename
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


class CompanyClassifier:
    def __init__(self):
        self._central = _load_list("central_soes.txt")
        self._foreign = _load_list("foreign_companies.txt")
        self._llm = None

    def classify(self, company: str, default: str = "private") -> tuple[str, str, float]:
        """返回 (category, source, confidence)。source: list / llm / default

        default：名录与 LLM 均未命中时的兜底类型。可按数据源传入领域先验
        （如国聘平台以央国企为主传 "central"），通用场景保持 "private"。
        """
        company_l = company.lower()
        for entry in self._central:
            if entry in company or company in entry:
                return "central", "list", 1.0
        for entry in self._foreign:
            entry_l = entry.lower()
            if entry_l in company_l or company_l in entry_l:
                return "foreign", "list", 1.0
        result = self._classify_by_llm(company)
        if result:
            return result, "llm", 0.7
        return default, "default", 0.3

    def _classify_by_llm(self, company: str) -> str | None:
        if not settings.llm_enabled:
            return None
        if self._llm is None:
            self._llm = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        prompt = (
            "判断企业类型，只回答一个词：central（央企/国企/事业单位）、"
            "foreign（外企/合资）、private（民营企业）。\n"
            f"企业名：{company}"
        )
        try:
            resp = self._llm.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10,
            )
            answer = resp.choices[0].message.content.strip().lower()
            if answer in ("central", "foreign", "private"):
                return answer
            logger.warning("LLM 分类返回异常值: %s", answer)
            return None
        except Exception as e:
            logger.error("LLM 分类失败: %s", e)
            return None
