"""发布模块测试：JSON / Markdown / HTML 三种产物。"""
import json

from hhrating.models import Metrics, Restaurant
from hhrating.publish import publish
from hhrating.storage import Database


def seed_db(tmp_path):
    db = Database(tmp_path / "db.json")
    db.upsert(
        Restaurant(
            id="quanjude-qianmen",
            name="全聚德（前门店）",
            city="北京",
            cuisine="烤鸭",
            metrics=Metrics(
                online_rating=4.4,
                review_count=150_000,
                awards=["michelin_1_star@2025"],
                founded_year=1864,
            ),
            sources=["https://example.com/a"],
            data_date="2026-08-29",
        )
    )
    db.upsert(
        Restaurant(
            id="xirongji",
            name="新荣记（南京西路店）",
            city="上海",
            cuisine="台州菜",
            metrics=Metrics(
                online_rating=4.9,
                review_count=8_000,
                awards=["michelin_3_star@2025"],
                celebrity_endorsements=["某名人：极致台州味"],
                founded_year=1995,
            ),
            sources=["https://example.com/b"],
            data_date="2026-08-29",
        )
    )
    return db


def test_publish_creates_three_artifacts(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    assert (out / "hhrating-index.json").exists()
    assert (out / "index.md").exists()
    assert (out / "index.html").exists()


def test_json_structure_and_ordering(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    data = json.loads((out / "hhrating-index.json").read_text(encoding="utf-8"))
    assert data["spec_version"] == "1.1"
    assert data["generated_at"].startswith("20")
    entries = data["restaurants"]
    assert [e["id"] for e in entries] == ["xirongji", "quanjude-qianmen"]  # 综合分降序
    xirongji = entries[0]
    # 新荣记：综合7 名人9(三星8分+名人1分) 人气4 网上9 年代4
    assert xirongji["index"] == "79494"
    assert xirongji["index_detail"] == {
        "overall": 7, "celebrity": 9, "popularity": 4, "online": 9, "age": 4,
    }
    assert xirongji["metrics"]["online_rating"] == 4.9
    assert xirongji["sources"] == ["https://example.com/b"]


def test_markdown_contains_table_and_legend(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    text = (out / "index.md").read_text(encoding="utf-8")
    assert "全聚德（前门店）" in text
    assert "新荣记（南京西路店）" in text
    assert "75879" in text  # 全聚德指数
    assert "名人推荐" in text  # 图例说明


def test_html_is_standalone_and_contains_index(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "75879" in html
    assert "全聚德（前门店）" in html
    assert "<script" in html  # 内嵌排序脚本，无外部依赖


def test_publish_does_not_mutate_database(tmp_path):
    db = seed_db(tmp_path)
    before = [(r.id, r.index) for r in db.restaurants]
    publish(db, tmp_path / "published")
    after = [(r.id, r.index) for r in db.restaurants]
    assert before == after


def test_publish_creates_explorer_page(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    assert (out / "explorer.html").exists()


def _explorer_json(out):
    import json
    import re

    html = (out / "explorer.html").read_text(encoding="utf-8")
    m = re.search(
        r'<script id="hh-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert m, "缺少内嵌数据块"
    return json.loads(m.group(1))


def test_explorer_embeds_full_json(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    data = _explorer_json(out)
    by_id = {e["id"]: e for e in data["restaurants"]}
    assert set(by_id) == {"quanjude-qianmen", "xirongji"}
    q = by_id["quanjude-qianmen"]
    assert q["metrics"]["founded_year"] == 1864
    assert q["sources"] == ["https://example.com/a"]
    assert q["index"] == "75879"
    assert data["spec_version"] == "1.1"


def test_explorer_escapes_script_breaking_content(tmp_path):
    db = seed_db(tmp_path)
    r = db.get("quanjude-qianmen")
    r.notes = "恶意<script>alert(1)</script>备注"
    db.upsert(r)
    out = publish(db, tmp_path / "published")
    data = _explorer_json(out)  # 若转义失效，</script> 会截断数据块导致解析失败
    assert any(e["notes"] and "<script>" in e["notes"] for e in data["restaurants"])


def test_explorer_has_query_ui_and_all_names(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    html = (out / "explorer.html").read_text(encoding="utf-8")
    assert 'id="q"' in html            # 搜索框
    assert 'id="city"' in html         # 城市筛选
    assert 'id="cuisine"' in html      # 菜系筛选
    assert 'id="min"' in html          # 综合分筛选
    assert "applyFilters" in html      # 查询逻辑
    assert "renderDetail" in html      # 详情面板
    for name in ("全聚德（前门店）", "新荣记（南京西路店）"):
        assert name in html


def test_index_links_to_explorer(tmp_path):
    db = seed_db(tmp_path)
    out = publish(db, tmp_path / "published")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "explorer.html" in html
