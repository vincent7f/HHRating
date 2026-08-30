"""高德状元榜全国收割：探测城市 → 并行抓分区页 → 增量写盘。

用法：python scripts/harvest_amap_national.py [--out data/seed/amap-national.json]
城市 slug 为常见拼音名，探测失败的自动跳过；全部请求走本地缓存（7 天 TTL）。
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.amap import USER_AGENT, parse_amap_html, ranking_url  # noqa: E402
from hhrating.cache import TextCache  # noqa: E402

CITY_NAMES = {
    "beijing": "北京", "shanghai": "上海", "tianjin": "天津", "chongqing": "重庆",
    "guangzhou": "广州", "shenzhen": "深圳", "foshan": "佛山", "dongguan": "东莞",
    "zhuhai": "珠海", "zhongshan": "中山", "huizhou": "惠州", "jiangmen": "江门",
    "zhaoqing": "肇庆", "shantou": "汕头", "chaozhou": "潮州", "jieyang": "揭阳",
    "shanwei": "汕尾", "meizhou": "梅州", "heyuan": "河源", "qingyuan": "清远",
    "shaoguan": "韶关", "yunfu": "云浮", "yangjiang": "阳江", "maoming": "茂名",
    "zhanjiang": "湛江", "chengdu": "成都", "hangzhou": "杭州", "nanjing": "南京",
    "wuhan": "武汉", "xian": "西安", "suzhou": "苏州", "ningbo": "宁波",
    "wuxi": "无锡", "changzhou": "常州", "nantong": "南通", "xuzhou": "徐州",
    "yangzhou": "扬州", "jiaxing": "嘉兴", "shaoxing": "绍兴", "taizhou": "台州",
    "hefei": "合肥", "wuhu": "芜湖", "xiamen": "厦门", "fuzhou": "福州",
    "quanzhou": "泉州", "zhangzhou": "漳州", "jinan": "济南", "qingdao": "青岛",
    "yantai": "烟台", "weifang": "潍坊", "linyi": "临沂", "zhengzhou": "郑州",
    "luoyang": "洛阳", "kaifeng": "开封", "changsha": "长沙", "zhuzhou": "株洲",
    "xiangtan": "湘潭", "nanning": "南宁", "liuzhou": "柳州", "guilin": "桂林",
    "haikou": "海口", "sanya": "三亚", "kunming": "昆明", "dali": "大理",
    "lijiang": "丽江", "guiyang": "贵阳", "zunyi": "遵义", "shenyang": "沈阳",
    "dalian": "大连", "anshan": "鞍山", "jilin": "吉林", "changchun": "长春",
    "harbin": "哈尔滨", "qiqihar": "齐齐哈尔", "shijiazhuang": "石家庄",
    "tangshan": "唐山", "baoding": "保定", "handan": "邯郸", "taiyuan": "太原",
    "datong": "大同", "hohhot": "呼和浩特", "huhehaote": "呼和浩特", "baotou": "包头",
    "lanzhou": "兰州", "xining": "西宁", "yinchuan": "银川", "urumqi": "乌鲁木齐",
    "wulumuqi": "乌鲁木齐", "lasa": "拉萨", "nanchang": "南昌", "ganzhou": "赣州",
    "jiujiang": "九江", "shangrao": "上饶", "haerbin": "哈尔滨", "anhui": "合肥",
    "cangzhou": "沧州", "langfang": "廊坊", "weihai": "威海", "zibo": "淄博",
    "taian": "泰安", "jining": "济宁", "heze": "菏泽", "puyang": "濮阳",
    "xingtai": "邢台", "zhangjiakou": "张家口", "chengde": "承德", "rinchang": "日喀则",
}

CACHE = TextCache(Path(__file__).parent.parent / "data" / "cache" / "text-cache.sqlite3")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def get(url: str) -> str | None:
    html = CACHE.get(url)
    if html is not None:
        return html
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        CACHE.put(url, html)
        return html
    except Exception:
        return None


def probe_city(slug: str) -> list[str]:
    html = get(f"https://www.amap.com/ranking/{slug}/food")
    if not html:
        return []
    return sorted(set(re.findall(rf"/ranking/{slug}/food/(\d+)", html)))


def harvest_district(slug: str, code: str) -> list[dict]:
    city = CITY_NAMES[slug]
    url = ranking_url(slug, code)
    html = get(url)
    if not html:
        return []
    return [
        {
            "name": it["name"],
            "city": city,
            "address": it.get("address"),
            "source": url,
            "list_name": "高德状元榜·美食（必吃美食）",
        }
        for it in parse_amap_html(html)
        if it.get("name")
    ]


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 999
    out_path = Path(__file__).parent.parent / "data" / "seed" / "amap-national.json"
    slugs = [s for s in CITY_NAMES if s not in
             ("guangzhou", "shenzhen", "foshan", "dongguan", "zhuhai", "zhongshan",
              "huizhou", "jiangmen", "zhaoqing", "shantou", "chaozhou", "jieyang",
              "shanwei", "meizhou", "heyuan", "qingyuan", "shaoguan", "yunfu",
              "yangjiang", "maoming", "zhanjiang", "huhehaote", "wulumuqi", "haerbin", "anhui")][:limit]

    print(f"探测 {len(slugs)} 个城市 …", flush=True)
    city_districts: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(probe_city, s): s for s in slugs}
        for fut in as_completed(futures):
            slug = futures[fut]
            codes = fut.result()
            if codes:
                city_districts[slug] = codes

    total_pages = sum(len(v) for v in city_districts.values())
    print(f"{len(city_districts)} 个城市有榜单，共 {total_pages} 个分区页，并行抓取 …", flush=True)

    entries: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
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
            if done % 20 == 0:
                print(f"  进度 {done}/{total_pages}，已收割 {len(entries)} 家", flush=True)

    out_path.write_text(
        json.dumps({"schema_version": 1, "source": "amap.com 状元榜·美食（全国收割）", "entries": entries},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    per_city: dict[str, int] = {}
    for e in entries:
        per_city[e["city"]] = per_city.get(e["city"], 0) + 1
    print("完成：", dict(sorted(per_city.items(), key=lambda x: -x[1])[:25]), flush=True)
    print(f"合计 {len(entries)} 家 → {out_path.name}", flush=True)


if __name__ == "__main__":
    main()
