"""去重与分类模块单元测试（不依赖 LLM 与网络）：python tests/test_dedup.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.dedup import is_duplicate, normalize_url, title_similarity  # noqa: E402


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


def _job(company, title, url):
    return {"company_name": company, "title": title, "apply_url": url}


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
    print("test_is_duplicate 通过")


def test_classifier_lists():
    """名录匹配：子公司简称应判为央国企，知名外企应判为外企；未知企业默认民企。"""
    from agent.classifier import CompanyClassifier
    c = CompanyClassifier()
    cases = {
        "中国建筑集团有限公司": "central",
        "中建三局": "central",
        "微软（中国）": "foreign",
        "特斯拉上海": "foreign",
        "国家电网": "central",
        "字节跳动": "private",  # 未命中名录 -> 兜底民企（source=default）
    }
    for name, want in cases.items():
        cat, src, _ = c.classify(name)
        assert cat == want, f"{name} -> {cat}, 期望 {want}"
        if name == "字节跳动":
            assert src == "default"
    print("test_classifier_lists 通过")


if __name__ == "__main__":
    test_normalize_url()
    test_title_similarity()
    test_is_duplicate()
    test_classifier_lists()
    print("全部通过")
