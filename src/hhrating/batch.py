"""自动批量采集管线：给定店名清单，自动检索公开摘要并生成入库记录。

设计约定（诚实优先）：
- 仅提取正则可验证的信号（评分/创立年份/点评数），提取不到就留空（评分记 0）；
- 多个候选值取多数（mode），评分并列取中高位，年份并列取最早值；
- 每条记录 notes 标注"自动采集、未经人工核实"；
- 已存在（同名归一化匹配）的记录一律跳过，绝不覆盖人工数据。
"""
from __future__ import annotations

import hashlib
import re
import statistics
import time
from collections import Counter
from datetime import date

from .models import Restaurant
from .storage import Database

CITY_PREFIXES = {"广州": "gz", "深圳": "sz", "北京": "bj", "上海": "sh", "成都": "cd"}

CUISINE_KEYWORDS = (
    "潮汕菜", "客家菜", "粤菜", "顺德菜", "本帮菜", "湘菜", "川菜", "淮扬菜",
    "台州菜", "杭帮菜", "西北菜", "东北菜", "新疆菜", "云南菜", "贵州菜",
    "烤鸭", "烧腊", "烧鹅", "早茶", "茶点", "点心", "小笼包", "肠粉", "粥",
    "火锅", "串串", "麻辣烫", "烧烤", "小龙虾", "日料", "寿司", "刺身",
    "韩料", "泰餐", "越南菜", "西餐", "牛排", "自助餐", "素菜", "斋菜",
)


def make_record_id(city: str, name: str) -> str:
    """确定性生成记录 id：{城市前缀}-{店名归一化哈希前8位}。"""
    prefix = CITY_PREFIXES.get(city, "r")
    norm = normalize_name(name)
    digest = hashlib.md5(norm.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def normalize_name(name: str) -> str:
    """店名归一化：去空白与括号注记（分店信息），便于查重与奖项匹配。"""
    cleaned = re.sub(r"[（(][^（）()]*[)）]", "", name)
    return re.sub(r"\s+", "", cleaned)


def guess_cuisine(texts: list[str]) -> str:
    """从标题/摘要中猜测菜系；找不到记"待分类"。"""
    for text in texts:
        for keyword in CUISINE_KEYWORDS:
            if keyword in text:
                return keyword
    return "待分类"


def _mode(values: list, tie: str = "median_high"):
    """多数值；并列时评分取中高位、年份取最早（tie="min"）。"""
    if not values:
        return None
    counts = Counter(values)
    top = max(counts.values())
    tied = sorted(v for v, c in counts.items() if c == top)
    if len(tied) == 1:
        return tied[0]
    if tie == "min":
        return tied[0]
    return tied[len(tied) // 2]


def collect_restaurant(name: str, city: str, collector, second_query: bool = True) -> dict | None:
    """检索单店公开摘要并聚合为一条待入库记录；无任何结果返回 None。"""
    ratings: list[float] = []
    years: list[int] = []
    counts: list[int] = []
    sources: list[str] = []
    titles: list[str] = []

    def _consume(results):
        from .collectors.websearch import extract_founded_year, extract_rating, extract_review_count

        for r in results:
            if r["url"] and r["url"] not in sources:
                sources.append(r["url"])
            text = f'{r["title"]} {r["snippet"]}'
            titles.append(text)
            for extract, sink in (
                (extract_rating, ratings),
                (extract_founded_year, years),
                (extract_review_count, counts),
            ):
                value = extract(text)
                if value is not None and value not in sink:
                    sink.append(value)

    _consume(collector.search(f"{name} {city} 大众点评 评分 点评"))
    if second_query and not years:
        _consume(collector.search(f"{name} 创立 历史介绍"))

    if not sources:
        return None
    today = date.today().isoformat()
    metrics = {}
    rating = _mode(ratings)
    if rating is not None:
        metrics["online_rating"] = float(rating)
    year = _mode(years, tie="min")
    if year is not None:
        metrics["founded_year"] = int(year)  # 并列时取最早主张
    if counts:
        metrics["review_count"] = int(statistics.median(counts))
    return {
        "id": make_record_id(city, name),
        "name": name,
        "city": city,
        "cuisine": guess_cuisine(titles),
        "metrics": metrics,
        "sources": sources[:5],
        "data_date": today,
        "notes": f"自动采集（DuckDuckGo/必应公开摘要，快照 {today}），未经人工核实；"
        f"信号：评分候选 {ratings or '无'}，年份候选 {years or '无'}，点评数候选 {counts or '无'}",
    }


def batch_import(
    names: list[str],
    city: str,
    collector,
    db: Database,
    limit: int | None = None,
    second_query: bool = True,
    delay: float = 0.0,
    progress=None,
) -> dict:
    """批量采集并入库。同名（归一化）记录跳过；返回摘要统计。"""
    existing = {normalize_name(r.name) for r in db.restaurants}
    summary = {"imported": 0, "skipped_existing": 0, "failed": 0, "total": len(names)}
    for i, name in enumerate(names[:limit] if limit else names, 1):
        if normalize_name(name) in existing:
            summary["skipped_existing"] += 1
            if progress:
                progress(f"[{i}/{len(names)}] 跳过（已收录）：{name}")
            continue
        try:
            record = collect_restaurant(name, city, collector, second_query=second_query)
        except Exception as exc:
            record = None
            if progress:
                progress(f"[{i}/{len(names)}] 出错：{name}（{exc}）")
        if record is None:
            summary["failed"] += 1
            if progress:
                progress(f"[{i}/{len(names)}] 失败（无结果）：{name}")
        else:
            db.upsert(Restaurant.from_dict(record))
            existing.add(normalize_name(name))
            summary["imported"] += 1
            if progress:
                progress(
                    f"[{i}/{len(names)}] 已收录：{name} → {record['metrics'] or '无有效指标'}"
                )
        if delay:
            time.sleep(delay)
    return summary
