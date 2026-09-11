"""全局配置：从 .env 读取，全部带默认值，Key 缺失时功能降级而不是崩溃。"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # LLM
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "https://api.deepseek.com"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "deepseek-chat"))

    # 搜索
    search_provider: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "none").lower())
    search_api_key: str = field(default_factory=lambda: _env("SEARCH_API_KEY"))

    # 运行
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / _env("DB_PATH", "data/job.db"))
    schedule_hour: int = field(default_factory=lambda: _env_int("SCHEDULE_HOUR", 9))
    schedule_minute: int = field(default_factory=lambda: _env_int("SCHEDULE_MINUTE", 0))
    web_host: str = field(default_factory=lambda: _env("WEB_HOST", "127.0.0.1"))
    web_port: int = field(default_factory=lambda: _env_int("WEB_PORT", 8000))

    # 爬虫行为
    request_timeout: float = 20.0
    request_delay: float = 1.5  # 同一源两次请求之间的间隔，避免给对方造成压力
    max_retries: int = 2

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def search_enabled(self) -> bool:
        return self.search_provider in ("bocha", "tavily") and bool(self.search_api_key)


settings = Settings()
