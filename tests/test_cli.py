"""CLI 集成测试：通过 main(argv) 驱动，验证命令行为与退出码。"""
import json

import pytest

from hhrating.cli import main
from hhrating.storage import Database


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "db.json"


def seed_record_dict():
    return {
        "id": "quanjude-qianmen",
        "name": "全聚德（前门店）",
        "city": "北京",
        "cuisine": "烤鸭",
        "metrics": {
            "online_rating": 4.4,
            "review_count": 150000,
            "awards": ["michelin_1_star@2025"],
            "founded_year": 1864,
        },
        "sources": ["https://example.com/a"],
        "data_date": "2026-08-29",
    }


def test_import_then_score_then_list(tmp_path, db_path, capsys):
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps({"schema_version": 1, "restaurants": [seed_record_dict()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert main(["--db", str(db_path), "import", str(seed)]) == 0
    assert main(["--db", str(db_path), "score"]) == 0
    out = capsys.readouterr().out
    assert "全聚德（前门店）" in out
    assert "75879" in out
    stored = Database(db_path).load().get("quanjude-qianmen")
    assert stored.index == "75879"
    assert stored.index_detail["overall"] == 7


def test_list_reports_missing_scores(tmp_path, db_path, capsys):
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps({"schema_version": 1, "restaurants": [seed_record_dict()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    main(["--db", str(db_path), "import", str(seed)])
    capsys.readouterr()
    assert main(["--db", str(db_path), "list"]) == 0
    out = capsys.readouterr().out
    assert "未评分" in out


def test_show_unknown_id_fails(tmp_path, db_path):
    assert main(["--db", str(db_path), "show", "nope"]) == 1


def test_show_prints_digit_breakdown(tmp_path, db_path, capsys):
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps({"schema_version": 1, "restaurants": [seed_record_dict()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    main(["--db", str(db_path), "import", str(seed)])
    main(["--db", str(db_path), "score"])
    capsys.readouterr()
    assert main(["--db", str(db_path), "show", "quanjude-qianmen"]) == 0
    out = capsys.readouterr().out
    assert "名人推荐值" in out
    assert "https://example.com/a" in out


def test_add_creates_record(tmp_path, db_path, capsys):
    argv = [
        "--db", str(db_path), "add",
        "--id", "test-dian",
        "--name", "测试店",
        "--city", "杭州",
        "--cuisine", "本帮菜",
        "--rating", "4.2",
        "--reviews", "3000",
        "--founded-year", "1990",
        "--source", "https://example.com/x",
        "--data-date", "2026-08-29",
    ]
    assert main(argv) == 0
    record = Database(db_path).load().get("test-dian")
    assert record.metrics.online_rating == 4.2
    assert record.metrics.review_count == 3000


def test_import_rejects_unknown_award(tmp_path, db_path):
    bad = seed_record_dict()
    bad["metrics"]["awards"] = ["golden_fork"]
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"schema_version": 1, "restaurants": [bad]}), encoding="utf-8")
    assert main(["--db", str(db_path), "import", str(seed)]) == 1


def test_publish_writes_files(tmp_path, db_path):
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps({"schema_version": 1, "restaurants": [seed_record_dict()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    main(["--db", str(db_path), "import", str(seed)])
    main(["--db", str(db_path), "score"])
    out_dir = tmp_path / "published"
    assert main(["--db", str(db_path), "publish", "--out", str(out_dir)]) == 0
    assert (out_dir / "index.md").exists()
    assert (out_dir / "hhrating-index.json").exists()


def test_seed_command_shows_collector_signals(tmp_path, db_path, capsys, monkeypatch):
    from hhrating.collectors import websearch as ws

    fixture = (
        '<a class="result__a" href="//e.com/1">测试店 - 点评</a>'
        '<a class="result__snippet">评分4.6，创立于1900年</a>'
    )

    class FakeResponse:
        def read(self):
            return fixture.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ws.DuckDuckGoCollector, "search", lambda self, q: ws.parse_ddg_html(fixture))
    assert main(["--db", str(db_path), "collect", "--query", "测试店 点评"]) == 0
    out = capsys.readouterr().out
    assert "4.6" in out
    assert "1900" in out
