"""统计分析：维度覆盖率、逐位分布、榜单概览。"""
from __future__ import annotations

from collections import Counter

from .scoring import compute_index
from .storage import Database

DIMENSIONS = (
    ("online", "网上得分"),
    ("popularity", "人气度"),
    ("celebrity", "名人推荐值"),
    ("age", "出现时间"),
)


def summarize(db: Database) -> dict:
    total = len(db.restaurants)
    detail_by_id = {}
    for r in db.restaurants:
        _, detail = compute_index(r.metrics, r.data_date)
        detail_by_id[r.id] = detail

    coverage = {}
    for key, _ in DIMENSIONS:
        coverage[key] = sum(1 for d in detail_by_id.values() if d[key] > 0)

    overall_hist = Counter(d["overall"] for d in detail_by_id.values())

    def _top(key, n=5):
        scored = [
            {"name": r.name, "index": detail_by_id[r.id][key], "id": r.id}
            for r in db.restaurants
            if detail_by_id[r.id][key] > 0
        ]
        scored.sort(key=lambda x: x["index"], reverse=True)
        return scored[:n]

    by_city = Counter(r.city for r in db.restaurants)
    return {
        "total": total,
        "by_city": dict(by_city),
        "coverage": coverage,
        "overall_hist": dict(sorted(overall_hist.items())),
        "top_overall": _top("overall"),
        "top_popularity": _top("popularity"),
        "top_celebrity": _top("celebrity"),
        "top_age": _top("age"),
    }


def format_summary(s: dict) -> str:
    lines = [f"收录：{s['total']} 家（按城市：{'、'.join(f'{k} {v}' for k, v in s['by_city'].items())}）"]
    lines.append("维度覆盖（非 0 记录数）：")
    for key, label in DIMENSIONS:
        n = s["coverage"][key]
        pct = f"{n / s['total'] * 100:.0f}%" if s["total"] else "0%"
        lines.append(f"  {label}　{n}/{s['total']}（{pct}）")
    hist = "  ".join(f"综合{d}位:{c}家" for d, c in s["overall_hist"].items())
    lines.append(f"综合得分分布：{hist}")

    def _board(title, rows, label):
        lines.append(title)
        for i, row in enumerate(rows, 1):
            lines.append(f"  {i}. {row['name']}（{label} {row['index']}）")

    _board("综合 TOP5：", s["top_overall"], "综合")
    _board("人气 TOP5：", s["top_popularity"], "人气")
    _board("名人推荐 TOP5：", s["top_celebrity"], "名人")
    _board("老字号 TOP5：", s["top_age"], "年代")
    return "\n".join(lines)
