"""CLI batch / apply-awards / stats 命令与奖项匹配、统计分析的测试。"""
import json

from hhrating.analysis import summarize
from hhrating.awards import apply_awards
from hhrating.batch import make_record_id
from hhrating.cli import main
from hhrating.models import Metrics, Restaurant
from hhrating.storage import Database


def make_record(id_, name, city, metrics, data_date="2026-08-29"):
    return Restaurant(
        id=id_, name=name, city=city, cuisine="粤菜",
        metrics=Metrics(**metrics), sources=["https://example.com/s"], data_date=data_date,
    )


class TestApplyAwards:
    def _db(self, tmp_path):
        db = Database(tmp_path / "db.json").load()
        db.upsert(make_record("gz-1", "陶陶居酒家（第十甫路总店）", "广州", {}))
        db.upsert(make_record("gz-2", "炳胜公馆", "广州", {"awards": ["michelin_1_star"]}))
        db.upsert(make_record("sh-1", "老正兴菜馆", "上海", {}))
        return db

    def _awards_file(self, tmp_path, entries):
        p = tmp_path / "awards.json"
        p.write_text(
            json.dumps({"schema_version": 1, "source": "https://example.com/list", "awards": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(p)

    def test_exact_and_contains_match(self, tmp_path):
        db = self._db(tmp_path)
        path = self._awards_file(tmp_path, [
            {"name": "陶陶居", "award": "blackpearl_1_diamond@2025", "city": "广州"},
            {"name": "炳胜公馆", "award": "blackpearl_2_diamond@2025", "city": "广州"},
        ])
        summary = apply_awards(db, path)
        assert summary["matched"] == 2
        assert db.get("gz-1").metrics.awards == ["blackpearl_1_diamond@2025"]

    def test_idempotent_and_city_scoped(self, tmp_path):
        db = self._db(tmp_path)
        path = self._awards_file(tmp_path, [
            {"name": "炳胜公馆", "award": "michelin_1_star", "city": "广州"},
            {"name": "老正兴菜馆", "award": "michelin_1_star", "city": "广州"},  # 城市不匹配
        ])
        summary = apply_awards(db, path)
        assert summary["already"] == 1
        assert summary["unmatched"] == 1

    def test_ambiguous_match_skipped(self, tmp_path):
        db = self._db(tmp_path)
        db.upsert(make_record("gz-3", "炳胜分店A", "广州", {}))
        db.upsert(make_record("gz-4", "炳胜分店B", "广州", {}))
        path = self._awards_file(tmp_path, [{"name": "炳胜", "award": "bib_gourmand", "city": "广州"}])
        summary = apply_awards(db, path)
        assert summary["ambiguous"] == 1
        assert db.get("gz-3").metrics.awards is None

    def test_branch_level_exact_match_wins(self, tmp_path):
        db = self._db(tmp_path)
        db.upsert(make_record("gz-5", "大鸽饭（棠下涌西路）", "广州", {}))
        db.upsert(make_record("gz-6", "大鸽饭（北京路店）", "广州", {}))
        path = self._awards_file(tmp_path, [
            {"name": "大鸽饭（棠下涌西路）", "award": "bib_gourmand@2025", "city": "广州"},
        ])
        summary = apply_awards(db, path)
        assert summary["matched"] == 1
        assert db.get("gz-5").metrics.awards == ["bib_gourmand@2025"]
        assert db.get("gz-6").metrics.awards is None

    def test_single_char_name_exact_match(self, tmp_path):
        db = self._db(tmp_path)
        db.upsert(make_record("gz-7", "江（文华东方酒店）", "广州", {}))
        path = self._awards_file(tmp_path, [{"name": "江", "award": "michelin_2_star@2025", "city": "广州"}])
        summary = apply_awards(db, path)
        assert summary["matched"] == 1
        assert db.get("gz-7").metrics.awards == ["michelin_2_star@2025"]


class TestSummarize:
    def test_coverage_and_top_lists(self, tmp_path):
        db = Database(tmp_path / "db.json").load()
        db.upsert(make_record("a", "甲店", "广州", {
            "online_rating": 4.8, "review_count": 200000, "founded_year": 1880,
        }))
        db.upsert(make_record("b", "乙店", "广州", {"online_rating": 4.2}))
        s = summarize(db)
        assert s["total"] == 2
        assert s["coverage"]["online"] == 2
        assert s["coverage"]["popularity"] == 1
        assert s["coverage"]["age"] == 1
        assert s["top_overall"][0]["name"] == "甲店"
        assert s["top_popularity"][0]["name"] == "甲店"
        assert s["by_city"]["广州"] == 2


class TestCliCommands:
    def _names_file(self, tmp_path):
        p = tmp_path / "names.txt"
        p.write_text("# 注释行\n点都德（大茶楼店）\n炳胜公馆\n", encoding="utf-8")
        return str(p)

    def test_batch_command(self, tmp_path, capsys, monkeypatch):
        from hhrating import cli
        from hhrating.collectors import websearch as ws

        class FakeCollector:
            def search(self, query):
                if "点都德" in query:
                    return [{"title": "点都德 - 大众点评", "url": "https://d.example.com/1",
                             "snippet": "评分4.7，5万+条点评，创于1933年"}]
                return []

            def collect_signals(self, query):
                from hhrating.batch import collect_restaurant  # noqa: F401
                results = self.search(query)
                return {"results": results, "rating_candidates": [4.7],
                        "founded_year_candidates": [1933], "review_count_candidates": [50000]}

        monkeypatch.setattr(cli, "create_collector", lambda proxy=None, cache=None: FakeCollector())
        db_path = tmp_path / "db.json"
        out_dir = tmp_path / "pub"
        assert main([
            "--db", str(db_path), "batch", "--names-file", self._names_file(tmp_path),
            "--city", "广州", "--no-second-query",
        ]) == 0
        out = capsys.readouterr().out
        assert "新收录 1 家" in out
        db = Database(db_path).load()
        assert len(db.restaurants) == 1
        record = db.restaurants[0]
        assert record.metrics.online_rating == 4.7
        assert record.metrics.founded_year == 1933

    def test_apply_awards_command(self, tmp_path, capsys):
        db_path = tmp_path / "db.json"
        db = Database(db_path).load()
        db.upsert(make_record("gz-1", "陶陶居酒家", "广州", {}))
        db.save()
        path = tmp_path / "awards.json"
        path.write_text(json.dumps({"schema_version": 1, "source": "s", "awards": [
            {"name": "陶陶居", "award": "bib_gourmand@2025", "city": "广州"}]}), encoding="utf-8")
        assert main(["--db", str(db_path), "apply-awards", str(path)]) == 0
        assert Database(db_path).load().get("gz-1").metrics.awards == ["bib_gourmand@2025"]

    def test_stats_command(self, tmp_path, capsys):
        db_path = tmp_path / "db.json"
        db = Database(db_path).load()
        db.upsert(make_record("a", "甲店", "广州", {
            "online_rating": 4.8, "review_count": 200000, "founded_year": 1880}))
        db.save()
        assert main(["--db", str(db_path), "stats"]) == 0
        out = capsys.readouterr().out
        assert "收录" in out
        assert "网上得分" in out

    def test_fill_updates_only_missing(self, tmp_path, monkeypatch):
        from hhrating import cli

        class FakeCollector:
            def search(self, query):
                if "评分" in query:
                    return [{"title": "乙店-点评", "url": "https://dp.example.com/b",
                             "snippet": "评分4.3，共9000条点评"}]
                if "创立" in query:
                    return [{"title": "乙店历史", "url": "https://n.example.com/h",
                             "snippet": "乙店创立于1950年"}]
                return []

        monkeypatch.setattr(cli, "create_collector", lambda proxy=None, cache=None: FakeCollector())
        db_path = tmp_path / "db.json"
        db = Database(db_path).load()
        db.upsert(make_record("gz-a", "甲店", "广州", {"online_rating": 4.8}))  # 完整 → 跳过
        db.upsert(make_record("gz-b", "乙店", "广州", {}))  # 全缺 → 补齐
        db.save()
        assert main(["--db", str(db_path), "fill", "--city", "广州", "--delay", "0"]) == 0
        reloaded = Database(db_path).load()
        assert reloaded.get("gz-a").metrics.online_rating == 4.8  # 未被覆盖
        filled = reloaded.get("gz-b")
        assert filled.metrics.online_rating == 4.3
        assert filled.metrics.review_count == 9000
        assert filled.metrics.founded_year == 1950
        assert "补采" in (filled.notes or "")

    def test_classify_command(self, tmp_path, capsys):
        db_path = tmp_path / "db.json"
        db = Database(db_path).load()
        db.upsert(Restaurant(
            id="gz-1", name="木屋烧烤", city="广州", cuisine="待分类",
            metrics=Metrics(), sources=["https://e.com/s"], data_date="2026-08-31",
        ))
        db.save()
        assert main(["--db", str(db_path), "classify"]) == 0
        out = capsys.readouterr().out
        assert "已分类 1 家" in out
        assert "烧烤" in out
        assert Database(db_path).load().get("gz-1").cuisine == "烧烤"
