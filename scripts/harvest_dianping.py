"""大众点评 m 站人气排行页并行收割：城市×菜品查询 → 排行页 → 导入。

用法：python scripts/harvest_dianping.py [--dishes 8] [--delay 0.6]
"""
from __future__ import annotations

import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.batch import import_list_records  # noqa: E402
from hhrating.collectors import create_collector  # noqa: E402
from hhrating.cache import TextCache  # noqa: E402
from hhrating.dianping import dianping_urls, parse_dianping_dishes  # noqa: E402
from hhrating.storage import Database  # noqa: E402

CITIES = ["广州", "深圳", "佛山", "东莞", "珠海", "中山", "惠州", "江门", "肇庆"]
DISHES = ["火锅", "椰子鸡", "烤肉", "自助餐", "粤菜", "早茶", "肠粉", "烧鹅",
          "糖水", "甜品", "湘菜", "川菜", "酸菜鱼", "牛杂", "烧腊", "寿司",
          "西餐", "砂锅粥", "面馆", "饺子"]

_fetch_opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # DP m 站国内直连


CACHE = TextCache(Path(__file__).parent.parent / "data" / "cache" / "text-cache.sqlite3")


def fetch_dp_page(url: str) -> str | None:
    cached = CACHE.get(url)
    if cached is not None:
        return cached
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"}
        )
        with _fetch_opener(req) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            CACHE.put(url, html)
            return html
    except Exception:
        return None


def main() -> None:
    n_dishes = 8
    if "--dishes" in sys.argv:
        n_dishes = int(sys.argv[sys.argv.index("--dishes") + 1])
    delay = 0.6
    if "--delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--delay") + 1])

    collector = create_collector()
    db = Database("data/restaurants.json").load()

    queries = []
    for city in CITIES:
        for dish in DISHES[:n_dishes]:
            queries.append((city, dish, f"{city}{dish} 人气商户排行 大众点评"))

    # 1) 逐条搜索（带间隔，避免限流），收集 DP 排行页 URL
    dp_urls: dict[str, tuple[str, str]] = {}  # url -> (city, dish)
    for i, (city, dish, q) in enumerate(queries, 1):
        try:
            results = collector.search(q)
        except Exception as exc:
            print(f"[{i}/{len(queries)}] 搜索异常 {q}: {str(exc)[:40]}")
            results = []
        found = 0
        for r in results:
            for u in dianping_urls(r.get("url", "") + " " + r.get("snippet", "")):
                if u not in dp_urls:
                    dp_urls[u] = (city, dish)
                    found += 1
        print(f"[{i}/{len(queries)}] {q}: 排行页 +{found}")
        if delay:
            time.sleep(delay)

    print(f"共发现排行页 {len(dp_urls)} 个，并行抓取解析 …")

    # 2) 并行抓取排行页并解析
    entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_dp_page, u): (u, dp_urls[u]) for u in dp_urls}
        for fut in as_completed(futures):
            url, (city, dish) = futures[fut]
            html = fut.result()
            if not html:
                continue
            shops = parse_dianping_dishes(html)
            for shop in shops:
                entries.append(
                    {
                        "name": shop["name"],
                        "city": city,
                        "source": url,
                        "list_name": f"大众点评{city}{dish}人气商户排行",
                    }
                )
    print(f"解析出商户条目 {len(entries)}")

    # 3) 导入
    summary = import_list_records(entries, db)
    db.save()
    print(summary)
    print("数据库总数:", len(db))


if __name__ == "__main__":
    main()
