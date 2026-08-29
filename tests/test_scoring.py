"""五位指数评分引擎测试（规则依据 docs/index-spec.md v1.0）。"""
import pytest

from hhrating.models import Metrics
from hhrating.scoring import (
    age_digit,
    celebrity_digit,
    compute_index,
    online_digit,
    overall_digit,
    popularity_digit,
    round_half_up,
)


class TestOnlineDigit:
    @pytest.mark.parametrize(
        "rating,expected",
        [
            (5.0, 9), (4.9, 9), (4.8, 9),
            (4.79, 8), (4.6, 8),
            (4.59, 7), (4.4, 7),
            (4.39, 6), (4.2, 6),
            (4.19, 5), (4.0, 5),
            (3.99, 4), (3.7, 4),
            (3.69, 3), (3.4, 3),
            (3.39, 2), (3.0, 2),
            (2.99, 1), (0.0, 1),
        ],
    )
    def test_thresholds(self, rating, expected):
        assert online_digit(rating) == expected

    def test_missing_is_zero(self):
        assert online_digit(None) == 0


class TestPopularityDigit:
    @pytest.mark.parametrize(
        "count,expected",
        [
            (0, 1), (499, 1),
            (500, 2), (1999, 2),
            (2000, 3), (4999, 3),
            (5000, 4), (9999, 4),
            (10000, 5), (29999, 5),
            (30000, 6), (59999, 6),
            (60000, 7), (99999, 7),
            (100000, 8), (299999, 8),
            (300000, 9), (1000000, 9),
        ],
    )
    def test_buckets(self, count, expected):
        assert popularity_digit(count) == expected

    def test_social_bonus_plus1(self):
        # 基础 5（1 万档）+ 社媒 10 万 → 6
        assert popularity_digit(10000, social_mentions=100000) == 6

    def test_social_bonus_plus2_capped_at_9(self):
        assert popularity_digit(60000, social_mentions=1000000) == 9
        assert popularity_digit(300000, social_mentions=1000000) == 9

    def test_social_below_thresholds_no_change(self):
        assert popularity_digit(10000, social_mentions=99999) == 5

    def test_missing_review_count_is_zero_even_with_social(self):
        assert popularity_digit(None) == 0
        assert popularity_digit(None, social_mentions=500000) == 0


class TestCelebrityDigit:
    def test_fields_present_but_no_signal_is_one(self):
        assert celebrity_digit(awards=[], endorsements=[], media=[], master_chef=False) == 1

    def test_all_fields_missing_is_zero(self):
        assert celebrity_digit(awards=None, endorsements=None, media=None, master_chef=None) == 0

    @pytest.mark.parametrize(
        "award,expected",
        [
            ("michelin_3_star", 9),   # 8 分
            ("michelin_2_star", 7),   # 6 分
            ("michelin_1_star", 5),   # 4 分
            ("bib_gourmand", 3),      # 2 分
            ("michelin_plate", 2),    # 1 分
            ("blackpearl_3_diamond", 7),
            ("blackpearl_2_diamond", 5),
            ("blackpearl_1_diamond", 3),
        ],
    )
    def test_awards(self, award, expected):
        assert celebrity_digit(awards=[award]) == expected

    def test_award_with_year_suffix(self):
        assert celebrity_digit(awards=["michelin_1_star@2025"]) == 5

    def test_awards_take_highest_not_stack(self):
        # 米其林一星(4) + 黑珍珠一钻(2) → 取最高 4 分，不叠加
        assert celebrity_digit(awards=["michelin_1_star", "blackpearl_1_diamond"]) == 5

    def test_unknown_award_ignored(self):
        assert celebrity_digit(awards=["made_up_award"]) == 1

    def test_endorsements_capped_at_three_points(self):
        assert celebrity_digit(endorsements=["甲"]) == 2
        assert celebrity_digit(endorsements=["甲", "乙", "丙"]) == 4
        assert celebrity_digit(endorsements=["甲", "乙", "丙", "丁", "戊"]) == 4

    def test_media_capped_at_two_points(self):
        assert celebrity_digit(media=["舌尖上的中国"]) == 2
        assert celebrity_digit(media=["a", "b", "c"]) == 3

    def test_master_chef_two_points(self):
        assert celebrity_digit(master_chef=True) == 3

    def test_combination(self):
        # 一星(4) + 大师(2) + 两位名人(2) = 8 分 → 9
        assert (
            celebrity_digit(
                awards=["michelin_1_star"],
                endorsements=["甲", "乙"],
                media=[],
                master_chef=True,
            )
            == 9
        )


