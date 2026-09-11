"""双层去重：URL 归一化精确匹配 + 标题相似度模糊匹配。"""
from difflib import SequenceMatcher


def normalize_url(url: str) -> str:
    """去掉协议、query、尾斜杠，统一为可比较形态。"""
    u = (url or "").strip().lower()
    u = u.split("://", 1)[-1]
    u = u.split("?")[0].split("#")[0]
    return u.rstrip("/")


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


def is_duplicate(new_job: dict, existing: list[dict],
                 title_threshold: float = 0.92) -> dict | None:
    """判断 new_job 是否与 existing（同企业已有岗位）重复。

    匹配规则：同企业名下，apply_url 归一化相同，或标题相似度超阈值。
    命中返回已有岗位 dict，否则 None。
    """
    new_url = normalize_url(new_job.get("apply_url", ""))
    new_title = new_job.get("title", "")
    new_company = (new_job.get("company_name") or "").strip()
    for old in existing:
        if (old.get("company_name") or "").strip() != new_company:
            continue
        if new_url and normalize_url(old.get("apply_url", "")) == new_url:
            return old
        if title_similarity(new_title, old.get("title", "")) >= title_threshold:
            return old
    return None
