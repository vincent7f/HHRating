"""并行名录发现运行器：代码搜索 + 并行抓文 + 店名提取 + 导入。

用法：python scripts/discover_runner.py [--proxy http://127.0.0.1:8009]
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.batch import import_list_records  # noqa: E402
from hhrating.collectors import create_collector  # noqa: E402
from hhrating.discovery import build_entries, search_list_articles  # noqa: E402
from hhrating.storage import Database  # noqa: E402

CITIES = ["广州", "深圳", "佛山", "东莞", "珠海", "中山", "惠州", "江门", "肇庆"]

QUERIES = {
    "广州": ["广州 各区 人气餐厅 推荐名单 汇总", "广州 本地宝 必吃餐厅 名单"],
    "深圳": ["深圳 各区 必吃餐厅 名单 汇总", "深圳 本地宝 人气餐厅 推荐"],
    "佛山": ["佛山 必吃餐厅 名单 汇总", "佛山 禅城 南海 人气餐厅 推荐"],
    "东莞": ["东莞 必吃餐厅 名单 汇总", "东莞 各镇 美食 老字号 推荐"],
    "珠海": ["珠海 必吃餐厅 名单 汇总", "珠海 人气餐厅 茶楼 推荐"],
    "中山": ["中山 必吃餐厅 名单 石岐乳鸽", "中山 美食 老字号 推荐"],
    "惠州": ["惠州 必吃餐厅 名单 汇总", "惠州 美食 人气餐厅 推荐"],
    "江门": ["江门 必吃餐厅 名单 古井烧鹅", "江门 美食 老字号 推荐"],
    "肇庆": ["肇庆 必吃餐厅 名单 汇总", "肇庆 美食 人气餐厅 推荐"],
}


def main() -> None:
    proxy = None
    if "--proxy" in sys.argv:
        proxy = sys.argv[sys.argv.index("--proxy") + 1]
    collector = create_collector(proxy=proxy)
    db = Database("data/restaurants.json").load()

    # 1) 并行搜索名录文章
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(search_list_articles, collector, c, qs): c for c, qs in QUERIES.items()}
        for fut in as_completed(futures):
            city = futures[fut]
            try:
                found = fut.result()
                articles.extend(found)
                print(f"[{city}] 文章候选 {len(found)} 篇")
            except Exception as exc:
                print(f"[{city}] 搜索失败: {exc}")
    print(f"文章候选合计 {len(articles)} 篇，并行抓取提取 …")

    # 2) 并行抓文 + 提取店名
    entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(build_entries, [a], a["city"], "名录文章"): a for a in articles}
        for fut in as_completed(futures):
            try:
                entries.extend(fut.result())
            except Exception as exc:
                print(f"[抓取失败] {exc}")
    print(f"文章提取店名条目合计 {len(entries)}")

    # 3) 导入
    summary = import_list_records(entries, db)
    db.save()
    print(summary)
    print("数据库总数:", len(db))


if __name__ == "__main__":
    main()
