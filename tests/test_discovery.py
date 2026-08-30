"""名录文章店名提取测试。"""
from hhrating.discovery import extract_restaurant_names, looks_like_city_page


class TestExtractNames:
    def test_basic_list_article(self):
        text = """
        深圳必吃餐厅推荐：
        1. 润园四季椰子鸡（福田店）
        2. 八合里牛肉火锅
        3. 胜记渔港 酒家
        推荐几家甜品店：满记甜品、杨小怪糖水铺。
        这家公司的业务不错。欢迎大家前来品尝美食。
        """
        names = extract_restaurant_names(text, city="深圳")
        assert "润园四季椰子鸡（福田店）" in names
        assert "八合里牛肉火锅" in names
        assert "满记甜品" in names
        # 公司/无关短语不应入选
        assert not any("公司" in n for n in names)
        assert not any("欢迎" in n for n in names)

    def test_dedupes_and_limits_length(self):
        text = "甲餐厅、甲餐厅、乙酒家、" + "超长名称" * 30 + "餐厅"
        names = extract_restaurant_names(text, city="深圳")
        assert names.count("甲餐厅") == 1
        assert not any(len(n) > 20 for n in names)

    def test_branch_suffix_captured(self):
        text = "推荐：润园四季椰子鸡（福田店）、胜记渔港 酒家"
        names = extract_restaurant_names(text, city="深圳")
        assert "润园四季椰子鸡（福田店）" in names
        assert "胜记渔港" in names

    def test_html_stripped(self):
        text = "<p><strong>孖记士多</strong>（老字号大排档）</p><p>表哥茶餐厅</p>"
        names = extract_restaurant_names(text, city="广州")
        assert "孖记士多" in names
        assert "表哥茶餐厅" in names


class TestCityGuard:
    def test_looks_like_city_page(self):
        assert looks_like_city_page("深圳必吃餐厅名单 椰子鸡 火锅", "深圳") is True
        assert looks_like_city_page("北京烤鸭大全", "深圳") is False
