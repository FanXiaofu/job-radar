"""牛客数据源单元测试：详情页链接、企业名、广告卡片过滤，不依赖网络。

运行：python tests/test_nowcoder.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.sources.nowcoder import JOB_DETAIL_URL, NowcoderSource  # noqa: E402


def _job(**overrides):
    job = {
        "id": 462162,
        "companyId": 5540,
        "jobName": "测试工程师-成都",
        "jobCityList": ["成都"],
        "ext": '{"requirements": "任职要求", "infos": "岗位职责"}',
        "deliverEnd": 1814284800000,
        "recruitType": 1,
        "recommendInternCompany": {"companyName": "电科金仓"},
        "redirectExternalUrl": None,
    }
    job.update(overrides)
    return job


def test_to_item_builds_detail_url():
    item = NowcoderSource()._to_item(_job())

    assert item.parsed["company_name"] == "电科金仓"
    assert item.parsed["title"] == "测试工程师-成都"
    assert item.parsed["apply_url"] == JOB_DETAIL_URL.format(job_id=462162)
    assert item.url == item.parsed["apply_url"]
    print("test_to_item_builds_detail_url 通过")


def test_to_item_prefers_external_url():
    external = "https://careers.example.com/apply"
    item = NowcoderSource()._to_item(_job(redirectExternalUrl=external))

    assert item.parsed["apply_url"] == external
    assert item.url == JOB_DETAIL_URL.format(job_id=462162), "来源页仍应是职位详情页"
    print("test_to_item_prefers_external_url 通过")


def test_to_item_falls_back_to_company_page():
    source = NowcoderSource()
    calls = []
    source._company_name = lambda company_id: calls.append(company_id) or "回退公司"

    item = source._to_item(_job(recommendInternCompany=None))

    assert item.parsed["company_name"] == "回退公司"
    assert calls == [5540]
    print("test_to_item_falls_back_to_company_page 通过")


def test_crawl_query_skips_null_title():
    source = NowcoderSource()
    source._request = lambda query, page, recruit_type: {
        "datas": [
            {"data": {"id": 1, "jobName": ""}},
            {"data": _job(id=2)},
        ],
        "totalPage": 1,
    }

    items = source._crawl_query("算法", "1", set())

    assert len(items) == 1
    assert items[0].parsed["title"] == "测试工程师-成都"
    print("test_crawl_query_skips_null_title 通过")


if __name__ == "__main__":
    test_to_item_builds_detail_url()
    test_to_item_prefers_external_url()
    test_to_item_falls_back_to_company_page()
    test_crawl_query_skips_null_title()
    print("全部通过")
