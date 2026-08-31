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

from .models import Metrics, Restaurant
from .storage import Database

CITY_PREFIXES = {
    "广州": "gz", "深圳": "sz", "北京": "bj", "上海": "sh", "成都": "cd",
    "佛山": "fs", "东莞": "dg", "珠海": "zh", "中山": "zs", "惠州": "hz",
    "江门": "jm", "肇庆": "zq", "顺德": "sd",
}

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
    """店名归一化：去空白与括号注记（分店信息），便于奖项匹配。"""
    cleaned = re.sub(r"[（(][^（）()]*[)）]", "", name)
    return re.sub(r"\s+", "", cleaned)


def name_key(name: str) -> str:
    """查重键：分店级全名（全角括号折算为半角，仅去空白）。"""
    return re.sub(r"\s+", "", name).replace("（", "(").replace("）", ")")


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


def collect_restaurant(name: str, city: str, collector, second_query: bool = True,
                       pause: float = 0.0) -> dict | None:
    """检索单店公开摘要并聚合为一条待入库记录；无任何结果返回 None。"""
    from .collectors.websearch import (
        extract_address,
        extract_founded_year,
        extract_rating,
        extract_review_count,
    )

    ratings: list[float] = []
    years: list[int] = []
    counts: list[int] = []
    addresses: list[str] = []
    sources: list[str] = []
    titles: list[str] = []

    def _consume(results):
        for r in results:
            if r["url"] and r["url"] not in sources:
                sources.append(r["url"])
            text = f'{r["title"]} {r["snippet"]}'
            titles.append(text)
            for extract, sink in (
                (extract_rating, ratings),
                (extract_founded_year, years),
                (extract_review_count, counts),
                (extract_address, addresses),
            ):
                value = extract(text)
                if value is not None and value not in sink:
                    sink.append(value)

    _consume(collector.search(f"{name} {city} 大众点评 评分 点评"))
    if second_query and not years:
        if pause:
            time.sleep(pause)  # 搜索引擎对连续查询限流，查询间留间隔
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
    record = {
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
    if addresses:
        record["address"] = max(addresses, key=len)  # 最长者信息最全
    return record


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
    """批量采集并入库。同名（分店级全名）记录跳过；返回摘要统计。"""
    existing = {name_key(r.name) for r in db.restaurants}
    summary = {"imported": 0, "skipped_existing": 0, "failed": 0, "total": len(names)}
    for i, name in enumerate(names[:limit] if limit else names, 1):
        if name_key(name) in existing:
            summary["skipped_existing"] += 1
            if progress:
                progress(f"[{i}/{len(names)}] 跳过（已收录）：{name}")
            continue
        try:
            record = collect_restaurant(name, city, collector,
                                        second_query=second_query, pause=delay)
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
            existing.add(name_key(name))
            summary["imported"] += 1
            if progress:
                progress(
                    f"[{i}/{len(names)}] 已收录：{name} → {record['metrics'] or '无有效指标'}"
                )
        if delay:
            time.sleep(delay)
    return summary


def import_list_records(entries: list[dict], db: Database) -> dict:
    """从权威名录（榜单页/文章）批量建记录：不联网搜索单店，指标留空待补采。

    entry 字段：name（必填）、city（必填）、address/cuisine/district/branch（可选）、
    source（名录 URL）、list_name（名录名称）。
    """
    summary = {"imported": 0, "skipped_existing": 0, "failed": 0, "total": len(entries)}
    existing = {name_key(r.name) for r in db.restaurants}
    today = date.today().isoformat()
    pending: list[Restaurant] = []
    for entry in entries:
        name = (entry.get("name") or "").strip()
        city = (entry.get("city") or "").strip()
        if not name or not city:
            summary["failed"] += 1
            continue
        if name_key(name) in existing:
            summary["skipped_existing"] += 1
            continue
        list_name = entry.get("list_name") or "网络名录"
        cuisine = entry.get("cuisine")
        notes = f"来自名录「{list_name}」自动录入（快照 {today}），指标待补采"
        if entry.get("district"):
            notes += f"；区域：{entry['district']}"
        record = Restaurant(
            id=make_record_id(city, name),
            name=name,
            city=city,
            cuisine=cuisine or "待分类",
            metrics=Metrics(),
            sources=[entry["source"]] if entry.get("source") else [],
            data_date=today,
            address=entry.get("address"),
            branch=entry.get("branch"),
            notes=notes,
        )
        pending.append(record)
        existing.add(name_key(name))
        summary["imported"] += 1
    if pending:
        db.bulk_upsert(pending)
    return summary


def fill_missing(db: Database, city: str, collector, delay: float = 2.5, progress=None) -> dict:
    """对在库记录做定向补采：只更新缺失的 评分/点评数/创立年份/地址，绝不覆盖已有值。"""
    from .collectors.websearch import (
        extract_address,
        extract_founded_year,
        extract_rating,
        extract_review_count,
    )

    summary = {"updated": 0, "skipped": 0, "failed": 0}
    targets = [r for r in db.restaurants if r.city == city]
    for i, r in enumerate(targets, 1):
        need_rating = r.metrics.online_rating is None
        need_count = r.metrics.review_count is None
        need_year = r.metrics.founded_year is None
        need_address = r.address is None
        if not (need_rating or need_count or need_year or need_address):
            summary["skipped"] += 1
            continue
        updated = []
        results = collector.search(f"{r.name} 大众点评 评分")
        for res in results:
            text = f'{res["title"]} {res["snippet"]}'
            if need_rating:
                v = extract_rating(text)
                if v is not None and v >= 1.0:  # 低于 1 分的"评分"是页面噪声
                    r.metrics.online_rating = v
                    need_rating = False
                    updated.append(f"评分{v}")
            if need_count:
                v = extract_review_count(text)
                if v is not None:
                    r.metrics.review_count = v
                    need_count = False
                    updated.append(f"点评{v}")
            if need_address:
                v = extract_address(text)
                if v is not None:
                    r.address = v
                    need_address = False
                    updated.append("地址")
        if need_year:
            if delay:
                time.sleep(delay)
            for res in collector.search(f"{r.name} 创立 哪一年"):
                v = extract_founded_year(f'{res["title"]} {res["snippet"]}')
                if v is not None:
                    r.metrics.founded_year = v
                    need_year = False
                    updated.append(f"{v}年创立")
                    break
        if updated:
            for res in results[:1]:
                if res["url"] and res["url"] not in r.sources and len(r.sources) < 6:
                    r.sources.append(res["url"])
            r.notes = f"{r.notes or ''}；{date.today().isoformat()} 补采：{'、'.join(updated)}"
            db.upsert(r)
            summary["updated"] += 1
        else:
            summary["failed"] += 1
        if progress:
            progress(f"[{i}/{len(targets)}] {r.name}: {'、'.join(updated) or '无补充'}")
        if delay:
            time.sleep(delay)
    return summary


# 菜系关键词 → 菜系（匹配时按关键词长度降序，先长后短）
_CUISINE_KW = sorted(
    (
        ("韩国料理", "韩国料理"), ("韩式", "韩国料理"), ("韩料", "韩国料理"),
        ("泰国菜", "泰国菜"), ("泰式", "泰国菜"),
        ("火锅", "火锅"), ("椰子鸡", "椰子鸡"), ("鸡煲", "鸡煲"), ("打边炉", "火锅"),
        ("麻辣烫", "麻辣烫"), ("串串", "串串"),
        ("烧烤", "烧烤"), ("烤肉", "烤肉"),
        ("寿司", "日本料理"), ("刺身", "日本料理"), ("日本料理", "日本料理"), ("日料", "日本料理"),
        ("烧鸟", "日本料理"), ("越南", "越南菜"),
        ("西餐", "西餐"), ("意式", "西餐"), ("牛排", "西餐"), ("披萨", "西餐"), ("汉堡", "西式快餐"),
        ("咖啡", "咖啡厅"), ("茶餐厅", "茶餐厅"), ("冰室", "茶餐厅"),
        ("糖水", "甜品"), ("甜品", "甜品"), ("双皮奶", "甜品"), ("炖品", "炖品"),
        ("肠粉", "肠粉"), ("汤粉", "米粉"), ("米粉", "米粉"), ("螺蛳粉", "米粉"), ("米线", "米线"),
        ("面馆", "面食"), ("拉面", "面食"), ("面家", "面食"), ("云吞", "粤式小食"),
        ("粥", "粥品"), ("烧腊", "烧腊"), ("烧鹅", "烧鹅"), ("乳鸽", "粤菜"),
        ("素食", "素食"), ("斋", "素食"), ("农庄", "农家菜"), ("山庄", "农家菜"),
        ("海鲜", "海鲜"), ("自助", "自助餐"),
        ("湘菜", "湘菜"), ("湖南", "湘菜"), ("川菜", "川菜"), ("四川", "川菜"),
        ("潮汕", "潮汕菜"), ("潮州菜", "潮州菜"), ("客家", "客家菜"), ("顺德", "顺德菜"),
        ("粤菜", "粤菜"), ("早茶", "粤式早茶"), ("点心", "点心"),
        ("西北菜", "西北菜"), ("西北", "西北菜"), ("兰州", "西北菜"), ("西贝", "西北菜"), ("莜面", "西北菜"),
        ("新疆", "新疆菜"), ("东北", "东北菜"), ("贵州", "贵州菜"), ("云南", "云南菜"),
        ("过桥米线", "云南菜"), ("烤鸭", "北京菜"), ("清真", "清真菜"), ("回民", "清真菜"),
        ("私房菜", "私房菜"), ("饺子", "饺子"),
    ),
    key=lambda kv: len(kv[0]),
    reverse=True,
)


def classify_cuisine_name(*parts: str | None) -> str | None:
    """从店名/备注推断菜系（最长关键词优先）；无线索返回 None，不强判。"""
    haystack = "".join(p for p in parts if p)
    for kw, cuisine in _CUISINE_KW:
        if kw in haystack:
            return cuisine
    return None


def classify_all_cuisines(db: Database) -> Counter:
    """为 cuisine 为空/'待分类' 的记录按店名+备注推断菜系，返回 Counter。"""
    counts: Counter = Counter()
    updated: list[Restaurant] = []
    for r in db.restaurants:
        if r.cuisine in (None, "", "待分类"):
            cuisine = classify_cuisine_name(r.name, r.notes)
            if cuisine:
                r.cuisine = cuisine
                updated.append(r)
                counts[cuisine] += 1
    if updated:
        db.bulk_upsert(updated)
    return counts
