"""菜系批量分类测试（纯店名/备注推断，无需联网）。"""
from collections import Counter

from hhrating.batch import classify_all_cuisines, classify_cuisine_name
from hhrating.models import Metrics, Restaurant
from hhrating.storage import Database

class TestClassifyName:
    def test_cuisine_from_suffix(self):
        assert classify_cuisine_name("豆花牟火锅店") == "火锅"
        assert classify_cuisine_name("潮汕牛肉火锅") == "火锅"
        assert classify_cuisine_name("金戈戈豉油鸡") is None  # 无菜系线索

    def test_priority_longest_keyword(self):
        # "日本料理" 应优先于 "料理" 类短词
        assert classify_cuisine_name("樱日本料理") == "日本料理"

    def test_known_cuisines(self):
        assert classify_cuisine_name("萨莉亚意式餐厅") == "西餐"
        assert classify_cuisine_name("翠华茶餐厅") == "茶餐厅"
        assert classify_cuisine_name("泰好味泰国菜") == "泰国菜"
        assert classify_cuisine_name("韩式烤肉店") == "韩国料理"
        assert classify_cuisine_name("兰州牛肉面") == "西北菜"
        assert classify_cuisine_name("木屋烧烤") == "烧烤"
        assert classify_cuisine_name("润园四季椰子鸡") == "椰子鸡"
        assert classify_cuisine_name("西贝莜面村") == "西北菜"
        assert classify_cuisine_name("农耕记湖南土菜") == "湘菜"
        assert classify_cuisine_name("顺德双皮奶") == "甜品"
        assert classify_cuisine_name("海底捞") is None  # 知名品牌但无名中线索——不强判

    def test_none_for_generic(self):
        assert classify_cuisine_name("美味餐厅") is None
        assert classify_cuisine_name("食堂") is None

    def test_cuisine_from_notes(self):
        # 店名无线索，备注有线索
        assert classify_cuisine_name("金戈戈豉油鸡", "正宗潮汕牛肉火锅") == "火锅"

    def test_longest_keyword_across_name_and_notes(self):
        # notes 里的短词不能压过店名长词
        assert classify_cuisine_name("樱日本料理", "火锅自助") == "日本料理"


class TestClassifyAll:
    def _db(self, tmp_path, rows):
        db = Database(tmp_path / "db.json").load()
        for r in rows:
            db.upsert(r)
        return db

    def test_updates_pending_only(self, tmp_path):
        db = self._db(tmp_path, [
            Restaurant(id="a", name="豆花牟火锅店", city="广州", cuisine="待分类",
                       metrics=Metrics(), sources=["https://e.com/a"], data_date="2026-08-31"),
            Restaurant(id="b", name="陶陶居酒家", city="广州", cuisine="粤菜",
                       metrics=Metrics(), sources=["https://e.com/b"], data_date="2026-08-31"),
            Restaurant(id="c", name="美味餐厅", city="广州", cuisine="待分类",
                       metrics=Metrics(), sources=["https://e.com/c"], data_date="2026-08-31"),
            Restaurant(id="d", name="金戈戈", city="广州", cuisine="待分类",
                       metrics=Metrics(), sources=["https://e.com/d"], data_date="2026-08-31",
                       notes="正宗火锅"),
        ])
        counts = classify_all_cuisines(db)
        assert db.get("a").cuisine == "火锅"
        assert db.get("b").cuisine == "粤菜"          # 已分类不覆盖
        assert db.get("c").cuisine == "待分类"        # 无线索保持
        assert db.get("d").cuisine == "火锅"          # 来自 notes
        assert counts == Counter({"火锅": 2})
        reloaded = Database(tmp_path / "db.json").load()
        assert reloaded.get("a").cuisine == "火锅"
