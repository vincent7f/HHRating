"""五位指数评分引擎。

规则的唯一权威依据是 docs/index-spec.md（v1.0）；本模块将其代码化。
指数形如 "89589"：综合 / 名人推荐 / 人气 / 网上得分 / 年代，每位 1-9（0 = 暂无数据）。
"""
from __future__ import annotations

import math
import warnings
from collections import OrderedDict

from . import SPEC_VERSION
from .models import Metrics

WEIGHTS = OrderedDict(
    (
        ("online", 0.35),
        ("popularity", 0.25),
        ("celebrity", 0.20),
        ("age", 0.20),
    )
)

AWARD_POINTS = {
    "michelin_3_star": 8,
    "michelin_2_star": 6,
    "michelin_1_star": 4,
    "bib_gourmand": 2,
    "michelin_plate": 1,
    "blackpearl_3_diamond": 6,
    "blackpearl_2_diamond": 4,
    "blackpearl_1_diamond": 2,
}

_CELEBRITY_EMPTY = (None, None, None, None)


def round_half_up(value: float) -> int:
    """四舍五入（.5 进位）；Python 内建 round 为银行家舍入，不适用。"""
    return int(math.floor(value + 0.5))


def _clamp(value: int, lo: int = 1, hi: int = 9) -> int:
    return max(lo, min(hi, value))


def online_digit(rating: float | None) -> int:
    """第 4 位：网上得分。区间左闭右开，最高档闭区间（见规范 §2）。"""
    if rating is None:
        return 0
    if rating >= 4.8:
        return 9
    if rating >= 4.6:
        return 8
    if rating >= 4.4:
        return 7
    if rating >= 4.2:
        return 6
    if rating >= 4.0:
        return 5
    if rating >= 3.7:
        return 4
    if rating >= 3.4:
        return 3
    if rating >= 3.0:
        return 2
    return 1


def popularity_digit(review_count: int | None, social_mentions: int | None = None) -> int:
    """第 3 位：人气度 = 点评数分桶（规范 §3.1）+ 社媒修正（§3.2）。"""
    if review_count is None:
        return 0
    buckets = (500, 2000, 5000, 10000, 30000, 60000, 100000, 300000)
    digit = 9
    for i, upper in enumerate(buckets):
        if review_count < upper:
            digit = i + 1
            break
    if social_mentions is not None:
        if social_mentions >= 1_000_000:
            digit += 2
        elif social_mentions >= 100_000:
            digit += 1
    return _clamp(digit)


def celebrity_digit(
    awards: list[str] | None = None,
    endorsements: list[str] | None = None,
    media: list[str] | None = None,
    master_chef: bool | None = None,
) -> int:
    """第 2 位：名人推荐值，加分点数制（规范 §4）。"""
    if (awards, endorsements, media, master_chef) == _CELEBRITY_EMPTY:
        return 0
    award_points = max(
        (AWARD_POINTS[a.split("@", 1)[0].strip()] for a in awards or [] if a.split("@", 1)[0].strip() in AWARD_POINTS),
        default=0,
    )
    points = award_points
    points += min(len(endorsements or []), 3)
    points += min(len(media or []), 2)
    if master_chef:
        points += 2
    return min(9, points + 1)


def age_digit(founded_year: int | None, reference_year: int) -> int:
    """第 5 位：出现时间（规范 §5）。"""
    if founded_year is None:
        return 0
    age = reference_year - founded_year
    if age < 0:
        warnings.warn(f"founded_year({founded_year}) 晚于快照年份({reference_year})，按 1 分处理")
        return 1
    if age < 5:
        return 1
    if age < 10:
        return 2
    if age < 20:
        return 3
    if age < 35:
        return 4
    if age < 50:
        return 5
    if age < 70:
        return 6
    if age < 90:
        return 7
    if age < 120:
        return 8
    return 9


def overall_digit(digits: dict[str, int | None]) -> int:
    """第 1 位：综合得分，缺失维度权重归一化（规范 §6）。数字 0 视为缺失。"""
    available = [(d, WEIGHTS[name]) for name, d in digits.items() if d]
    if not available:
        return 0
    weighted = sum(d * w for d, w in available)
    weight_sum = sum(w for _, w in available)
    return _clamp(round_half_up(weighted / weight_sum))


def compute_index(metrics: Metrics, data_date: str) -> tuple[str, OrderedDict]:
    """计算 5 位指数，返回 (指数字符串, 逐位明细)。

    明细键序与指数位序一致：overall / celebrity / popularity / online / age。
    """
    reference_year = int(data_date[:4])
    online = online_digit(metrics.online_rating)
    popularity = popularity_digit(metrics.review_count, metrics.social_mentions)
    celebrity = celebrity_digit(
        awards=metrics.awards,
        endorsements=metrics.celebrity_endorsements,
        media=metrics.media_features,
        master_chef=metrics.master_chef,
    )
    age = age_digit(metrics.founded_year, reference_year)
    overall = overall_digit(
        {"online": online, "popularity": popularity, "celebrity": celebrity, "age": age}
    )
    detail = OrderedDict(
        (
            ("overall", overall),
            ("celebrity", celebrity),
            ("popularity", popularity),
            ("online", online),
            ("age", age),
        )
    )
    index = "".join(str(detail[k]) for k in ("overall", "celebrity", "popularity", "online", "age"))
    return index, detail


__all__ = [
    "SPEC_VERSION",
    "AWARD_POINTS",
    "WEIGHTS",
    "age_digit",
    "celebrity_digit",
    "compute_index",
    "online_digit",
    "overall_digit",
    "popularity_digit",
    "round_half_up",
]
