"""数据模型与存储层测试。"""
import json

import pytest

from hhrating.models import Metrics, Restaurant
from hhrating.storage import Database, SCHEMA_VERSION


def make_restaurant(**overrides):
    payload = dict(
        id="quanjude-qianmen",
        name="全聚德（前门店）",
        city="北京",
        cuisine="烤鸭",
        metrics=Metrics(
            online_rating=4.4,
            review_count=150_000,
            social_mentions=20_000,
            awards=["michelin_1_star@2025"],
            celebrity_endorsements=["某某：烤鸭好"],
            media_features=["舌尖上的中国"],
            master_chef=True,
            founded_year=1864,
        ),
        sources=["https://example.com/a"],
        data_date="2026-08-29",
    )
    for key, value in overrides.items():
        payload[key] = value
    return Restaurant(**payload)


class TestModels:
    def test_roundtrip_dict(self):
        r = make_restaurant()
        assert Restaurant.from_dict(r.to_dict()) == r

    def test_to_dict_is_json_serializable(self):
        r = make_restaurant()
        json.dumps(r.to_dict(), ensure_ascii=False)

    def test_metrics_partial_defaults(self):
        m = Metrics()
        assert m.online_rating is None
        assert m.review_count is None
        assert m.awards is None  # None = 未调研；[] = 已调研无信号
        assert m.master_chef is None

    def test_invalid_online_rating_rejected(self):
        with pytest.raises(ValueError, match="online_rating"):
            Metrics(online_rating=5.5)

    def test_negative_review_count_rejected(self):
        with pytest.raises(ValueError, match="review_count"):
            Metrics(review_count=-1)

    def test_invalid_founded_year_rejected(self):
        with pytest.raises(ValueError, match="founded_year"):
            Metrics(founded_year=999)

    def test_missing_required_fields_rejected(self):
        bad = make_restaurant().to_dict()
        del bad["name"]
        with pytest.raises(ValueError, match="name"):
            Restaurant.from_dict(bad)

    def test_empty_sources_rejected(self):
        with pytest.raises(ValueError, match="sources"):
            make_restaurant(sources=[])


class TestDatabase:
    def test_save_and_load_roundtrip(self, tmp_path):
        db = Database(tmp_path / "db.json")
        r = make_restaurant()
        db.upsert(r)
        reloaded = Database(tmp_path / "db.json")
        assert reloaded.load().restaurants == [r]

    def test_writes_schema_version(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant())
        raw = json.loads((tmp_path / "db.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == SCHEMA_VERSION

    def test_upsert_replaces_same_id(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant())
        db.upsert(make_restaurant(name="全聚德（前门大街店）"))
        db2 = Database(tmp_path / "db.json")
        assert len(db2.load().restaurants) == 1
        assert db2.load().restaurants[0].name == "全聚德（前门大街店）"

    def test_load_missing_file_returns_empty(self, tmp_path):
        db = Database(tmp_path / "nope.json")
        assert db.load().restaurants == []

    def test_load_invalid_json_raises(self, tmp_path):
        p = tmp_path / "db.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON"):
            Database(p).load()

    def test_load_wrong_schema_version_rejected(self, tmp_path):
        p = tmp_path / "db.json"
        p.write_text(json.dumps({"schema_version": 999, "restaurants": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="schema_version"):
            Database(p).load()

    def test_get_by_id(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant())
        assert db.get("quanjude-qianmen").name == "全聚德（前门店）"
        assert db.get("nope") is None

    def test_remove(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant())
        assert db.remove("quanjude-qianmen") is True
        assert db.get("quanjude-qianmen") is None
        assert db.remove("quanjude-qianmen") is False

    def test_list_all_sorted_by_id(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant(id="b", name="乙店"))
        db.upsert(make_restaurant(id="a", name="甲店"))
        assert [r.id for r in db.list_all()] == ["a", "b"]

    def test_unicode_pretty_output(self, tmp_path):
        db = Database(tmp_path / "db.json")
        db.upsert(make_restaurant())
        text = (tmp_path / "db.json").read_text(encoding="utf-8")
        assert "全聚德（前门店）" in text
