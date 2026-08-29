"""奖项名单匹配：把"榜单/名单"形式的奖项记录匹配到库内饭店记录。

名单文件格式（JSON）：
{
  "schema_version": 1,
  "source": "名单来源 URL",
  "awards": [{"name": "炳胜公馆", "award": "blackpearl_2_diamond@2025", "city": "广州"}, ...]
}

匹配规则：店名归一化（去空白与括号注记）后精确相等优先，其次唯一包含关系；
城市不一致、多个候选命中视为歧义，一律跳过（诚实优先，宁缺勿错）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .batch import name_key, normalize_name
from .storage import Database


def _name_matches(record_norm: str, award_norm: str) -> bool:
    if record_norm == award_norm:
        return True  # 单字店名（江/宋/屿）也允许精确相等
    if len(record_norm) < 2 or len(award_norm) < 2:
        return False
    return record_norm in award_norm or award_norm in record_norm


def apply_awards(db: Database, awards_file: str | Path) -> dict:
    raw = json.loads(Path(awards_file).read_text(encoding="utf-8"))
    entries = raw.get("awards", [])
    summary = {"matched": 0, "already": 0, "ambiguous": 0, "unmatched": 0, "total": len(entries)}
    records = db.restaurants
    for entry in entries:
        award = entry.get("award")
        name = entry.get("name", "")
        name_norm = normalize_name(name)
        if not award or not name_norm:
            summary["unmatched"] += 1
            continue
        # 两段匹配：先按分店级全名（保留括号）精确匹配，避免同名分店歧义；
        # 再按归一化名包含匹配。两个阶段都受城市过滤约束。
        city_records = [
            r for r in records if not entry.get("city") or r.city == entry["city"]
        ]
        exact_branch = [r for r in city_records if name_key(r.name) == name_key(name)]
        candidates = [
            r for r in city_records
            if _name_matches(normalize_name(r.name), name_norm)
        ]
        if exact_branch:
            pool = exact_branch if len(exact_branch) == 1 else []
        elif len(candidates) == 1:
            pool = candidates
        else:
            pool = []
        if not pool:
            summary["ambiguous" if candidates else "unmatched"] += 1
            continue
        record = pool[0]
        awards = list(record.metrics.awards or [])
        if award in awards:
            summary["already"] += 1
            continue
        awards.append(award)
        record.metrics.awards = awards
        db.upsert(record)
        summary["matched"] += 1
    return summary
