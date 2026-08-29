"""高德状元榜采集与名录导入测试。"""
import json
from pathlib import Path

import pytest

from hhrating.amap import AmapCollector, parse_amap_jsonld
from hhrating.batch import import_list_records
from hhrating.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "amap_tianhe.jsonld"


class TestParseJsonLd:
    def test_parses_ranking_items(self):
        raw = FIXTURE.read_text(encoding="utf-8")
        items = parse_amap_jsonld(raw)
        assert len(items) == 10
        assert items[0]["name"] == "SKY NO.1空中一号"
        assert items[1]["name"] == "炳胜品味(珠江新城旗舰店)"
        assert items[0]["position"] == 1
        # 空地址字段统一为 None
        assert items[0]["address"] is None

    def test_address_kept_when_present(self):
        raw = json.dumps(
            {
                "@type": "ItemList",
                "itemListElement": [
                    {"position": 1, "item": {"@type": "Place", "name": "甲店", "address": "广州市荔湾区第十甫路20号"}},
                ],
            },
            ensure_ascii=False,
        )
        items = parse_amap_jsonld(raw)
        assert items[0]["address"] == "广州市荔湾区第十甫路20号"

    def test_empty_list(self):
        assert parse_amap_jsonld('{"@type": "ItemList", "itemListElement": []}') == []


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestAmapCollector:
    def test_fetch_uses_ranking_url(self):
        seen = {}

        def opener(req):
            seen["url"] = req.full_url
            return FakeResponse(FIXTURE.read_text(encoding="utf-8"))

        collector = AmapCollector(opener=opener)
        items = collector.fetch("guangzhou", "440106")
        assert "amap.com/ranking/guangzhou/food/440106" in seen["url"]
        assert len(items) == 10
        assert items[0]["source"] == "https://www.amap.com/ranking/guangzhou/food/440106"

    def test_network_error_raises(self):
        def opener(req):
            raise OSError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            AmapCollector(opener=opener).fetch("guangzhou", "440106")


class TestImportListRecords:
    def test_imports_with_address_and_provenance(self, tmp_path):
        db = Database(tmp_path / "db.json").load()
        entries = [
            {"name": "SKY NO.1空中一号", "city": "广州", "district": "天河区",
             "address": "广州市天河区珠江东路6号", "source": "https://www.amap.com/ranking/guangzhou/food/440106",
             "list_name": "2025高德状元榜·美食"},
            {"name": "炳胜品味(珠江新城旗舰店)", "city": "广州", "district": "天河区",
             "source": "https://www.amap.com/ranking/guangzhou/food/440106",
             "list_name": "2025高德状元榜·美食"},
        ]
        summary = import_list_records(entries, db)
        assert summary["imported"] == 2
        r = db.restaurants[0]
        assert r.address == "广州市天河区珠江东路6号"
        assert r.metrics.online_rating is None
        assert "高德状元榜" in r.notes
        assert any("amap.com" in s for s in r.sources)

    def test_dedupes_by_branch_name(self, tmp_path):
        db = Database(tmp_path / "db.json").load()
        entries = [
            {"name": "同福轩（天河店）", "city": "广州", "source": "https://a.example.com", "list_name": "L"},
            {"name": "同福轩（天河店）", "city": "广州", "source": "https://a.example.com", "list_name": "L"},
        ]
        summary = import_list_records(entries, db)
        assert summary["imported"] == 1
        assert summary["skipped_existing"] == 1

    def test_entry_without_name_skipped(self, tmp_path):
        db = Database(tmp_path / "db.json").load()
        summary = import_list_records([{"city": "广州", "source": "https://a.example.com", "list_name": "L"}], db)
        assert summary["imported"] == 0
        assert summary["failed"] == 1
