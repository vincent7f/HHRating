"""搜狗引擎：中文多词查询的主引擎（必应/DDG 在部分代理环境下会丢弃中文词项）。

结构（2026-08 实测）：结果容器 div.vrwrap；标题 h3.vr-title > a（href 多为
/link?url=... 跳转链，正文高亮使用 <em> 与 HTML 注释）；摘要 class 含
str_info / str-text-info。/link 跳转通过响应中的 window.location.replace
还原真实地址（仅解析前 N 条以控制请求量）。
"""
from __future__ import annotations

import re
from functools import partial
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin
from urllib.request import ProxyHandler, Request, build_opener, urlopen

SEARCH_ENDPOINT = "https://www.sogou.com/web?"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_BASE = "https://www.sogou.com"

_JS_REDIRECT_RE = re.compile(r'window\.location\.replace\("([^"]+)"\)')


def resolve_sogou_link(url: str, opener=None, timeout: float = 15) -> str:
    """把搜狗 /link 跳转还原为真实地址；失败时原样返回。"""
    if "/link?url=" not in url:
        return url
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        if opener is not None:
            with opener(request) as resp:
                body = resp.read().decode("utf-8", "replace")
        else:
            with urlopen(request, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
        m = _JS_REDIRECT_RE.search(body)
        return m.group(1) if m else url
    except Exception:
        return url


class _SogouHTMLParser(HTMLParser):
    """按文档顺序配对标题与摘要：新标题开始时落盘上一条；snippet 在 </a> 之后出现。"""

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
        href = attrs.get("href", "")
        if tag == "h3" and "vr-title" in cls:
            self._flush()
            self._pending = {"title": "", "url": "", "snippet": ""}
            self._in_title_link = True
        elif tag == "a" and self._in_title_link and self._pending is not None and not self._pending["url"]:
            self._pending["url"] = urljoin(_BASE, href)
        elif tag in ("div", "p", "span") and self._pending is not None and (
            "str_info" in cls or "str-text-info" in cls
        ):
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
        elif tag in ("div", "p", "span") and self._in_snippet:
            self._in_snippet = False

    def close(self) -> None:
        super().close()
        self._flush()


def parse_sogou_html(html: str) -> list[dict[str, str]]:
    parser = _SogouHTMLParser()
    parser.feed(html)
    parser.close()
    cleaned = []
    for r in parser.results:
        title = re.sub(r"\s+", " ", r["title"]).strip()
        cleaned.append({"title": title, "url": r["url"], "snippet": r["snippet"].strip()})
    return cleaned


class SogouCollector:
    def __init__(self, opener=None, proxy: str | None = None, timeout: float = 20,
                 resolve_links: int = 3) -> None:
        if opener is not None:
            self._opener = opener
        elif proxy:
            self._opener = partial(
                build_opener(ProxyHandler({"http": proxy, "https": proxy})).open, timeout=timeout
            )
        else:
            self._opener = partial(urlopen, timeout=timeout)
        self._resolve_links = resolve_links

    def search(self, query: str) -> list[dict[str, str]]:
        url = SEARCH_ENDPOINT + "query=" + quote_plus(query)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
        try:
            with self._opener(request) as response:
                html = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"搜狗检索失败：{exc}") from exc
        results = parse_sogou_html(html)
        resolved = 0
        for r in results:
            if "/link?url=" in r["url"] and resolved < self._resolve_links:
                r["url"] = resolve_sogou_link(r["url"], opener=self._opener)
                resolved += 1
        return [r for r in results if r["title"]]
