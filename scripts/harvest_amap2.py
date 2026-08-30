"""高德状元榜并行收割器 v2：探测广东全部城市 → 线程池并行抓取分区榜单。

用法：python scripts/harvest_amap2.py [--all-guangdong]
默认仅珠三角 9 市；--all-guangdong 时扩展到全省地级市。
输出：data/seed/amap-harvest2.json（与 v1 文件分离，保证来源可追溯）
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.amap import USER_AGENT, parse_amap_html, ranking_url  # noqa: E402
from hhrating.cache import TextCache  # noqa: E402

PRD = ["guangzhou", "shenzhen", "foshan", "dongguan", "zhuhai", "zhongshan", "huizhou", "jiangmen", "zhaoqing"]
OTHER_GD = ["shantou", "chaozhou", "jieyang", "shanwei", "meizhou", "heyuan", "qingyuan", "shaoguan", "yunfu", "yangjiang", "maoming", "zhanjiang"]

CITY_NAMES = {
    "guangzhou": "广州", "shenzhen": "深圳", "foshan": "佛山", "dongguan": "东莞",
    "zhuhai": "珠海", "zhongshan": "中山", "huizhou": "惠州", "jiangmen": "江门",
    "zhaoqing": "肇庆", "shantou": "汕头", "chaozhou": "潮州", "jieyang": "揭阳",
    "shanwei": "汕尾", "meizhou": "梅州", "heyuan": "河源", "qingyuan": "清远",
    "shaoguan": "韶关", "yunfu": "云浮", "yangjiang": "阳江", "maoming": "茂名",
    "zhanjiang": "湛江",
}

opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # 直连，绕过系统代理


def get(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener(req) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def discover_districts(slug: str) -> list[str]:
    """城市页 → 该城市可用的分区代码列表。"""
    html = get(f"https://www.amap.com/ranking/{slug}/food")
    if not html:
        return []
    return sorted(set(re.findall(rf"/ranking/{slug}/food/(\d+)", html)))


CACHE = TextCache(Path(__file__).parent.parent / "data" / "cache" / "text-cache.sqlite3")


def harvest_district(slug: str, code: str) -> list[dict]:
    city = CITY_NAMES[slug]
    url = ranking_url(slug, code)
    html = CACHE.get(url)
    if html is not None:
        html = html
    else:
        html = get(url) or ""
        if html:
            CACHE.put(url, html)
    if not html:
        return []
    items = parse_amap_html(html)
    return [
        {
            "name": it["name"],
            "city": city,
            "address": it.get("address"),
            "source": url,
            "list_name": "2025高德状元榜·美食（必吃美食）",
        }
        for it in items
        if it.get("name")
    ]


def main() -> None:
    all_gd = "--all-guangdong" in sys.argv
    slugs = PRD + (OTHER_GD if all_gd else [])
    print(f"探测 {len(slugs)} 个城市页 …")
    city_districts: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(discover_districts, s): s for s in slugs}
        for fut in as_completed(futures):
            slug = futures[fut]
            codes = fut.result()
            if codes:
                city_districts[slug] = codes
    total_pages = sum(len(v) for v in city_districts.values())
    print(f"{len(city_districts)} 个城市有榜单，共 {total_pages} 个分区页，并行抓取 …")

    entries: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {}
        for slug, codes in city_districts.items():
            for code in codes:
                futures[pool.submit(harvest_district, slug, code)] = (slug, code)
        for fut in as_completed(futures):
            slug, code = futures[fut]
            try:
                items = fut.result()
                entries.extend(items)
            except Exception as exc:
                print(f"[失败] {slug}/{code}: {exc}")
            done += 1
            if done % 10 == 0:
                print(f"  进度 {done}/{total_pages}，已收割 {len(entries)} 家")

    out = Path(__file__).parent.parent / "data" / "seed" / "amap-harvest2.json"
    out.write_text(
        json.dumps(
            {"schema_version": 1, "source": "amap.com 状元榜·美食（v2 全城并行收割）", "entries": entries},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    per_city: dict[str, int] = {}
    for e in entries:
        per_city[e["city"]] = per_city.get(e["city"], 0) + 1
    print("完成：", per_city, f"→ 共 {len(entries)} 家 → {out.name}")


if __name__ == "__main__":
    main()
