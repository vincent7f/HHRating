"""本地网页文本缓存测试（SQLite，仅存正文，默认 7 天有效）。"""
from hhrating.cache import CachedResponse, TextCache, cached_opener


class FakeResponse:
    def __init__(self, body):
        self._body = body
        self.calls = 0

    def read(self):
        self.calls += 1
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestTextCache:
    def test_put_get_roundtrip(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3")
        cache.put("https://a.example.com/x", "正文内容<xml>标签</xml>")
        assert cache.get("https://a.example.com/x") == "正文内容<xml>标签</xml>"

    def test_missing_url_returns_none(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3")
        assert cache.get("https://nope.example.com") is None

    def test_ttl_expiry(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3", ttl_days=7)
        cache.put("https://old.example.com", "旧文本")
        # 回写抓取时间为 8 天前
        old = __import__("time").time() - 8 * 86400
        cache._conn.execute("UPDATE pages SET fetched_at=? WHERE url=?", (old, "https://old.example.com"))
        cache._conn.commit()
        assert cache.get("https://old.example.com") is None  # 过期不返回

    def test_default_ttl_is_seven_days(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3")
        assert cache.ttl_seconds == 7 * 86400

    def test_creates_parent_dirs(self, tmp_path):
        cache = TextCache(tmp_path / "deep" / "dir" / "cache.sqlite3")
        cache.put("u", "t")
        assert cache.get("u") == "t"


class TestCachedOpener:
    def test_second_visit_uses_cache(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3")
        inner = FakeResponse("<html>页面正文</html>")
        calls = []

        def fake_opener(request, timeout=20):
            calls.append(request.full_url)
            return inner

        opener = cached_opener(cache, fake_opener)
        first = opener(__import__("urllib.request", fromlist=["Request"]).Request("https://x.example.com/p1"))
        assert first.read().decode("utf-8") == "<html>页面正文</html>"
        second = opener(__import__("urllib.request", fromlist=["Request"]).Request("https://x.example.com/p1"))
        assert second.read().decode("utf-8") == "<html>页面正文</html>"
        assert len(calls) == 1  # 第二次命中缓存，不再联网

    def test_supports_with_statement(self, tmp_path):
        cache = TextCache(tmp_path / "cache.sqlite3")
        opener = cached_opener(cache, lambda req, timeout=20: FakeResponse("hello"))
        resp = opener(__import__("urllib.request", fromlist=["Request"]).Request("https://y.example.com"))
        with resp as r:
            assert r.read().decode("utf-8") == "hello"
