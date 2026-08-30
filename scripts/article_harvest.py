"""全国名录文章收割：360 解析 → 抓文 → 提取 → 导入（分批防丢失更新）。

用法：python scripts/article_harvest.py [--batch-cities 8]
城市清单取自数据库现有城市。
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.batch import import_list_records  # noqa: E402
from hhrating.collectors.so360 import So360Collector  # noqa: E402
from hhrating.discovery import build_entries  # noqa: E402
from hhrating.storage import Database  # noqa: E402

DB_PATH = "data/restaurants.json"


def main() -> None:
    batch_cities = 8
    if "--batch-cities" in sys.argv:
        batch_cities = int(sys.argv[sys.argv.index("--batch-cities") + 1])

    db = Database(DB_PATH).load()
    cities = sorted({r.city for r in db.restaurants})
    print(f"城市 {len(cities)} 个，按批处理（每批 {batch_cities} 城）", flush=True)

    total_imported = 0
    for i in range(0, len(cities), batch_cities):
        chunk = cities[i:i + batch_cities]
        collector = So360Collector(resolve_links=4)
        articles: list[dict] = []

        # 搜索（每城 2 查询，串行以免触发限流；解析与抓文走线程池）
        for city in chunk:
            for q in (f"{city} 美食街 店铺 名单", f"{city} 网红餐厅 打卡 推荐"):
                try:
                    results = collector.search(q)
                except Exception:
                    results = []
                for r in results[:4]:
                    if r["url"].startswith("http") and "so.com" not in r["url"] and "ai.so.com" not in r["url"]:
                        articles.append({"url": r["url"], "title": r["title"], "query": q, "city": city})
                time.sleep(1.2)

        # 并行抓文提取
        entries: list[dict] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(build_entries, [a], a["city"], "名录文章"): a for a in articles}
            for fut in as_completed(futures):
                try:
                    entries.extend(fut.result())
                except Exception:
                    pass

        # 每批重新加载数据库（避免长跑快照丢失更新），单次落盘
        fresh = Database(DB_PATH).load()
        s = import_list_records(entries, fresh)
        fresh.save()
        total_imported += s["imported"]
        print(f"[批 {i // batch_cities + 1}] 城市 {chunk} → 文章 {len(articles)} 篇，条目 {len(entries)}，导入 {s['imported']}", flush=True)

    print(f"合计导入 {total_imported} 家")


if __name__ == "__main__":
    main()
