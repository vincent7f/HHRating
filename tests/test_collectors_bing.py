"""采集器测试补充：必应引擎与多引擎回退。"""
import pytest

from hhrating.collectors import create_collector
from hhrating.collectors.bing import BingCollector, parse_bing_html

BING_FIXTURE = """
<html><body>
<ol id="b_results">
<li class="b_algo"><h2><a href="https://example.com/b1">便宜坊烤鸭 - 百科</a></h2>
<div class="b_caption"><p class="b_lineclamp">便宜坊创立于1416年，大众点评评分4.4。</p></div></li>
<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9iMg==&ntb=1">便宜坊官网</a></h2>
<p>焖炉烤鸭技艺 2008 年列入国家级非遗。</p></li>
</ol>
</body></html>
"""


class FakeResponse:
    def __init__(self, html):
        self._html = html

    def read(self):
        return self._html.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestBingParse:
    def test_extracts_results(self):
        results = parse_bing_html(BING_FIXTURE)
        assert len(results) == 2
        assert results[0]["title"] == "便宜坊烤鸭 - 百科"
        assert results[0]["url"] == "https://example.com/b1"
        assert "1416年" in results[0]["snippet"]

    def test_decodes_bing_redirect_url(self):
        results = parse_bing_html(BING_FIXTURE)
        assert results[1]["url"] == "https://example.com/b2"

    def test_empty_results(self):
        assert parse_bing_html("<html><body><ol id='b_results'></ol></body></html>") == []


class TestBingCollector:
    def test_fetch_through_injected_opener(self):
        collector = BingCollector(opener=lambda req: FakeResponse(BING_FIXTURE))
        results = collector.search("便宜坊")
        assert results[0]["title"] == "便宜坊烤鸭 - 百科"


class TestFallback:
    def test_first_non_empty_engine_wins(self):
        class Stub:
            def __init__(self, name, out):
                self.name, self._out = name, out

            def search(self, q):
                self.q = q
                return self._out

        empty = Stub("ddg", [])
        good = Stub("bing", [{"title": "t", "url": "u", "snippet": "s"}])
        collector = create_collector(engines=[empty, good])
        assert collector.search("便宜坊")[0]["title"] == "t"
        assert empty.q == good.q == "便宜坊"

    def test_engine_error_falls_through(self):
        class Broken:
            def search(self, q):
                raise RuntimeError("blocked")

        class Ok:
            def search(self, q):
                return [{"title": "t", "url": "u", "snippet": "s"}]

        collector = create_collector(engines=[Broken(), Ok()])
        assert collector.search("x") == [{"title": "t", "url": "u", "snippet": "s"}]

    def test_default_creates_four_engines(self):
        collector = create_collector()
        assert len(collector.engines) == 4
        assert collector.engines[0].__class__.__name__ == "So360Collector"
        assert collector.engines[1].__class__.__name__ == "SogouCollector"
        assert collector.engines[2].__class__.__name__ == "DuckDuckGoCollector"
        assert collector.engines[3].__class__.__name__ == "BingCollector"
