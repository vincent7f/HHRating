"""搜狗引擎测试（中文查询主引擎；夹具来自真实返回结构）。"""
from hhrating.collectors.sogou import SogouCollector, parse_sogou_html, resolve_sogou_link

SOGOU_FIXTURE = """
<html><body>
<div class="vrwrap">
  <h3 class="vr-title"><a target="_blank" href="/link?url=abc123">百年老店<em>广州</em>陶陶居 - 大众点评</a></h3>
  <div class="str_info">陶陶居第十甫路总店 评分4.2，共1.5万+条点评。</div>
</div>
<div class="vrwrap">
  <h3 class="vr-title"><a href="https://direct.example.com/page">直链结果</a></h3>
  <div class="str-text-info">始创于1880年，康有为题字。</div>
</div>
<div class="vrwrap">
  <h3 class="vr-title"><a href="/link?url=def456">无摘要结果</a></h3>
</div>
</body></html>
"""


class TestSogouParse:
    def test_extracts_results(self):
        results = parse_sogou_html(SOGOU_FIXTURE)
        assert len(results) == 3
        first = results[0]
        assert first["title"] == "百年老店广州陶陶居 - 大众点评"  # em 标签已合并
        assert first["url"] == "https://www.sogou.com/link?url=abc123"
        assert "1.5万+条点评" in first["snippet"]
        assert results[1]["url"] == "https://direct.example.com/page"  # 直链保留
        assert results[2]["snippet"] == ""


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestLinkResolution:
    def test_resolves_js_redirect(self):
        calls = []

        def opener(req):
            calls.append(req.full_url)
            return FakeResponse('<script>window.location.replace("https://real.example.com/a")</script>')

        url = resolve_sogou_link("https://www.sogou.com/link?url=abc123", opener=opener, timeout=5)
        assert url == "https://real.example.com/a"

    def test_falls_back_to_original_on_failure(self):
        def opener(req):
            raise OSError("blocked")

        url = resolve_sogou_link("https://www.sogou.com/link?url=x", opener=opener, timeout=5)
        assert url == "https://www.sogou.com/link?url=x"

    def test_collector_resolves_limited_links(self):
        def opener(req):
            if "/link?url=" in req.full_url:
                return FakeResponse('window.location.replace("https://real.example.com/x")')
            return FakeResponse(SOGOU_FIXTURE)

        collector = SogouCollector(opener=opener, resolve_links=2)
        results = collector.search("陶陶居")
        resolved = [r["url"] for r in results if r["url"].startswith("https://real.example.com")]
        assert len(resolved) == 2  # 只解析前 2 条 /link
        assert results[1]["url"] == "https://direct.example.com/page"
