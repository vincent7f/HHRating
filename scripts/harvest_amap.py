"""收割高德"状元榜·美食"珠三角分区榜单 → data/seed/amap-harvest.json

用法：python scripts/harvest_amap.py
输出条目：{name, city, district, address, source, list_name}
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.amap import AmapCollector  # noqa: E402

DISTRICTS = {
    "guangzhou": {
        "city": "广州",
        "codes": {
            "440103": "荔湾区", "440104": "越秀区", "440105": "海珠区", "440106": "天河区",
            "440111": "白云区", "440112": "黄埔区", "440113": "番禺区", "440114": "花都区",
            "440115": "南沙区", "440117": "从化区", "440118": "增城区",
        },
    },
    "shenzhen": {
        "city": "深圳",
        "codes": {
            "440303": "罗湖区", "440304": "福田区", "440305": "南山区", "440306": "宝安区",
            "440307": "龙岗区", "440308": "盐田区", "440309": "龙华区", "440310": "坪山区",
            "440311": "光明区",
        },
    },
    "foshan": {
        "city": "佛山",
        "codes": {
            "440604": "禅城区", "440605": "南海区", "440606": "顺德区",
            "440607": "三水区", "440608": "高明区",
        },
    },
    "dongguan": {"city": "东莞", "codes": {"441900": "东莞市区"}},
    "zhuhai": {"city": "珠海", "codes": {"440402": "香洲区", "440403": "斗门区", "440404": "金湾区"}},
    "zhongshan": {"city": "中山", "codes": {"442000": "中山市区"}},
    "huizhou": {"city": "惠州", "codes": {"441302": "惠城区", "441303": "惠阳区"}},
    "jiangmen": {"city": "江门", "codes": {"440703": "蓬江区", "440705": "新会区"}},
    "zhaoqing": {"city": "肇庆", "codes": {"441202": "端州区", "441203": "鼎湖区"}},
}


def main() -> None:
    # amap.com 为国内站点，显式绕过环境代理直连
    direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    collector = AmapCollector(opener=direct_opener)
    out_path = Path(__file__).parent.parent / "data" / "seed" / "amap-harvest.json"
    entries: list[dict] = []
    ok_pages = fail_pages = 0
    for slug, info in DISTRICTS.items():
        for code, district_name in info["codes"].items():
            url = f"https://www.amap.com/ranking/{slug}/food/{code}"
            try:
                items = collector.fetch(slug, code)
            except Exception as exc:
                print(f"[跳过] {info['city']}{district_name}: {exc}")
                fail_pages += 1
                continue
            for item in items:
                entries.append(
                    {
                        "name": item["name"],
                        "city": info["city"],
                        "district": district_name,
                        "address": item.get("address"),
                        "source": url,
                        "list_name": "2025高德状元榜·美食（必吃美食）",
                    }
                )
            ok_pages += 1
            print(f"[OK] {info['city']}{district_name}: {len(items)} 家")
            time.sleep(0.5)
    out_path.write_text(
        json.dumps({"schema_version": 1, "source": "amap.com 状元榜·美食", "entries": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"完成：{ok_pages} 页成功 / {fail_pages} 页失败，共收割 {len(entries)} 家 → {out_path}")


if __name__ == "__main__":
    main()
