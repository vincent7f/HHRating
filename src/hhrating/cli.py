"""命令行接口。

用法（安装后用 `hhrating`，源码目录用 `python -m hhrating`）：
  hhrating import data/seed/restaurants.json   # 导入种子数据
  hhrating add --id xx --name ...              # 手工录入
  hhrating score [--id ID]                     # 计算/刷新指数
  hhrating list [--min N]                      # 指数榜单
  hhrating show ID_OR_NAME                     # 档案详情
  hhrating collect --query "..." [--proxy ...] # 联网检索辅助信号
  hhrating publish [--out DIR]                 # 发布 JSON/MD/HTML
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from . import __version__
from .collectors import create_collector
from .models import Metrics, Restaurant
from .scoring import compute_index
from .storage import Database

DEFAULT_DB = "data/restaurants.json"
DEFAULT_CACHE = "data/cache/text-cache.sqlite3"


def _cache_from(args):
    """按 --no-cache 构造本地文本缓存（默认 7 天有效）。"""
    if getattr(args, "no_cache", False):
        return None
    from .cache import TextCache

    return TextCache(DEFAULT_CACHE)


DIGIT_LABELS = (
    ("overall", "综合得分"),
    ("celebrity", "名人推荐值"),
    ("popularity", "人气度"),
    ("online", "网上得分"),
    ("age", "出现时间"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhrating", description="美食点评指数资料库")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"数据库 JSON 路径（默认 {DEFAULT_DB}）")
    parser.add_argument("--version", action="version", version=f"hhrating {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="从 JSON 文件导入记录（结构见 docs/data-dictionary.md）")
    p.add_argument("file")

    p = sub.add_parser("add", help="录入一家饭店")
    p.add_argument("--id", required=True, help="唯一 slug，如 quanjude-qianmen")
    p.add_argument("--name", required=True)
    p.add_argument("--city", required=True)
    p.add_argument("--cuisine", required=True)
    p.add_argument("--name-en", dest="name_en")
    p.add_argument("--branch")
    p.add_argument("--address", help="详细地址")
    p.add_argument("--rating", type=float, help="网上评分（0-5）")
    p.add_argument("--reviews", type=int, help="全网点评总数")
    p.add_argument("--social", type=int, help="社交媒体热度条目数")
    p.add_argument("--founded-year", type=int)
    p.add_argument("--award", action="append", default=[], help="奖项枚举，可重复")
    p.add_argument("--celebrity", action="append", default=[], help="名人推荐记录，可重复")
    p.add_argument("--media", action="append", default=[], help="媒体报道，可重复")
    p.add_argument("--master-chef", action="store_true", help="有烹饪大师坐镇")
    p.add_argument("--source", action="append", required=True, help="来源 URL，至少一条")
    p.add_argument("--data-date", default=date.today().isoformat(), help="数据快照日期")
    p.add_argument("--notes")

    p = sub.add_parser("score", help="计算/刷新指数")
    p.add_argument("--id", help="仅指定记录")

    p = sub.add_parser("list", help="指数榜单")
    p.add_argument("--min", type=int, default=None, help="只显示综合得分 ≥ N 的记录")

    p = sub.add_parser("show", help="查看档案详情")
    p.add_argument("target", help="id 或名称")

    p = sub.add_parser("collect", help="联网检索公开摘要，辅助整理指标（结果需人工确认）")
    p.add_argument("--query", required=True)
    p.add_argument("--proxy", default=None, help="HTTP 代理，如 http://127.0.0.1:8009")
    p.add_argument("--no-cache", action="store_true", help="禁用本地网页缓存")

    p = sub.add_parser("batch", help="按店名清单自动批量采集并入库")
    p.add_argument("--names-file", required=True, help="店名清单（每行一个，# 为注释）")
    p.add_argument("--city", required=True)
    p.add_argument("--proxy", default=None, help="HTTP 代理，如 http://127.0.0.1:8009")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=0.8, help="每次检索间隔秒数")
    p.add_argument("--no-second-query", action="store_true", help="不追加创立年份补充检索")
    p.add_argument("--no-cache", action="store_true", help="禁用本地网页缓存")

    p = sub.add_parser("apply-awards", help="把奖项名单（JSON）匹配到库内记录")
    p.add_argument("file")

    p = sub.add_parser("fill", help="对在库记录定向补采缺失指标（不覆盖已有值）")
    p.add_argument("--city", required=True)
    p.add_argument("--proxy", default=None)
    p.add_argument("--delay", type=float, default=2.5, help="每次检索间隔秒数")

    p = sub.add_parser("stats", help="数据库统计分析（覆盖率/分布/TOP榜）")

    p = sub.add_parser("publish", help="发布 JSON/Markdown/HTML")
    p.add_argument("--out", default="published", help="输出目录（默认 published/）")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = Database(args.db).load()

    try:
        if args.command == "import":
            return _cmd_import(db, args.file)
        if args.command == "add":
            return _cmd_add(db, args)
        if args.command == "score":
            return _cmd_score(db, args.id)
        if args.command == "list":
            return _cmd_list(db, args.min)
        if args.command == "show":
            return _cmd_show(db, args.target)
        if args.command == "collect":
            return _cmd_collect(args)
        if args.command == "batch":
            return _cmd_batch(db, args)
        if args.command == "apply-awards":
            return _cmd_apply_awards(db, args.file)
        if args.command == "fill":
            return _cmd_fill(db, args)
        if args.command == "stats":
            return _cmd_stats(db)
        if args.command == "publish":
            return _cmd_publish(db, args.out)
    except (ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------- import
def _cmd_import(db: Database, file_path: str) -> int:
    import json
    from pathlib import Path

    raw = json.loads(Path(file_path).read_text(encoding="utf-8"))
    items = raw["restaurants"] if isinstance(raw, dict) else raw
    imported = 0
    for item in items:
        restaurant = Restaurant.from_dict(item)
        db.upsert(restaurant)
        imported += 1
    print(f"已导入 {imported} 条记录 → {db.path}")
    return 0


# ------------------------------------------------------------------------ add
def _cmd_add(db: Database, args) -> int:
    restaurant = Restaurant(
        id=args.id,
        name=args.name,
        name_en=args.name_en,
        city=args.city,
        cuisine=args.cuisine,
        branch=args.branch,
        address=args.address,
        metrics=Metrics(
            online_rating=args.rating,
            review_count=args.reviews,
            social_mentions=args.social,
            awards=list(args.award) or None,
            celebrity_endorsements=list(args.celebrity) or None,
            media_features=list(args.media) or None,
            master_chef=True if args.master_chef else None,
            founded_year=args.founded_year,
        ),
        sources=list(args.source),
        data_date=args.data_date,
        notes=args.notes,
    )
    db.upsert(restaurant)
    print(f"已录入：{restaurant.name}（{restaurant.id}）")
    return 0


# ----------------------------------------------------------------------- score
def _cmd_score(db: Database, target_id: str | None) -> int:
    targets = [db.get(target_id)] if target_id else db.restaurants
    if target_id and targets[0] is None:
        raise ValueError(f"找不到记录：{target_id}")
    for r in targets:
        r.index, r.index_detail = compute_index(r.metrics, r.data_date)
    db.save()  # 单次写盘：逐条 upsert 会触发 O(n²) 全文件序列化，大库会崩溃
    for r in sorted(targets, key=lambda x: x.index or "", reverse=True):
        print(f"{r.index}  {r.name}")
    return 0


# ------------------------------------------------------------------------ list
def _cmd_list(db: Database, minimum: int | None) -> int:
    rows = []
    for r in db.restaurants:
        if r.index is None:
            index, detail = compute_index(r.metrics, r.data_date)
            r.index, r.index_detail = index, detail
            db.upsert(r)
        rows.append(r)
    db.save()
    scored = [r for r in rows if r.index]
    scored.sort(key=lambda r: (r.index_detail["overall"], r.index), reverse=True)
    unscored = [r for r in rows if not r.index]
    if minimum is not None:
        scored = [r for r in scored if r.index_detail["overall"] >= minimum]
    for i, r in enumerate(scored, 1):
        print(f"{i:>3}. {r.index}  {r.name}（{r.city} · {r.cuisine}）")
    for r in unscored:
        print(f"  —   未评分  {r.name}（{r.city} · {r.cuisine}）")
    print(f"共 {len(scored) + len(unscored)} 家（未评分 {len(unscored)} 家）")
    return 0


# ------------------------------------------------------------------------ show
def _cmd_show(db: Database, target: str) -> int:
    record = db.get(target) or next(
        (r for r in db.restaurants if r.name == target), None
    )
    if record is None:
        raise ValueError(f"找不到记录：{target}")
    if record.index is None:
        record.index, record.index_detail = compute_index(record.metrics, record.data_date)
    print(f"{record.name} [{record.id}]")
    subtitle = f"{record.city} · {record.cuisine}"
    if record.branch:
        subtitle += f" · {record.branch}"
    print(subtitle)
    if record.address:
        print(f"地址：{record.address}")
    print()
    print(f"指数：{record.index}")
    for key, label in DIGIT_LABELS:
        print(f"  {label:　<8}{record.index_detail[key]:>2}")
    m = record.metrics
    print()
    print("指标（快照 " + record.data_date + "）：")
    print(f"  网上评分：{m.online_rating if m.online_rating is not None else '—'}（5 分制）")
    print(f"  点评总数：{m.review_count if m.review_count is not None else '—'}")
    print(f"  社媒热度：{m.social_mentions if m.social_mentions is not None else '—'}")
    print(f"  创立年份：{m.founded_year if m.founded_year is not None else '—'}")
    if m.awards:
        print(f"  奖项：{'、'.join(m.awards)}")
    if m.celebrity_endorsements:
        print(f"  名人推荐：{'；'.join(m.celebrity_endorsements)}")
    if m.media_features:
        print(f"  媒体报道：{'；'.join(m.media_features)}")
    if m.master_chef:
        print("  烹饪大师坐镇：是")
    print()
    print("来源：")
    for s in record.sources:
        print(f"  - {s}")
    if record.notes:
        print(f"\n备注：{record.notes}")
    return 0


# --------------------------------------------------------------------- collect
def _cmd_collect(args) -> int:
    collector = create_collector(proxy=args.proxy, cache=_cache_from(args))
    signals = collector.collect_signals(args.query)
    print(f"查询：{args.query}")
    print(f"评分候选：{signals['rating_candidates'] or '无'}")
    print(f"创立年份候选：{signals['founded_year_candidates'] or '无'}")
    print(f"点评数候选：{signals.get('review_count_candidates') or '无'}")
    print()
    for r in signals["results"]:
        print(f"· {r['title']}")
        print(f"  {r['url']}")
        print(f"  {r['snippet']}")
    print()
    print("（以上为公开摘要信号，录入前请人工核对来源）")
    return 0


# ----------------------------------------------------------------------- batch
def _cmd_batch(db: Database, args) -> int:
    from pathlib import Path

    from .batch import batch_import

    names = []
    for line in Path(args.names_file).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    collector = create_collector(proxy=args.proxy, cache=_cache_from(args))
    summary = batch_import(
        names,
        args.city,
        collector,
        db,
        limit=args.limit,
        second_query=not args.no_second_query,
        delay=args.delay,
        progress=lambda msg: print(msg, flush=True),
    )
    print(
        f"完成：新收录 {summary['imported']} 家，"
        f"已存在跳过 {summary['skipped_existing']} 家，失败 {summary['failed']} 家"
    )
    return 0


def _cmd_apply_awards(db: Database, file_path: str) -> int:
    from .awards import apply_awards

    summary = apply_awards(db, file_path)
    print(
        f"奖项匹配：成功 {summary['matched']} 条（其中已存在 {summary['already']} 条），"
        f"歧义跳过 {summary['ambiguous']} 条，未匹配 {summary['unmatched']} 条"
    )
    return 0


def _cmd_fill(db: Database, args) -> int:
    from .batch import fill_missing

    collector = create_collector(proxy=args.proxy, cache=_cache_from(args))
    summary = fill_missing(
        db, args.city, collector, delay=args.delay, progress=lambda msg: print(msg, flush=True)
    )
    print(f"补采完成：更新 {summary['updated']} 家，无补充 {summary['failed']} 家，完整跳过 {summary['skipped']} 家")
    return 0


def _cmd_stats(db: Database) -> int:
    from .analysis import format_summary, summarize

    print(format_summary(summarize(db)))
    return 0


# --------------------------------------------------------------------- publish
def _cmd_publish(db: Database, out: str) -> int:
    from .publish import publish

    out_dir = publish(db, out)
    print(f"已发布：{out_dir}/hhrating-index.json、index.md、index.html")
    return 0
