"""高德"状元榜·美食"采集器：分区分榜的服务端渲染页面，含 JSON-LD 结构化数据。

URL 形如 https://www.amap.com/ranking/{city}/food/{district_code}
（如 guangzhou/440106 为广州天河区必吃美食 TOP10）。
榜单基于高德真实用户评价数据，是"热闹饭店"的权威名录来源。
"""
from __future__ import annotations

import json
import re
from functools import partial
from urllib.parse import quote_plus
from urllib.request import ProxyHandler, Request, build_opener, urlopen

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def ranking_url(city: str, district_code: str) -> str:
    return f"https://www.amap.com/ranking/{quote_plus(city)}/food/{quote_plus(district_code)}"


def parse_amap_jsonld(raw: str) -> list[dict]:
    """解析页面 JSON-LD ItemList → [{name, address, position}]。"""
    data = json.loads(raw)
    items = []
    for element in data.get("itemListElement", []):
        item = element.get("item", {})
        name = (item.get("name") or "").strip()
        if not name:
            continue
        address = (item.get("address") or "").strip() or None
        items.append({"name": name, "address": address, "position": element.get("position")})
    return items


def parse_amap_html(html: str) -> list[dict]:
    """从页面中提取 JSON-LD（兼容裸 JSON 与无 JSON-LD 时回退 poi-name 列表）。"""
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    if m:
        return parse_amap_jsonld(m.group(1))
    if html.lstrip().startswith("{"):
        return parse_amap_jsonld(html)
    names = re.findall(r'class="[^"]*poi-name[^"]*"[^>]*>([^<]+)<', html)
    return [{"name": n.strip(), "address": None, "position": i + 1} for i, n in enumerate(names) if n.strip()]


class AmapCollector:
    def __init__(self, opener=None, proxy: str | None = None, timeout: float = 20) -> None:
        if opener is not None:
            self._opener = opener
        elif proxy:
            self._opener = partial(
                build_opener(ProxyHandler({"http": proxy, "https": proxy})).open, timeout=timeout
            )
        else:
            self._opener = partial(urlopen, timeout=timeout)

    def fetch(self, city: str, district_code: str) -> list[dict]:
        url = ranking_url(city, district_code)
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener(request) as response:
                html = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"高德榜单抓取失败：{exc}") from exc
        items = parse_amap_html(html)
        for item in items:
            item["source"] = url
        return items
