"""LLM 结构化抽取：原始招聘文本 -> 标准 JSON。失败重试一次，仍失败返回 None 并留待人工排查。"""
import json
import logging

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

SCHEMA_PROMPT = """你是招聘信息结构化助手。从下面的原始文本中抽取招聘信息，只输出一个 JSON 对象，不要输出其他内容。

字段定义：
- company_name: 企业全称（字符串，无法判断则空字符串）
- title: 岗位名称（字符串）
- recruit_type: "campus"（校招/应届/实习）或 "social"（社招）或 "unknown"
- requirements: 招聘要求摘要（字符串，200 字以内，无则空字符串）
- location: 工作地点（字符串，无则空字符串）
- apply_url: 投递/报名链接（完整 URL，原文中没有则空字符串）
- deadline: 报名截止日期（YYYY-MM-DD，无则空字符串）

原始文本：
<<<
{raw}
>>>"""

RETRY_PROMPT = """上次输出不是合法 JSON 或缺少必需字段：{error}
请重新抽取，只输出一个合法 JSON 对象，字段：company_name, title, recruit_type, requirements, location, apply_url, deadline。

原始文本：
<<<
{raw}
>>>"""


class JobExtractor:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> OpenAI:
        # 惰性创建：结构化源走不到 LLM，无 Key 时也不应报错
        if self._client is None:
            if not settings.llm_enabled:
                raise RuntimeError("未配置 LLM_API_KEY")
            self._client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        return self._client

    def extract(self, raw_text: str) -> dict | None:
        if not settings.llm_enabled:
            logger.warning("未配置 LLM_API_KEY，跳过结构化抽取")
            return None
        raw_text = raw_text[:6000]  # 控制成本
        result = self._ask(SCHEMA_PROMPT.format(raw=raw_text))
        if result is None:
            result = self._ask(RETRY_PROMPT.format(error=self._last_error, raw=raw_text))
        return result

    def _ask(self, prompt: str) -> dict | None:
        try:
            resp = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            if not isinstance(data.get("title"), str) or not data.get("company_name"):
                self._last_error = "缺少 company_name 或 title"
                return None
            return data
        except (json.JSONDecodeError, KeyError) as e:
            self._last_error = f"JSON 解析失败: {e}"
            logger.warning("LLM 输出解析失败: %s", e)
            return None
        except Exception as e:
            self._last_error = f"API 调用失败: {e}"
            logger.error("LLM API 调用失败: %s", e)
            return None
