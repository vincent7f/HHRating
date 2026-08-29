"""数据模型：饭店记录与原始指标。

字段定义见 docs/data-dictionary.md；校验规则与文档一致。
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

VALID_AWARDS = {
    "michelin_3_star",
    "michelin_2_star",
    "michelin_1_star",
    "bib_gourmand",
    "michelin_plate",
    "blackpearl_3_diamond",
    "blackpearl_2_diamond",
    "blackpearl_1_diamond",
}


def _clean_award(award: str) -> str:
    """去掉年份后缀（michelin_1_star@2025 -> michelin_1_star）。"""
    return award.split("@", 1)[0].strip()


@dataclass
class Metrics:
    """原始指标（全部来自公开网络资料，可缺失）。

    列表字段为 None 表示"未调研"；显式空列表表示"已调研、无信号"。
    """

    online_rating: float | None = None
    review_count: int | None = None
    social_mentions: int | None = None
    awards: list[str] | None = None
    celebrity_endorsements: list[str] | None = None
    media_features: list[str] | None = None
    master_chef: bool | None = None  # None = 未调研；True/False = 已调研结果
    founded_year: int | None = None

    def __post_init__(self) -> None:
        if self.online_rating is not None and not (0 <= self.online_rating <= 5):
            raise ValueError(f"online_rating 必须在 0-5 之间，得到 {self.online_rating!r}")
        if self.review_count is not None and self.review_count < 0:
            raise ValueError(f"review_count 不能为负数，得到 {self.review_count!r}")
        if self.social_mentions is not None and self.social_mentions < 0:
            raise ValueError(f"social_mentions 不能为负数，得到 {self.social_mentions!r}")
        if self.founded_year is not None and not (1000 <= self.founded_year <= 2100):
            raise ValueError(f"founded_year 应为 1000-2100 的年份，得到 {self.founded_year!r}")
        for award in self.awards or []:
            if _clean_award(award) not in VALID_AWARDS:
                raise ValueError(f"未知奖项枚举：{award!r}，合法值见 docs/data-dictionary.md")

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Metrics:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Restaurant:
    """一家饭店的档案记录。"""

    id: str
    name: str
    city: str
    cuisine: str
    metrics: Metrics
    sources: list[str]
    data_date: str
    name_en: str | None = None
    branch: str | None = None
    index: str | None = None
    index_detail: dict[str, int] | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        missing = [f for f in ("id", "name", "city", "cuisine", "data_date") if not getattr(self, f)]
        if missing:
            raise ValueError(f"缺少必填字段：{', '.join(missing)}")
        if not self.sources:
            raise ValueError("sources 不能为空：每条记录至少附带 1 个数据来源 URL")
        if not is_dataclass(self.metrics):
            raise ValueError("metrics 必须是 Metrics 对象")

    def to_dict(self) -> dict[str, Any]:
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["metrics"] = self.metrics.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Restaurant:
        if not isinstance(data, dict):
            raise ValueError("饭店记录必须是 JSON 对象")
        known = {f.name for f in fields(cls)}
        required = ("id", "name", "city", "cuisine", "metrics", "sources", "data_date")
        absent = [f for f in required if f not in data or data[f] in (None, "")]
        if absent:
            raise ValueError(f"缺少必填字段：{', '.join(absent)}")
        kwargs = {k: v for k, v in data.items() if k in known}
        if "metrics" in kwargs and not isinstance(kwargs["metrics"], Metrics):
            kwargs["metrics"] = Metrics.from_dict(kwargs.pop("metrics") or {})
        return cls(**kwargs)
