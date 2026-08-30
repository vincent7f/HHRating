"""批量自动采集管线测试（采集器注入假引擎，不联网）。"""
import pytest

from hhrating.batch import (
    batch_import,
    collect_restaurant,
    make_record_id,
    normalize_name,
)
from hhrating.collectors.websearch import extract_review_count
from hhrating.storage import Database


class TestExtractReviewCount:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("大众点评 4.5分 共12万+条评价", 120000),
            ("2万+评价", 20000),
            ("1.4万条点评", 14000),
            ("8000条点评", 8000),
            ("有12843条评价", 12843),
            ("27万+ 条点评", 270000),
            ("10.42万收藏", None),  # 收藏数不算点评数
            ("评分4.6 人均100元", None),
            ("没有数字", None),
        ],
    )
    def test_patterns(self, text, expected):
        assert extract_review_count(text) == expected


class TestNaming:
    def test_make_record_id_deterministic(self):
        assert make_record_id("广州", "炳胜公馆") == make_record_id("广州", "炳胜公馆")
        assert make_record_id("广州", "炳胜公馆") != make_record_id("广州", "陶陶居")

    def test_make_record_id_format(self):
        rid = make_record_id("广州", "点都德（大茶楼店）")
        assert rid.startswith("gz-")
        assert len(rid) == 11

    def test_normalize_name(self):
        assert normalize_name("陶陶居酒家（第十甫路总店）") == "陶陶居酒家"
        assert normalize_name("点都德(大茶楼店)") == "点都德"
        assert normalize_name(" 炳胜 公馆 ") == "炳胜公馆"


class FakeCollector:
    """按查询返回预置结果，并记录查询串。"""

    def __init__(self, results_by_keyword):
        self.results_by_keyword = results_by_keyword
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        for keyword, results in self.results_by_keyword.items():
            if keyword in query:
                return results
        return []

    def collect_signals(self, query):
        from hhrating.collectors.websearch import extract_founded_year, extract_rating

        results = self.search(query)
        ratings, years, counts = [], [], []
        for r in results:
            text = f'{r["title"]} {r["snippet"]}'
            for extract, sink in (
                (extract_rating, ratings),
                (extract_founded_year, years),
                (extract_review_count, counts),
            ):
                value = extract(text)
                if value is not None and value not in sink:
                    sink.append(value)
        return {
            "results": results,
            "rating_candidates": ratings,
            "founded_year_candidates": years,
            "review_count_candidates": counts,
        }


BING_LIKE = [
    {"title": "点都德(大茶楼店) - 大众点评", "url": "https://dianping.example.com/1", "snippet": "评分4.7，共5.2万+条点评"},
    {"title": "点都德简介 - 百科", "url": "https://baike.example.com/2", "snippet": "点都德创于1933年"},
]
HISTORY_LIKE = [
    {"title": "点都德的历史 - 文章", "url": "https://news.example.com/3", "snippet": "品牌创立于1933年"},
]


class TestCollectRestaurant:
    def test_merges_signals_into_metrics(self):
        collector = FakeCollector({"大众点评": BING_LIKE, "创立": HISTORY_LIKE})
        record = collect_restaurant("点都德（大茶楼店）", "广州", collector)
        assert record is not None
        assert record["metrics"]["online_rating"] == 4.7
        assert record["metrics"]["review_count"] == 52000
        assert record["metrics"]["founded_year"] == 1933
        assert len(record["sources"]) >= 2
        assert record["data_date"]
        assert "自动采集" in record["notes"]

    def test_second_query_only_when_year_missing(self):
        no_year = [{"title": "某店 - 大众点评", "url": "https://d.example.com/9", "snippet": "评分4.5"}]
        collector = FakeCollector({"大众点评": no_year, "创立": HISTORY_LIKE})
        collect_restaurant("某店", "广州", collector, second_query=False)
        assert len(collector.queries) == 1
        collector2 = FakeCollector({"大众点评": no_year, "创立": HISTORY_LIKE})
        collect_restaurant("某店", "广州", collector2)
        assert len(collector2.queries) == 2

    def test_no_sources_returns_none(self):
        collector = FakeCollector({})
        assert collect_restaurant("无名店", "广州", collector) is None

    def test_conflicting_ratings_take_majority(self):
        results = BING_LIKE + [
            {"title": "点评页", "url": "https://x.example.com/4", "snippet": "评分4.7分 人均80"},
            {"title": "点评页2", "url": "https://x.example.com/5", "snippet": "评分4.2分"},
        ]
        collector = FakeCollector({"大众点评": results})
        record = collect_restaurant("某店", "广州", collector, second_query=False)
        assert record["metrics"]["online_rating"] == 4.7


class TestBatchImport:
    def _db(self, tmp_path):
        return Database(tmp_path / "db.json").load()

    def test_imports_and_skips_existing(self, tmp_path):
        db = self._db(tmp_path)
        names = ["点都德（大茶楼店）", "炳胜公馆（珠江新城店）"]
        collector = FakeCollector({"点都德": BING_LIKE})  # 只有点都德有结果
        summary = batch_import(names, "广州", collector, db, second_query=False)
        assert summary["imported"] == 1
        assert summary["skipped_existing"] == 0
        first_id = make_record_id("广州", "点都德（大茶楼店）")
        assert db.get(first_id).metrics.online_rating == 4.7

        # 重复运行：同名记录跳过，不覆盖已有人工数据
        summary2 = batch_import(names, "广州", collector, db, second_query=False)
        assert summary2["imported"] == 0
        assert summary2["skipped_existing"] == 1
        assert summary2["failed"] == 1  # 炳胜公馆无结果

    def test_respects_limit(self, tmp_path):
        db = self._db(tmp_path)
        names = ["店甲", "店乙", "店丙"]
        collector = FakeCollector({"大众点评": BING_LIKE})
        summary = batch_import(names, "广州", collector, db, limit=2, second_query=False)
        assert summary["imported"] == 2

    def test_guess_cuisine_from_snippets(self):
        from hhrating.batch import guess_cuisine

        assert guess_cuisine(["潮汕菜 砂锅粥"]) == "潮汕菜"
        assert guess_cuisine(["正宗重庆火锅"]) == "火锅"
        assert guess_cuisine(["评分4.5 人均80"]) == "待分类"


class TestNameKey:
    def test_folds_fullwidth_parens(self):
        from hhrating.batch import name_key

        assert name_key("陶陶居酒家（第十甫路总店）") == name_key("陶陶居酒家(第十甫路总店)")
        assert name_key("点都德（大茶楼店）") != name_key("点都德(长隆店)")
