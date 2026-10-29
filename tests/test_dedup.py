"""去重与分类模块单元测试（不依赖 LLM 与网络）：python tests/test_dedup.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.dedup import is_duplicate, normalize_location, normalize_url, title_similarity  # noqa: E402
from config import settings  # noqa: E402


def test_normalize_url():
    assert normalize_url("https://www.Example.com/job/1?utm=xx#top") == "www.example.com/job/1"
    assert normalize_url("http://example.com/job/1/") == "example.com/job/1"
    assert normalize_url("") == ""
    print("test_normalize_url 通过")


def test_title_similarity():
    assert title_similarity("算法工程师", "算法工程师") == 1.0
    assert title_similarity("算法工程师", "算法工程师（北京）") > 0.6
    assert title_similarity("算法工程师", "销售总监") < 0.3
    print("test_title_similarity 通过")


def test_normalize_location():
    assert normalize_location("北京、上海") == normalize_location("上海，北京")
    assert normalize_location("北京/上海") == normalize_location("上海、北京")
    assert normalize_location("") == ""
    print("test_normalize_location 通过")


def _job(company, title, url, location=""):
    return {"company_name": company, "title": title,
            "apply_url": url, "location": location}


def test_is_duplicate():
    existing = [
        _job("中国建筑集团", "2026届校招-算法工程师", "https://campus.cscec.com/apply/2026?from=1"),
        _job("微软", "Software Engineer", "https://careers.microsoft.com/job/99"),
    ]
    # 同企业 + 同 URL（带 query 干扰）-> 重复
    assert is_duplicate(_job("中国建筑集团", "算法工程师", "https://campus.cscec.com/apply/2026"), existing)
    # 同企业 + 高相似标题、无 URL -> 重复
    assert is_duplicate(_job("中国建筑集团", "2026届校招-算法工程师", ""), existing)
    # 不同企业同名岗位 -> 不重复
    assert not is_duplicate(_job("微软", "算法工程师", "https://x.com/1"), existing)
    # 同企业不同岗位 -> 不重复
    assert not is_duplicate(_job("中国建筑集团", "土建工程师", "https://campus.cscec.com/apply/777"), existing)

    beijing = _job("某公司", "算法工程师", "https://x.com/bj", "北京")
    shanghai = _job("某公司", "算法工程师", "https://x.com/sh", "上海")
    # 跨城市同标题 -> 不重复
    assert not is_duplicate(shanghai, [beijing])
    # 同城市同标题 -> 重复
    assert is_duplicate(_job("某公司", "算法工程师", "https://x.com/bj2", "北京"), [beijing])
    # 任一侧地点为空 -> 允许模糊匹配
    assert is_duplicate(_job("某公司", "算法工程师", "", ""), [beijing])
    # 多地点顺序不同 -> 重复
    multi = _job("某公司", "算法工程师", "https://x.com/m1", "北京、上海")
    assert is_duplicate(_job("某公司", "算法工程师", "https://x.com/m2", "上海，北京"), [multi])
    # URL 相同但地点不同 -> 不重复
    assert not is_duplicate(
        _job("某公司", "算法工程师", "https://x.com/same", "上海"),
        [_job("某公司", "算法工程师", "https://x.com/same", "北京")],
    )
    print("test_is_duplicate 通过")


def test_classifier_lists():
    """名录匹配：子公司简称应判为央国企，知名外企应判为外企；未知企业应为未分类。"""
    from agent.classifier import CompanyClassifier
    old_key = settings.llm_api_key
    settings.llm_api_key = ""
    try:
        c = CompanyClassifier()
        cases = {
            "中国建筑集团有限公司": "central",
            "中建三局": "central",
            "微软（中国）": "foreign",
            "特斯拉上海": "foreign",
            "国家电网": "central",
            "华为技术有限公司": "private",
            "字节跳动": "private",
            "某不知名科技有限公司": "unknown",  # 未命中名录/LLM -> 未分类（source=default）
        }
        for name, want in cases.items():
            cat, src, conf = c.classify(name)
            assert cat == want, f"{name} -> {cat}, 期望 {want}"
            if name == "某不知名科技有限公司":
                assert (src, conf) == ("default", 0.3)
            if name == "华为技术有限公司":
                assert (src, conf) == ("list", 1.0)
    finally:
        settings.llm_api_key = old_key
    print("test_classifier_lists 通过")


if __name__ == "__main__":
    test_normalize_url()
    test_title_similarity()
    test_normalize_location()
    test_is_duplicate()
    test_classifier_lists()
    print("全部通过")
