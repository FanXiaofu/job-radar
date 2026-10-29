"""应届生求职网数据源测试：列表页解析、日期分组、GB18030 解码，不依赖网络。

运行：python tests/test_yingjiesheng.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.sources.yingjiesheng import YingjieshengSource  # noqa: E402

FIXTURE = """<html><body>
<table class="jobul">
  <tr class="jobth"><th>公司名称</th><th>讨论区</th><th>备注</th></tr>
  <tr class="clock"><td><strong>2026.10.30(周五)</strong> 倒计时：4天</td></tr>
  <tr class="bg1"><td><a href="/job-008-097-891.html">【北京上海成都辽宁重庆】大连银行2027校园招聘</a></td></tr>
  <tr class="bg0"><td><a href="/job-008-100-001.html">【全国】某公司2027校园招聘业务培训生|客户经理</a></td></tr>
  <tr class="clock"><td><strong>2026.11.01(周日)</strong> 倒计时：6天</td></tr>
  <tr class="bg1"><td><a href="/job-008-130-630.html">【四川】泸州银行2027校园招聘</a></td></tr>
</table>
</body></html>"""


def test_parse_page():
    items = YingjieshengSource()._parse_page(FIXTURE)
    assert len(items) == 3, len(items)

    first = items[0].parsed
    assert first["company_name"] == "大连银行"
    assert first["title"] == "2027校园招聘"
    assert first["location"] == "北京上海成都辽宁重庆"
    assert first["deadline"] == "2026-10-30"
    assert first["apply_url"] == "https://www.yingjiesheng.com/job-008-097-891.html"
    assert items[0].url == first["apply_url"]

    second = items[1].parsed
    assert second["company_name"] == "某公司"
    assert second["title"] == "2027校园招聘业务培训生|客户经理"
    assert second["deadline"] == "2026-10-30"

    third = items[2].parsed
    assert third["company_name"] == "泸州银行"
    assert third["deadline"] == "2026-11-01"
    print("test_parse_page 通过")


def test_crawl_decodes_gb18030():
    source = YingjieshengSource()

    class FakeResponse:
        content = FIXTURE.encode("gb18030")

    source.fetch = lambda url: FakeResponse()
    items = source.crawl()

    assert len(items) == 3
    assert items[0].parsed["company_name"] == "大连银行"
    print("test_crawl_decodes_gb18030 通过")


if __name__ == "__main__":
    test_parse_page()
    test_crawl_decodes_gb18030()
    print("全部通过")
