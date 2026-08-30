"""网上数据采集器。

`DuckDuckGoCollector` 通过 DuckDuckGo HTML 端点检索公开网页摘要，
辅助人工整理评分、点评数、创立年份等指标（human-in-the-loop，不做自动定稿）。

网络层可注入以便测试；代理支持两种方式：
1. 环境变量 `HTTP_PROXY` / `HTTPS_PROXY`（urllib 默认识别）；
2. 构造参数 `proxy="http://127.0.0.1:8009"`（显式指定）。
"""
from __future__ import annotations

import re
from functools import partial
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin
from urllib.request import ProxyHandler, Request, build_opener, urlopen

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; HHRating/0.1; +local research tool)"


class CollectError(RuntimeError):
    """采集失败（网络、解析等）。"""


def _normalize_url(href: str) -> str:
    """DuckDuckGo 结果链接规范化（协议相对 / 跳转包装）。"""
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if "/l/?" in href:
        qs = parse_qs(href.split("?", 1)[1])
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


class _DDGHTMLParser(HTMLParser):
    """提取 result__a（标题+链接）与 result__snippet（摘要）。"""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._pending: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag != "a":
            return
        if "result__a" in cls:
            self._pending = {
                "title": "",
                "url": _normalize_url(attrs.get("href", "")),
                "snippet": "",
            }
            self._field = "title"
        elif "result__snippet" in cls and self._pending is not None:
            self._field = "snippet"

    def handle_data(self, data):
        if self._pending is not None and self._field:
            self._pending[self._field] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._field:
            if self._field == "snippet" and self._pending is not None:
                self.results.append(self._pending)
                self._pending = None
            self._field = None


def parse_ddg_html(html: str) -> list[dict[str, str]]:
    parser = _DDGHTMLParser()
    parser.feed(html)
    return [
        {
            "title": r["title"].strip(),
            "url": r["url"],
            "snippet": r["snippet"].strip(),
        }
        for r in parser.results
        if r["title"]
    ]


def extract_rating(text: str) -> float | None:
    """从文本中提取 0-5 分制评分；无命中或超出范围返回 None。"""
    patterns = (
        r"评分\s*([0-5](?:\.\d)?)",
        r"([0-5](?:\.\d)?)\s*分",
        r"rating\s*([0-5](?:\.\d)?)",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = float(m.group(1))
            if 0 <= value <= 5:
                return value
            return None  # 命中了明显越界的"分数"，视为噪声
    return None


def extract_founded_year(text: str, reference_year: int = 2026) -> int | None:
    """提取"创立年份"。近 30 年的年份多为翻新/开业新闻，予以排除。

    不含裸"建于"：该表述多指建筑物年份，对餐厅是常见误报。
    """
    m = re.search(r"(?:始创|创立|创建|创办|始建|创)于?\s*(\d{4})\s*年?", text)
    if not m:
        return None
    year = int(m.group(1))
    if year < 1000 or year > reference_year - 30:
        return None
    return year


def extract_review_count(text: str) -> int | None:
    """从文本中提取点评/评价条数（"12万+条评价"→120000）；收藏数不算。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*万\+?\s*条?\s*(?:用户)?(?:评价|点评|评论)", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d{3,7})\s*条\s*(?:用户)?(?:评价|点评|评论)", text)
    if m:
        return int(m.group(1))
    return None


def extract_address(text: str) -> str | None:
    """提取"市+区/县+路/街/巷"形态的详细地址；匹配不到返回 None。"""
    m = re.search(
        r"[\u4e00-\u9fa5]{1,8}市[\u4e00-\u9fa5]{1,10}[区县]"
        r"[\u4e00-\u9fa5A-Za-z0-9]{1,20}?(?:路|大街|街道|街|巷|村|大道)"
        r"[\u4e00-\u9fa5A-Za-z0-9]{0,12}\d{0,5}号?",
        text,
    )
    if not m:
        return None
    address = m.group(0).strip("，。；,; ")
    address = re.sub(r"^(?:位于|地址[:：]?|在|近)", "", address)
    return address or None


class DuckDuckGoCollector:
    """检索公开网页摘要，产出待人工确认的信号（评分/年份候选等）。"""

    def __init__(self, opener=None, proxy: str | None = None, timeout: float = 20) -> None:
        if opener is not None:
            self._opener = opener
        elif proxy:
            self._opener = partial(
                build_opener(ProxyHandler({"http": proxy, "https": proxy})).open, timeout=timeout
            )
        else:
            # 显式直连：避免被系统代理（注册表/env）劫持到不可用的本地端口
            self._opener = partial(build_opener(ProxyHandler({})).open, timeout=timeout)

    def search(self, query: str) -> list[dict[str, str]]:
        url = SEARCH_ENDPOINT + "?q=" + quote_plus(query)
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener(request) as response:
                html = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise CollectError(f"检索失败：{exc}") from exc
        return parse_ddg_html(html)

    def collect_signals(self, query: str) -> dict:
        """检索并聚合信号：结果列表 + 评分候选 + 创立年份候选。"""
        results = self.search(query)
        ratings: list[float] = []
        years: list[int] = []
        for r in results:
            text = f'{r["title"]} {r["snippet"]}'
            rating = extract_rating(text)
            if rating is not None and rating not in ratings:
                ratings.append(rating)
            year = extract_founded_year(text)
            if year is not None and year not in years:
                years.append(year)
        return {
            "results": results,
            "rating_candidates": ratings,
            "founded_year_candidates": years,
        }


__all__ = [
    "CollectError",
    "DuckDuckGoCollector",
    "extract_address",
    "extract_founded_year",
    "extract_rating",
    "extract_review_count",
    "parse_ddg_html",
    "urljoin",
]