class TestAgeDigit:
    @pytest.mark.parametrize(
        "founded,expected",
        [
            (2024, 1), (2022, 1),          # [0,5)
            (2021, 2), (2017, 2),          # [5,10)
            (2016, 3), (2011, 3),          # [10,20)
            (2006, 4), (1992, 4),          # [20,35)
            (1991, 5), (1977, 5),          # [35,50)
            (1976, 6), (1957, 6),          # [50,70)
            (1956, 7), (1937, 7),          # [70,90)
            (1936, 8), (1907, 8),          # [90,120)
            (1906, 9), (1864, 9), (1416, 9),  # ≥120
        ],
    )
    def test_buckets_reference_2026(self, founded, expected):
        assert age_digit(founded, reference_year=2026) == expected

    def test_new_store_under_five_years(self):
        assert age_digit(2024, reference_year=2026) == 1

    def test_future_year_scores_one(self):
        assert age_digit(2030, reference_year=2026) == 1

    def test_missing_is_zero(self):
        assert age_digit(None, reference_year=2026) == 0


class TestOverallDigit:
    def test_all_nine_is_nine(self):
        assert overall_digit({"online": 9, "popularity": 9, "celebrity": 9, "age": 9}) == 9

    def test_weighted_example_from_spec(self):
        # 7*.35 + 5*.25 + 3*.20 + 9*.20 = 6.10 → 6
        assert overall_digit({"online": 7, "popularity": 5, "celebrity": 3, "age": 9}) == 6

    def test_missing_dimension_weight_renormalized(self):
        # 剔除 online 后：(8*.25 + 5*.20 + 4*.20) / (0.25+0.20+0.20) = 3.8/0.65 = 5.85 → 6
        assert overall_digit({"online": 0, "popularity": 8, "celebrity": 5, "age": 4}) == 6

    def test_all_missing_is_zero(self):
        assert overall_digit({"online": 0, "popularity": 0, "celebrity": 0, "age": 0}) == 0

    def test_single_dimension_insufficient_is_zero(self):
        # 规范 v1.1：可得维度不足两个 → 综合 0（防止单维度被归一化放大）
        assert overall_digit({"online": 0, "popularity": 0, "celebrity": 0, "age": 8}) == 0
        assert overall_digit({"online": 9, "popularity": 0, "celebrity": 0, "age": 0}) == 0

    def test_clamped_to_nine(self):
        assert overall_digit({"online": 9, "popularity": 9, "celebrity": 9, "age": 8}) == 9

    def test_round_half_up_not_bankers(self):
        assert round_half_up(6.5) == 7
        assert round_half_up(2.5) == 3
        assert round_half_up(6.4) == 6


class TestComputeIndex:
    def test_full_restaurant_index_string(self):
        metrics = Metrics(
            online_rating=4.9,       # online 9
            review_count=150000,     # popularity 8
            awards=["michelin_1_star"],  # celebrity 5
            founded_year=1864,       # age 9
        )
        index, detail = compute_index(metrics, data_date="2026-08-29")
        # overall = 9*.35 + 8*.25 + 5*.2 + 9*.2 = 3.15+2+1+1.8 = 7.95 → 8
        # 位序：综合8 名人5 人气8 网上9 年代9
        assert index == "85899"
        assert detail == {
            "overall": 8, "celebrity": 5, "popularity": 8, "online": 9, "age": 9,
        }

    def test_index_is_five_characters(self):
        index, _ = compute_index(Metrics(), data_date="2026-08-29")
        assert len(index) == 5
        assert index == "00000"

    def test_missing_dimensions_encoded_as_zero(self):
        metrics = Metrics(online_rating=4.5)  # 仅网上得分已调研 → 7
        index, detail = compute_index(metrics, data_date="2026-08-29")
        # 综合位仅一个维度可得 → 0（规范 v1.1）；位序：综合0 名人0 人气0 网上7 年代0
        assert index == "00070"
        assert index[3] == "7"
        assert detail == {"overall": 0, "celebrity": 0, "popularity": 0, "online": 7, "age": 0}

    def test_detail_uses_spec_key_order(self):
        _, detail = compute_index(
            Metrics(online_rating=4.0, review_count=8000, founded_year=1990),
            data_date="2026-08-29",
        )
        assert list(detail.keys()) == ["overall", "celebrity", "popularity", "online", "age"]
