"""大众点评 m 站"人气商户排行"页解析测试。"""
from pathlib import Path

from hhrating.dianping import parse_dianping_dishes, dianping_urls

FIXTURE = Path(__file__).parent / "fixtures" / "dianping_dishes.html"


class TestParseDianpingDishes:
    def test_extracts_shop_names_in_order(self):
        shops = parse_dianping_dishes(FIXTURE.read_text(encoding="utf-8"))
        # 夹具为截断切片，只含 5 家完整商户
        assert len(shops) == 5
        assert shops[0]["name"] == "文华老友记"
        assert shops[1]["name"] == "平步猪杂粥"

    def test_branch_merged(self):
        # 真实页面 branchName 位于 shopName 之前
        html = '{"shopinfo":{"shopId":"1","branchName":"天河店","shopName":"甲餐厅"}}'
        shops = parse_dianping_dishes(html)
        assert shops[0]["name"] == "甲餐厅（天河店）"

    def test_empty_page(self):
        assert parse_dianping_dishes("<html></html>") == []


class TestUrlExtraction:
    def test_extracts_dish_list_urls(self):
        text = (
            "看这里 https://m.dianping.com/dishes/list/c3508d10191246 和 "
            "https://m.dianping.com/dishes/list/c10d10086370?notitlebar=1 以及"
            "https://www.dianping.com/shop/123 无关"
        )
        urls = dianping_urls(text)
        assert urls == [
            "https://m.dianping.com/dishes/list/c3508d10191246",
            "https://m.dianping.com/dishes/list/c10d10086370",
        ]
