"""360 搜索引擎（so.com）：中文查询的备选引擎，结果多为真实直链。

结构（2026-08 实测）：结果位于 h3.res-title > a（class 属性格式多变，
如 `class="res-title "` 或 `<h3   class="res-title">`），摘要为
p/div.res-desc；部分链接为 /link?m=... 相对跳转。
"""
from __future__ import annotations

from functools import partial
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin
from urllib.request import ProxyHandler, Request, build_opener, urlopen

SEARCH_ENDPOINT = "https://www.so.com/s?q="
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_BASE = "https://www.so.com"


class _So360HTMLParser(HTMLParser):
    """顺序配对：h3.res-title 的首个 <a> 开新条目，其后 res-desc 文本为摘要。"""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_title_link = False
        self._in_snippet = False
        self._pending: dict[str, str] | None = None

    def _flush(self) -> None:
        if self._pending and self._pending["title"].strip():
            self.results.append(self._pending)
        self._pending = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "h3" and "res-title" in cls:
            self._flush()
            self._pending = {"title": "", "url": "", "snippet": ""}
            self._in_title_link = True
        elif tag == "a" and self._in_title_link and self._pending is not None and not self._pending["url"]:
            self._pending["url"] = urljoin(_BASE, attrs.get("href", ""))
        elif tag in ("p", "div") and self._pending is not None and "res-desc" in cls:
            self._in_snippet = True

    def handle_data(self, data):
        if self._pending is None:
            return
        if self._in_title_link:
            self._pending["title"] += data
        elif self._in_snippet:
            self._pending["snippet"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title_link:
            self._in_title_link = False
        elif tag in ("p", "div") and self._in_snippet:
            self._in_snippet = False

    def close(self) -> None:
        super().close()
        self._flush()


def parse_so360_html(html: str) -> list[dict[str, str]]:
    parser = _So360HTMLParser()
    parser.feed(html)
    parser.close()
    cleaned = []
    for r in parser.results:
        title = r["title"].strip()
        if title and "其他人还搜" not in title:
            cleaned.append({"title": title, "url": r["url"], "snippet": r["snippet"].strip()})
    return cleaned


class So360Collector:
    def __init__(self, opener=None, proxy: str | None = None, timeout: float = 20) -> None:
        if opener is not None:
            self._opener = opener
        elif proxy:
            self._opener = partial(
                build_opener(ProxyHandler({"http": proxy, "https": proxy})).open, timeout=timeout
            )
        else:
            self._opener = partial(build_opener(ProxyHandler({})).open, timeout=timeout)

    def search(self, query: str) -> list[dict[str, str]]:
        url = SEARCH_ENDPOINT + quote_plus(query)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
        try:
            with self._opener(request) as response:
                html = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"360 检索失败：{exc}") from exc
        return parse_so360_html(html)
