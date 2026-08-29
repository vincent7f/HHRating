"""地址字段与地址提取测试。"""
import pytest

from hhrating.batch import guess_cuisine
from hhrating.collectors.websearch import extract_address
from hhrating.models import Restaurant
from hhrating.storage import Database


def make_restaurant(**overrides):
    from hhrating.models import Metrics

    payload = dict(
        id="taotaoju",
        name="陶陶居",
        city="广州",
        cuisine="粤菜",
        metrics=Metrics(founded_year=1880),
        sources=["https://example.com/a"],
        data_date="2026-08-29",
    )
    payload.update(overrides)
    return Restaurant(**payload)


class TestAddressModel:
    def test_address_roundtrip(self, tmp_path):
        db = Database(tmp_path / "db.json")
        r = make_restaurant(address="广州市荔湾区第十甫路20号")
        db.upsert(r)
        reloaded = Database(tmp_path / "db.json").load()
        assert reloaded.get("taotaoju").address == "广州市荔湾区第十甫路20号"

    def test_address_optional(self):
        assert make_restaurant().address is None


class TestExtractAddress:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("地址：广州市荔湾区第十甫路20号", "广州市荔湾区第十甫路20号"),
            ("位于佛山市顺德区大良街道清晖路150号，近清晖园", "佛山市顺德区大良街道清晖路150号"),
            ("深圳市南山区科苑南路2888号万象天地", "深圳市南山区科苑南路2888号万象天地"),
            ("陶陶居(第十甫路总店) 人均105元", None),
            ("评分4.5 环境4.2", None),
        ],
    )
    def test_patterns(self, text, expected):
        assert extract_address(text) == expected
