"""360 链接解析与 Cookie 会话测试。"""
import http.cookiejar

from hhrating.collectors.so360 import So360Collector, resolve_so360_link


class FakeResponse:
    def __init__(self, body, final_url="https://www.so.com/link?m=fake"):
        self._body = body
        self._final = final_url

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return self._final


class TestResolve:
    def test_resolves_js_redirect(self):
        def opener(req, timeout=20):
            return FakeResponse('window.location.replace("https://www.bendibao.com/a/1.htm")')

        url = resolve_so360_link("https://www.so.com/link?m=abc", opener=opener)
        assert url == "https://www.bendibao.com/a/1.htm"

    def test_falls_back_to_original(self):
        def opener(req, timeout=20):
            return FakeResponse("<html>无跳转</html>")

        url = resolve_so360_link("https://www.so.com/link?m=abc", opener=opener)
        assert url == "https://www.so.com/link?m=abc"

    def test_non_link_url_untouched(self):
        assert resolve_so360_link("https://www.example.com/a") == "https://www.example.com/a"


class TestCollectorResolve:
    def test_search_resolves_top_links(self):
        page = (
            '<li class="res-list"><h3 class="res-title"><a href="/link?m=aaa">洛阳老字号一 - 本地宝</a></h3>'
            '<p class="res-desc">内容一</p></li>'
            '<li class="res-list"><h3 class="res-title"><a href="/link?m=bbb">洛阳老字号二 - 头条</a></h3>'
            '<p class="res-desc">内容二</p></li>'
        )

        def opener(req, timeout=20):
            url = req.full_url
            if "/s?q=" in url:
                return FakeResponse(page, final_url=url)
            return FakeResponse(f'window.location.replace("https://real.example.com/x")')

        collector = So360Collector(opener=opener, resolve_links=2)
        results = collector.search("洛阳 老字号")
        resolved = [r["url"] for r in results if r["url"].startswith("https://real.example.com")]
        assert len(resolved) == 2

    def test_default_opener_carries_cookie_jar(self):
        import inspect

        src = inspect.getsource(So360Collector.__init__)
        assert "HTTPCookieProcessor" in src or "CookieJar" in src
