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
  <p>生成时间 {generated_at} · 评分标准 v{spec_version} · 共 {count} 家 · <a href="explorer.html" style="color:#fff">数据查询页</a></p>
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
    _write_explorer(out, entries, generated_at)
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


_EXPLORER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HHRating · 数据查询</title>
<style>
  :root { --accent:#b02a30; }
  * { box-sizing:border-box; }
  body { font-family:"Microsoft YaHei","PingFang SC",sans-serif; margin:0; background:#faf7f2; color:#2b2320; }
  header { background:var(--accent); color:#fff; padding:24px 32px; }
  header h1 { margin:0 0 6px; font-size:24px; }
  header p { margin:0; opacity:.9; font-size:13px; }
  header a { color:#fff; }
  main { max-width:1200px; margin:20px auto 48px; padding:0 16px; }
  .legend { background:#fff; border:1px solid #e8ded2; border-radius:8px; padding:10px 16px; font-size:13px; line-height:1.7; margin-bottom:14px; }
  .controls { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
  .controls input, .controls select, .controls button {
    padding:8px 10px; border:1px solid #d9cbb8; border-radius:6px; font-size:14px; background:#fff; }
  .controls input { flex:1 1 240px; }
  .controls button { cursor:pointer; }
  .controls button:hover { border-color:var(--accent); color:var(--accent); }
  .status { font-size:13px; color:#8a7f73; margin-bottom:10px; }
  table { width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  th, td { padding:9px 10px; text-align:left; border-bottom:1px solid #f0e8dd; font-size:14px; }
  th { background:#f3ece1; cursor:pointer; user-select:none; white-space:nowrap; }
  th:hover { color:var(--accent); }
  td.idx { font-family:Consolas,Menlo,monospace; font-size:16px; font-weight:700; color:var(--accent); letter-spacing:1px; cursor:pointer; }
  tr.row:hover td { background:#fdf9f3; }
  tr.row.active td { background:#fdf3ee; }
  .digits span { display:inline-block; min-width:18px; text-align:center; margin-right:2px; padding:1px 4px; border-radius:4px; background:#f3ece1; font-size:12px; }
  .zero { color:#b5a99a; }
  #detail { display:none; background:#fff; border:1px solid #e8ded2; border-left:4px solid var(--accent); border-radius:8px; padding:16px 20px; margin-top:14px; font-size:14px; line-height:1.8; }
  #detail h2 { margin:0 0 4px; font-size:18px; color:var(--accent); }
  #detail .sub { color:#8a7f73; font-size:13px; margin-bottom:10px; }
  #detail .big { font-family:Consolas,Menlo,monospace; font-size:24px; font-weight:700; color:var(--accent); letter-spacing:3px; }
  #detail h3 { margin:12px 0 4px; font-size:14px; border-bottom:1px dashed #e8ded2; }
  #detail a { color:var(--accent); word-break:break-all; }
  #detail ul { margin:4px 0; padding-left:20px; }
  .none { color:#b5a99a; }
  footer { text-align:center; font-size:12px; color:#8a7f73; padding:20px; }
</style>
</head>
<body>
<header>
  <h1>HHRating · 数据查询</h1>
  <p>生成时间 __GENERATED__ · 评分标准 v__SPEC__ · <a href="index.html">指数榜单</a> · 全部字段可搜索</p>
</header>
<main>
<div class="legend">__LEGEND__</div>
<div class="controls">
  <input id="q" type="search" placeholder="搜索：店名 / 菜系 / 城市 / 奖项 / 名人 / 备注 …">
  <select id="city"><option value="">全部城市</option></select>
  <select id="cuisine"><option value="">全部菜系</option></select>
  <select id="min">
    <option value="">综合分不限</option>
    <option value="9">综合 ≥ 9</option>
    <option value="7">综合 ≥ 7</option>
    <option value="5">综合 ≥ 5</option>
    <option value="1">综合 ≥ 1（排除暂无数据）</option>
  </select>
  <button id="reset" type="button">重置</button>
</div>
<div class="status" id="status"></div>
<table id="board">
<thead><tr>
  <th data-key="index">指数</th><th data-key="name">名称</th><th data-key="city">城市</th>
  <th data-key="cuisine">菜系</th><th data-key="rating">网上评分</th><th data-key="reviews">点评数</th>
  <th>逐位明细</th>
</tr></thead>
<tbody id="rows"></tbody>
</table>
<div id="detail"></div>
</main>
<footer>__DISCLAIMER__</footer>
<script id="hh-data" type="application/json">__PAYLOAD__</script>
<script>
var DATA = JSON.parse(document.getElementById('hh-data').textContent);
var DIGITS = [["overall","综合得分"],["celebrity","名人推荐值"],["popularity","人气度"],["online","网上得分"],["age","出现时间"]];
var sortKey = null, sortDir = -1;

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function norm(s) { return String(s == null ? "" : s).toLowerCase(); }
function haystack(r) {
  var m = r.metrics || {};
  return [r.name, r.name_en, r.city, r.cuisine, r.branch, r.notes,
    (m.awards||[]).join(" "), (m.celebrity_endorsements||[]).join(" "),
    (m.media_features||[]).join(" "), r.id].join(" ");
}
function getState() {
  return {
    q: document.getElementById('q').value.trim(),
    city: document.getElementById('city').value,
    cuisine: document.getElementById('cuisine').value,
    min: document.getElementById('min').value
  };
}
function filtered() {
  var st = getState();
  return DATA.restaurants.filter(function(r) {
    if (st.q && norm(haystack(r)).indexOf(norm(st.q)) === -1) return false;
    if (st.city && r.city !== st.city) return false;
    if (st.cuisine && r.cuisine !== st.cuisine) return false;
    if (st.min !== "" && r.index_detail.overall < Number(st.min)) return false;
    return true;
  });
}
function digitsCell(r) {
  var d = r.index_detail;
  return DIGITS.map(function(p) {
    var v = d[p[0]];
    return '<span title="' + p[1] + '" class="' + (v === 0 ? 'zero' : '') + '">' + v + '</span>';
  }).join("");
}
function sortValue(r, key) {
  var m = r.metrics || {};
  if (key === "index") return parseInt(r.index, 10);
  if (key === "rating") return m.online_rating == null ? -1 : m.online_rating;
  if (key === "reviews") return m.review_count == null ? -1 : m.review_count;
  return r[key] || "";
}
function renderTable() {
  var rows = filtered();
  if (sortKey) {
    rows = rows.slice().sort(function(a, b) {
      var x = sortValue(a, sortKey), y = sortValue(b, sortKey);
      if (typeof x === "string" && typeof y === "string") return sortDir * x.localeCompare(y, "zh");
      return sortDir * (x - y);
    });
  }
  var html = rows.map(function(r) {
    var m = r.metrics || {};
    return '<tr class="row" data-id="' + esc(r.id) + '">' +
      '<td class="idx">' + esc(r.index) + '</td>' +
      '<td>' + esc(r.name) + '</td>' +
      '<td>' + esc(r.city) + '</td>' +
      '<td>' + esc(r.cuisine || "") + '</td>' +
      '<td>' + (m.online_rating == null ? '<span class="none">—</span>' : m.online_rating.toFixed(1)) + '</td>' +
      '<td>' + (m.review_count == null ? '<span class="none">—</span>' : m.review_count.toLocaleString()) + '</td>' +
      '<td class="digits">' + digitsCell(r) + '</td></tr>';
  }).join("");
  document.getElementById('rows').innerHTML = html;
  document.getElementById('status').textContent =
    '共 ' + DATA.restaurants.length + ' 家 · 筛选结果 ' + rows.length + ' 家（点击行查看全部数据，点击表头排序）';
}
function li(label, values) {
  if (!values || !values.length) return "";
  return '<ul>' + values.map(function(v) { return '<li>' + esc(v) + '</li>'; }).join("") + '</ul>';
}
function renderDetail(id) {
  var r = DATA.restaurants.find(function(x) { return x.id === id; });
  if (!r) return;
  var m = r.metrics || {};
  var d = r.index_detail;
  document.querySelectorAll('tr.row').forEach(function(tr) {
    tr.classList.toggle('active', tr.dataset.id === id);
  });
  var html = '<h2>' + esc(r.name) + ' <span style="font-size:13px;color:#8a7f73">' + esc(r.id) + '</span></h2>' +
    '<div class="sub">' + esc(r.city) + ' · ' + esc(r.cuisine || "—") +
    (r.branch ? ' · ' + esc(r.branch) : '') + ' · 数据快照 ' + esc(r.data_date) + '</div>' +
    '<div class="big">' + esc(r.index) + '</div>' +
    '<div>' + DIGITS.map(function(p) { return p[1] + ' ' + d[p[0]]; }).join('　') + '</div>' +
    '<h3>指标</h3><ul>' +
    '<li>网上评分：' + (m.online_rating == null ? '—' : m.online_rating.toFixed(1) + '（5 分制）') + '</li>' +
    '<li>点评总数：' + (m.review_count == null ? '—' : m.review_count.toLocaleString()) + '</li>' +
    '<li>社媒热度：' + (m.social_mentions == null ? '—' : m.social_mentions.toLocaleString()) + '</li>' +
    '<li>创立年份：' + (m.founded_year == null ? '—' : m.founded_year) + '</li>' +
    '<li>烹饪大师坐镇：' + (m.master_chef ? '是' : '—') + '</li></ul>' +
    (m.awards && m.awards.length ? '<h3>奖项</h3>' + li("奖项", m.awards) : '') +
    (m.celebrity_endorsements && m.celebrity_endorsements.length ? '<h3>名人推荐</h3>' + li("名人", m.celebrity_endorsements) : '') +
    (m.media_features && m.media_features.length ? '<h3>媒体报道</h3>' + li("媒体", m.media_features) : '') +
    '<h3>来源</h3><ul>' + (r.sources||[]).map(function(s) {
      return '<li><a href="' + esc(s) + '" target="_blank" rel="noopener">' + esc(s) + '</a></li>';
    }).join("") + '</ul>' +
    (r.notes ? '<h3>备注</h3><div>' + esc(r.notes) + '</div>' : '');
  var panel = document.getElementById('detail');
  panel.innerHTML = html;
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function applyFilters() { renderTable(); }
function populateSelects() {
  var uniq = function(key) {
    var seen = {};
    DATA.restaurants.forEach(function(r) { if (r[key]) seen[r[key]] = 1; });
    return Object.keys(seen).sort(function(a, b) { return a.localeCompare(b, "zh"); });
  };
  var citySel = document.getElementById('city');
  uniq("city").forEach(function(c) {
    var o = document.createElement('option'); o.value = c; o.textContent = c; citySel.appendChild(o);
  });
  var cuiSel = document.getElementById('cuisine');
  uniq("cuisine").forEach(function(c) {
    var o = document.createElement('option'); o.value = c; o.textContent = c; cuiSel.appendChild(o);
  });
}
document.getElementById('q').addEventListener('input', applyFilters);
['city','cuisine','min'].forEach(function(id) {
  document.getElementById(id).addEventListener('change', applyFilters);
});
document.getElementById('reset').addEventListener('click', function() {
  document.getElementById('q').value = '';
  ['city','cuisine','min'].forEach(function(id) { document.getElementById(id).value = ''; });
  sortKey = null; sortDir = -1;
  document.getElementById('detail').style.display = 'none';
  applyFilters();
});
document.getElementById('rows').addEventListener('click', function(e) {
  var tr = e.target.closest('tr.row');
  if (tr) renderDetail(tr.dataset.id);
});
document.querySelectorAll('#board th[data-key]').forEach(function(th) {
  th.addEventListener('click', function() {
    var key = th.dataset.key;
    if (sortKey === key) { sortDir = -sortDir; } else { sortKey = key; sortDir = -1; }
    renderTable();
  });
});
populateSelects();
applyFilters();
</script>
</body>
</html>
"""


def _embed_json(payload: dict) -> str:
    """内嵌 JSON：转义 < 防止数据中出现 </script> 截断页面。"""
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def _write_explorer(out: Path, entries: list[dict], generated_at: str) -> None:
    payload = {
        "schema_version": 1,
        "spec_version": SPEC_VERSION,
        "generated_at": generated_at,
        "restaurants": [_entry_public_dict(e) for e in entries],
    }
    html = (
        _EXPLORER_TEMPLATE
        .replace("__GENERATED__", generated_at)
        .replace("__SPEC__", SPEC_VERSION)
        .replace("__LEGEND__", LEGEND)
        .replace("__DISCLAIMER__", DISCLAIMER)
        .replace("__PAYLOAD__", _embed_json(payload))
    )
    (out / "explorer.html").write_text(html, encoding="utf-8")


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
        "> 数据查询页：[explorer.html](explorer.html)（可搜索/筛选全部字段）",
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
