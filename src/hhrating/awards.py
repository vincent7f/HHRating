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

from .batch import normalize_name
from .storage import Database


def _name_matches(record_norm: str, award_norm: str) -> bool:
    if len(record_norm) < 2 or len(award_norm) < 2:
        return False
    return record_norm == award_norm or record_norm in award_norm or award_norm in record_norm


def apply_awards(db: Database, awards_file: str | Path) -> dict:
    raw = json.loads(Path(awards_file).read_text(encoding="utf-8"))
    entries = raw.get("awards", [])
    summary = {"matched": 0, "already": 0, "ambiguous": 0, "unmatched": 0, "total": len(entries)}
    records = db.restaurants
    for entry in entries:
        award = entry.get("award")
        name_norm = normalize_name(entry.get("name", ""))
        if not award or not name_norm:
            summary["unmatched"] += 1
            continue
        candidates = [
            r for r in records
            if (not entry.get("city") or r.city == entry["city"])
            and _name_matches(normalize_name(r.name), name_norm)
        ]
        exact = [r for r in candidates if normalize_name(r.name) == name_norm]
        pool = exact or candidates
        if not pool:
            summary["unmatched"] += 1
            continue
        if len(pool) > 1:
            summary["ambiguous"] += 1
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
