"""名录发现管线：搜索引擎找名录文章 → 并行抓取 → 提取店名 → 产出导入条目。

设计为纯代码执行（无需 LLM 参与）：
1. `search_list_articles(collector, city, queries)` → 候选文章 URL；
2. `fetch_article(url)` → 正文文本（直连优先，失败尝试代理）；
3. `extract_restaurant_names(text, city)` → 餐饮后缀白名单过滤后的店名；
4. `build_entries(...)` → 供 import_list_records 使用的条目。
"""
from __future__ import annotations

import re
import urllib.request
from functools import partial
from urllib.parse import quote_plus
from urllib.request import ProxyHandler, Request, build_opener, urlopen

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# 餐饮后缀白名单（用于从自由文本中识别店名；匹配时按长度降序优先）
_SUFFIX = sorted(
    (
        "餐厅", "菜馆", "饭店", "酒家", "食堂", "火锅", "鸡煲", "糖水铺", "糖水", "甜品店",
        "甜品", "茶餐厅", "大排档", "烧烤店", "牛肉店", "肠粉店", "烧腊", "煲仔饭", "渔港",
        "农庄", "山庄", "茶楼", "点心", "烧鹅", "乳鸽", "面馆", "粉店", "饼店", "粥铺",
        "小吃", "小馆", "食府", "饭庄", "士多", "串串", "炖品", "卤味", "私房菜",
        "椰子鸡", "牛肉火锅", "海鲜酒楼", "美食店", "快餐",
    ),
    key=len,
    reverse=True,
)
_LIST_WORDS = ("公司", "集团", "银行", "学校", "医院", "政府", "推荐", "必吃", "名单",
               "榜单", "攻略", "排行", "盘点", "合集", "一文", "大全", "排名", "指南",
               "地图", "测评", "合集")

_TAG_RE = re.compile(r"<[^>]+>")
_NAME_RE = re.compile(
    r"[\u4e00-\u9fa5A-Za-z0-9·]{1,12}?"
    + "(?:" + "|".join(_SUFFIX) + r")"
    + r"(?:（[^（）]{1,12}）|\([^()]{1,12}\))?"
)


def _clean(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = _TAG_RE.sub("\n", text)
    text = re.sub(r"&nbsp;?", " ", text)
    # 标点/括号内容统一断行；行内空白合并（"胜记渔港 酒家"→"胜记渔港酒家"）
    text = re.sub(r"[，。；：、！？!?…—\[\]【】\"“”'‘’|]", "\n", text)
    text = re.sub(r"[ \t\u3000]+", "", text)
    return text


def extract_restaurant_names(text: str, city: str) -> list[str]:
    """从文章文本提取店名：餐饮后缀白名单 + 去重 + 列表词剔除 + 长度限制。"""
    cleaned = _clean(text)
    names: list[str] = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _NAME_RE.search(line)
        if not m:
            continue
        name = m.group(0).strip()
        if len(name) < 3 or len(name) > 20:
            continue
        if any(w in name for w in _LIST_WORDS):
            continue
        if name not in names:
            names.append(name)
    return names


def looks_like_city_page(title_or_text: str, city: str) -> bool:
    return city in (title_or_text or "")


def fetch_article(url: str, proxy: str | None = None, timeout: float = 20) -> str | None:
    """抓取文章 HTML。proxy 为 None 时先直连（国内站），失败再用系统代理；反之亦然。"""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    if proxy is None:
        openers = [
            build_opener(ProxyHandler({})).open,                      # 直连
            build_opener(ProxyHandler({})).open,                      # 兜底重试
        ]
    else:
        openers = [
            build_opener(ProxyHandler({"http": proxy, "https": proxy})).open,
            build_opener(ProxyHandler({})).open,
        ]
    for opener in openers:
        try:
            with opener(request, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            continue
    return None


def search_list_articles(collector, city: str, queries: list[str]) -> list[dict]:
    """用代码搜索找名录文章 URL（去重、过滤非本城结果）。"""
    seen: set[str] = set()
    articles: list[dict] = []
    for q in queries:
        try:
            results = collector.search(q)
        except Exception:
            continue
        for r in results:
            url, title = r.get("url", ""), r.get("title", "")
            if not url or url in seen:
                continue
            if looks_like_city_page(title, city) or looks_like_city_page(r.get("snippet", ""), city):
                seen.add(url)
                articles.append({"url": url, "title": title, "query": q, "city": city})
    return articles


def build_entries(articles: list[dict], city: str, list_hint: str = "网络名录文章") -> list[dict]:
    """抓取文章并提取店名 → import_list_records 条目。"""
    entries: list[dict] = []
    for art in articles:
        text = fetch_article(art["url"])
        if not text:
            continue
        names = extract_restaurant_names(text, city)
        for name in names:
            entries.append(
                {
                    "name": name,
                    "city": city,
                    "source": art["url"],
                    "list_name": f"{list_hint}：{art['title'][:40]}",
                }
            )
    return entries
