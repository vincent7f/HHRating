"""必应 HTML 端点采集器（对代理环境更友好，作为 DuckDuckGo 的备选引擎）。"""
from __future__ import annotations

import base64
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote
from urllib.request import Request, urlopen

SEARCH_ENDPOINT = "https://www.bing.com/search/"
USER_AGENT = "Mozilla/5.0 (compatible; HHRating/0.1; +local research tool)"


def _normalize_bing_url(href: str) -> str:
    """还原必应跳转链接（/ck/a?...u=a1<base64>）为真实地址。"""
    if "/ck/a" in href and "u=" in href:
        qs = parse_qs(href.split("?", 1)[1])
        u = qs.get("u", [""])[0]
        if u.startswith("a1"):
            try:
                padded = u[2:] + "=" * (-len(u[2:]) % 4)
                return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
            except Exception:
                return href
    return unquote(href)


class _BingHTMLParser(HTMLParser):
    """提取 li.b_algo 下的 h2>a（标题+链接）与首个 p（摘要）。"""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_item = False
        self._pending: dict[str, str] | None = None
        self._field: str | None = None
        self._h2_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "li" and "b_algo" in cls:
            self._in_item = True
            self._pending = {"title": "", "url": "", "snippet": ""}
            return
        if not self._in_item or self._pending is None:
            return
        if tag == "h2":
            self._h2_depth += 1
        elif tag == "a" and self._h2_depth > 0 and not self._pending["url"]:
            self._pending["url"] = _normalize_bing_url(attrs.get("href", ""))
            self._field = "title"
        elif tag == "p" and self._field != "title":
            self._field = "snippet"

    def handle_data(self, data):
        if self._pending is not None and self._field:
            self._pending[self._field] += data

    def handle_endtag(self, tag):
        if tag == "h2" and self._h2_depth:
            self._h2_depth -= 1
        elif tag == "a" and self._field == "title":
            self._field = None
        elif tag == "p" and self._field == "snippet":
            self._field = None
        elif tag == "li" and self._in_item:
            if self._pending and self._pending["title"]:
                self.results.append(
                    {
                        "title": self._pending["title"].strip(),
                        "url": self._pending["url"],
                        "snippet": self._pending["snippet"].strip(),
                    }
                )
            self._pending = None
            self._in_item = False


def parse_bing_html(html: str) -> list[dict[str, str]]:
    parser = _BingHTMLParser()
    parser.feed(html)
    return parser.results


class BingCollector:
    def __init__(self, opener=None, proxy: str | None = None) -> None:
        if opener is not None:
            self._opener = opener
        else:
            self._opener = urlopen  # type: ignore[assignment]

    def search(self, query: str) -> list[dict[str, str]]:
        url = SEARCH_ENDPOINT + "?q=" + quote_plus(query) + "&setmkt=zh-CN"
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
        try:
            with self._opener(request) as response:
                html = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"必应检索失败：{exc}") from exc
        return parse_bing_html(html)
