"""采集器测试：解析逻辑用固定 HTML 夹具，网络层可注入。"""
import io
from urllib.error import URLError

import pytest

from hhrating.collectors.websearch import (
    DuckDuckGoCollector,
    extract_founded_year,
    extract_rating,
    parse_ddg_html,
)

FIXTURE_HTML = """
<html><body>
<div class="result results_links">
  <a class="result__a" href="//example.com/r1">全聚德烤鸭店（前门店） - 大众点评</a>
  <a class="result__snippet">全聚德前门店 评分4.2，共有125000条点评，创立于1864年。</a>
</div>
<div class="result results_links">
  <a class="result__a" href="//example.com/r2">北京全聚德简介 - 百科</a>
  <a class="result__snippet">全聚德创建于1864年（清同治三年），中华老字号。</a>
</div>
<div class="result results_links">
  <a class="result__a" href="//example.com/r3">无关结果</a>
  <a class="result__snippet">这条与饭店无关。</a>
</div>
</body></html>
"""


class TestParsing:
    def test_parse_ddg_html_extracts_results(self):
        results = parse_ddg_html(FIXTURE_HTML)
        assert len(results) == 3
        assert results[0]["title"].startswith("全聚德烤鸭店")
        assert results[0]["url"].startswith("https://example.com/r1")
        assert "125000条点评" in results[0]["snippet"]

    def test_parse_empty_page(self):
        assert parse_ddg_html("<html><body></body></html>") == []

    def test_extract_rating(self):
        assert extract_rating("大众点评评分4.6，环境好") == 4.6
        assert extract_rating("口味：4.5分 环境：4.2分") == 4.5
        assert extract_rating(" rating 4.8 of 5 ") == 4.8
        assert extract_rating("没有分数") is None

    def test_extract_rating_rejects_out_of_range(self):
        assert extract_rating("评分9.9分") is None

    def test_extract_founded_year(self):
        assert extract_founded_year("创立于1864年") == 1864
        assert extract_founded_year("创建于1864年（清同治三年）") == 1864
        assert extract_founded_year("始建于1903") == 1903
        assert extract_founded_year("现代建筑2024年落成") is None  # 太新，不像创立年份

    def test_extract_founded_year_rejects_recent(self):
        # 近 30 年的年份大概率不是"创立年份"
        assert extract_founded_year("2005年开业翻新") is None


class FakeResponse:
    def __init__(self, html: str):
        self._html = html

    def read(self) -> bytes:
        return self._html.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestCollector:
    def test_fetch_parses_through_injected_opener(self):
        collector = DuckDuckGoCollector(opener=lambda req: FakeResponse(FIXTURE_HTML))
        results = collector.search("全聚德 前门店 大众点评")
        assert len(results) == 3

    def test_query_is_urlencoded(self):
        seen = {}

        def fake_opener(req):
            seen["url"] = req.full_url
            return FakeResponse(FIXTURE_HTML)

        DuckDuckGoCollector(opener=fake_opener).search("全聚德 & 点评")
        assert "q=%E5%85%A8%E8%81%9A%E5%BE%B7" in seen["url"]
        assert "+%26+" in seen["url"]

    def test_network_error_raises_collect_error(self):
        collector = DuckDuckGoCollector(opener=lambda req: (_ for _ in ()).throw(URLError("boom")))
        with pytest.raises(Exception, match="boom"):
            collector.search("任何查询")

    def test_extract_signals_from_results(self):
        collector = DuckDuckGoCollector(opener=lambda req: FakeResponse(FIXTURE_HTML))
        signals = collector.collect_signals("全聚德")
        assert signals["rating_candidates"] == [4.2]
        assert 1864 in signals["founded_year_candidates"]
        assert signals["results"][0]["title"].startswith("全聚德烤鸭店")
