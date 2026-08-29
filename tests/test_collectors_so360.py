"""360 搜索引擎测试（so.com，中文查询备选引擎，直链结果）。"""
from hhrating.collectors.so360 import So360Collector, parse_so360_html

SO360_FIXTURE = """
<html><body>
<ul>
<li class="res-list">
  <h3 class="res-title "><a href="https://www.dianping.com/shop/123" target="_blank">陶陶居酒家(第十甫路总店)点评-大众点评</a></h3>
  <p class="res-desc">陶陶居酒家(第十甫路总店) 评分4.2，共有12000条点评，人均105元。</p>
</li>
<li class="res-list">
  <h3 class="res-title"><a href="/link?m=xyz">跳转结果 评分4.5</a></h3>
  <div class="res-desc">始创于1880年的百年茶楼，1.5万+条评价。</div>
</li>
<li class="res-list">
  <h3   class="res-title"><a href="https://baike.example.com/tao">陶陶居_百度百科</a></h3>
  <p class="res-desc">陶陶居始创于1880年。</p>
</li>
</ul>
<h3 class="title">其他人还搜了</h3>
</body></html>
"""


class TestSo360Parse:
    def test_extracts_results(self):
        results = parse_so360_html(SO360_FIXTURE)
        assert len(results) == 3
        first = results[0]
        assert first["title"].startswith("陶陶居酒家(第十甫路总店)")
        assert first["url"] == "https://www.dianping.com/shop/123"
        assert "12000条点评" in first["snippet"]
        assert results[1]["url"] == "https://www.so.com/link?m=xyz"  # 相对链接补全
        assert results[2]["title"] == "陶陶居_百度百科"

    def test_skips_related_searches(self):
        # "其他人还搜了" 的 h3.title 不是 res-title，不产生结果
        results = parse_so360_html(SO360_FIXTURE)
        assert all("其他人还搜" not in r["title"] for r in results)

    def test_collector_search(self):
        class FakeResponse:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        collector = So360Collector(opener=lambda req: FakeResponse(SO360_FIXTURE))
        results = collector.search("陶陶居 广州 点评")
        assert len(results) == 3
        assert "12000条点评" in results[0]["snippet"]
