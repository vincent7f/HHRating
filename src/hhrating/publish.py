"""发布模块：生成 JSON / Markdown / HTML 三种发布产物。

发布时对每条记录按其 metrics + data_date 现场重算指数（不信任库内缓存值），
保证产物与规范实现一致；产物目录默认 published/。
"""
from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from . import SPEC_VERSION
from .scoring import compute_index
from .storage import Database

DIGIT_LABELS = OrderedDict(
    (
        ("overall", "综合"),
        ("celebrity", "名人"),
        ("popularity", "人气"),
        ("online", "网上"),
        ("age", "年代"),
    )
)

LEGEND = (
    "指数共 5 位，每位 1–9 由差到好：第 1 位综合得分、第 2 位名人推荐值、"
    "第 3 位人气度、第 4 位网上得分、第 5 位出现时间（老店分高）。"
    "0 表示该维度暂无数据。评分标准见 docs/index-spec.md v" + SPEC_VERSION + "。"
)

DISCLAIMER = "数据来自公开网络资料的近似统计（快照日期见各条目），仅供研究参考。"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HHRating · 美食点评指数榜</title>
<style>
  :root {{ --accent:#b02a30; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:"Microsoft YaHei","PingFang SC",sans-serif; margin:0; background:#faf7f2; color:#2b2320; }}
  header {{ background:var(--accent); color:#fff; padding:28px 32px; }}
  header h1 {{ margin:0 0 6px; font-size:26px; }}
  header p {{ margin:0; opacity:.85; font-size:13px; }}
  main {{ max-width:1080px; margin:24px auto 48px; padding:0 16px; }}
  .legend {{ background:#fff; border:1px solid #e8ded2; border-radius:8px; padding:12px 16px; font-size:13px; line-height:1.7; margin-bottom:18px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #f0e8dd; font-size:14px; }}
  th {{ background:#f3ece1; cursor:pointer; user-select:none; white-space:nowrap; }}
  th:hover {{ color:var(--accent); }}
  td.idx {{ font-family:Consolas,Menlo,monospace; font-size:18px; font-weight:700; color:var(--accent); letter-spacing:2px; }}
  tr:hover td {{ background:#fdf9f3; }}
  .digits span {{ display:inline-block; min-width:20px; text-align:center; margin-right:2px; padding:1px 4px; border-radius:4px; background:#f3ece1; font-size:12px; }}
  footer {{ text-align:center; font-size:12px; color:#8a7f73; padding:20px; }}
</style>
</head>
<body>
<header>
  <h1>HHRating · 美食点评指数榜</h1>
  <p>生成时间 {generated_at} · 评分标准 v{spec_version} · 共 {count} 家</p>
</header>
<main>
<div class="legend">{legend}</div>
<table id="board">
<thead><tr>
  <th data-key="rank">#</th><th data-key="index">指数</th><th data-key="name">名称</th>
  <th data-key="city">城市</th><th data-key="cuisine">菜系</th><th>逐位明细</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
</main>
<footer>{disclaimer}</footer>
<script>
document.querySelectorAll('#board th[data-key]').forEach(function(th){{
  th.addEventListener('click', function(){{
    var tbody=document.querySelector('#board tbody');
    var rows=[].slice.call(tbody.rows);
    var key=th.dataset.key, dir=th.dataset.dir==='asc'?1:-1;
    th.dataset.dir=dir===1?'desc':'asc';
    rows.sort(function(a,b){{
      var x=a.dataset[key], y=b.dataset[key];
      if(key==='rank'||key==='index'){{ return dir*(parseInt(x,10)-parseInt(y,10)); }}
      return dir*x.localeCompare(y,'zh');
    }});
    rows.forEach(function(r){{ tbody.appendChild(r); }});
  }});
}});
</script>
</body>
</html>
"""


def _score_entries(db: Database) -> list[dict]:
    entries = []
    for r in db.restaurants:
        index, detail = compute_index(r.metrics, r.data_date)
        entry = r.to_dict()
        entry["index"] = index
        entry["index_detail"] = detail
        entries.append(entry)
    entries.sort(key=lambda e: (e["index_detail"]["overall"], e["index"]), reverse=True)
    return entries


def publish(db: Database, out_dir: str | Path, generated_at: str | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = _score_entries(db)
    generated_at = generated_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    _write_json(out, entries, generated_at)
    _write_markdown(out, entries, generated_at)
    _write_html(out, entries, generated_at)
    return out


def _entry_public_dict(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "name": entry["name"],
        "name_en": entry.get("name_en"),
        "city": entry["city"],
        "cuisine": entry["cuisine"],
        "branch": entry.get("branch"),
        "index": entry["index"],
        "index_detail": entry["index_detail"],
        "metrics": entry["metrics"],
        "sources": entry["sources"],
        "data_date": entry["data_date"],
        "notes": entry.get("notes"),
    }


def _write_json(out: Path, entries: list[dict], generated_at: str) -> None:
    payload = {
        "schema_version": 1,
        "spec_version": SPEC_VERSION,
        "generated_at": generated_at,
        "legend": LEGEND,
        "disclaimer": DISCLAIMER,
        "restaurants": [_entry_public_dict(e) for e in entries],
    }
    (out / "hhrating-index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_markdown(out: Path, entries: list[dict], generated_at: str) -> None:
    lines = [
        "# HHRating · 美食点评指数榜",
        "",
        f"> 生成时间：{generated_at} · 评分标准 v{SPEC_VERSION} · 共 {len(entries)} 家",
        "",
        LEGEND,
        "",
        "| 排名 | 指数 | 名称 | 城市 | 菜系 |",
        "|-----:|:-----|:-----|:-----|:-----|",
    ]
    for i, e in enumerate(entries, 1):
        d = e["index_detail"]
        digits = "".join(str(d[k]) for k in DIGIT_LABELS)
        lines.append(f'| {i} | `{digits}` | {e["name"]} | {e["city"]} | {e["cuisine"]} |')
    lines += [
        "",
        "## 逐位说明",
        "",
        "| 位 | 含义 |",
        "|----|------|",
        "| 1 | 综合得分 |",
        "| 2 | 名人推荐值 |",
        "| 3 | 人气度 |",
        "| 4 | 网上得分 |",
        "| 5 | 出现时间 |",
        "",
        f"数据快照日期以各条目 `data_date` 为准。{DISCLAIMER}",
        "",
    ]
    (out / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_html(out: Path, entries: list[dict], generated_at: str) -> None:
    rows = []
    for i, e in enumerate(entries, 1):
        d = e["index_detail"]
        digit_cells = "".join(f'<span title="{label}">{d[key]}</span>' for key, label in DIGIT_LABELS.items())
        rows.append(
            f'<tr data-rank="{i}" data-index="{e["index"]}" data-name="{e["name"]}" '
            f'data-city="{e["city"]}" data-cuisine="{e["cuisine"]}">'
            f"<td>{i}</td><td class=\"idx\">{e['index']}</td><td>{e['name']}</td>"
            f"<td>{e['city']}</td><td>{e['cuisine']}</td><td class=\"digits\">{digit_cells}</td></tr>"
        )
    html = _HTML_TEMPLATE.format(
        generated_at=generated_at,
        spec_version=SPEC_VERSION,
        count=len(entries),
        legend=LEGEND,
        rows="\n".join(rows),
        disclaimer=DISCLAIMER,
    )
    (out / "index.html").write_text(html, encoding="utf-8")
