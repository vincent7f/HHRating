"""摘要式并行收割：从搜索引擎结果的标题+摘要中提取店名（无需打开文章）。

- 4 个引擎各占一个工作线程，查询轮转分配（并行但不轰同一引擎）；
- 引擎被限流（连续空结果）时进入冷却；
- 结果写入 data/seed/snippet-harvest.json 并增量导入数据库。

用法：python scripts/snippet_harvest.py [--limit 180]
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.batch import import_list_records  # noqa: E402
from hhrating.collectors.bing import BingCollector  # noqa: E402
from hhrating.collectors.so360 import So360Collector  # noqa: E402
from hhrating.collectors.sogou import SogouCollector  # noqa: E402
from hhrating.cache import TextCache  # noqa: E402
from hhrating.collectors.websearch import DuckDuckGoCollector  # noqa: E402
from hhrating.discovery import extract_restaurant_names  # noqa: E402
from hhrating.storage import Database  # noqa: E402

PRD_CITIES = ["广州", "深圳", "佛山", "东莞", "珠海", "中山", "惠州", "江门", "肇庆"]
_NATIONAL = "北京 上海 广州 深圳 成都 杭州 武汉 重庆 南京 天津 西安 苏州 郑州 长沙 沈阳 青岛 合肥 宁波 无锡 厦门 福州 济南 昆明 哈尔滨 长春 大连 石家庄 南昌 南宁 贵阳 太原 太原 石家庄 徐州 烟台 温州 金华 嘉兴 绍兴 台州 常州 南通 扬州 徐州 保定 唐山 廊坊 沧州 大同 洛阳 惠州 中山 江门 芜湖 蚌埠 泉州 漳州 莆田 贵港 北海 柳州 桂林 海口 三亚 兰州 乌鲁木齐 呼和浩特 银川 西宁".split()
CITIES = sorted(set(PRD_CITIES + _NATIONAL))
DISHES = ["烧鹅", "早茶", "肠粉", "糖水", "火锅", "椰子鸡", "烤鱼", "寿司", "牛杂",
          "砂锅粥", "湘菜", "川菜", "日本菜", "自助餐", "烧腊", "饺子", "米线",
          "茶餐厅", "海鲜", "点心", "猪肚鸡", "牛腩", "云吞面", "煲仔饭", "卤鹅",
          "生腌", "粿条", "烧肉", "烤串", "酸菜鱼", "小龙虾", "烤鸭", "螺蛳粉",
          "麻辣烫", "潮汕菜", "客家菜", "顺德菜", "湛江鸡", "猪脚饭", "牛展"]

_CACHE = TextCache(Path(__file__).parent.parent / "data" / "cache" / "text-cache.sqlite3")
ENGINES = [
    ("so360", So360Collector(cache=_CACHE)),
    ("sogou", SogouCollector(resolve_links=0, cache=_CACHE)),
    ("bing", BingCollector(cache=_CACHE)),
    ("ddg", DuckDuckGoCollector(cache=_CACHE)),
]


def build_queries() -> list[tuple[str, str]]:
    templates = ["哪家好吃 推荐", "人气 排行 榜", "本地人 常去 哪家", "必吃店 在哪里"]
    queries = []
    for i, dish in enumerate(DISHES):
        for j, city in enumerate(CITIES):
            queries.append((city, f"{city}{dish} {templates[(i + j) % len(templates)]}"))
    return queries


def harvest_worker(engine_name: str, engine, queries: list[tuple[str, str]],
                   out: list[dict], lock: threading.Lock) -> None:
    cooldown_until = 0.0
    empty_streak = 0
    for city, q in queries:
        if time.time() < cooldown_until:
            time.sleep(1.0)
        try:
            results = engine.search(q)
        except Exception:
            results = []
        if not results:
            empty_streak += 1
            if empty_streak >= 3:
                cooldown_until = time.time() + 45  # 疑似限流，冷却 45 秒
                empty_streak = 0
            time.sleep(2.0)
            continue
        empty_streak = 0
        text = " ".join(f"{r.get('title', '')} {r.get('snippet', '')}" for r in results)
        with lock:
            for name in extract_restaurant_names(text, city):
                out.append(
                    {
                        "name": name,
                        "city": city,
                        "source": results[0].get("url", ""),
                        "list_name": f"搜索摘要（{engine_name}）",
                    }
                )
        time.sleep(2.0)


def main() -> None:
    limit = 180
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    queries = build_queries()[:limit]
    # 轮转分配给 4 个引擎线程
    buckets: list[list[tuple[str, str]]] = [[] for _ in ENGINES]
    for i, q in enumerate(queries):
        buckets[i % len(ENGINES)].append(q)

    harvested: list[dict] = []
    lock = threading.Lock()
    print(f"查询 {len(queries)} 条，{len(ENGINES)} 引擎并行 …", flush=True)
    with ThreadPoolExecutor(max_workers=len(ENGINES)) as pool:
        futures = [
            pool.submit(harvest_worker, name, engine, bucket, harvested, lock)
            for (name, engine), bucket in zip(ENGINES, buckets)
        ]
        for fut in as_completed(futures):
            fut.result()

    out_path = Path(__file__).parent.parent / "data" / "seed" / "snippet-harvest.json"
    out_path.write_text(
        json.dumps({"schema_version": 1, "source": "搜索结果标题/摘要", "entries": harvested},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"收割条目 {len(harvested)} → {out_path.name}")

    db = Database("data/restaurants.json").load()
    summary = import_list_records(harvested, db)
    db.save()
    print(summary)
    print("数据库总数:", len(db))


if __name__ == "__main__":
    main()
