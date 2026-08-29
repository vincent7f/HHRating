"""采集器包：网络信号辅助收集（human-in-the-loop）。

`create_collector()` 返回多引擎回退采集器（DuckDuckGo → 必应），
首个返回非空结果的引擎胜出；单引擎报错自动尝试下一个。
"""
from __future__ import annotations

from typing import Protocol

from .bing import BingCollector
from .websearch import DuckDuckGoCollector


class Engine(Protocol):
    def search(self, query: str) -> list[dict[str, str]]: ...


class FallbackCollector:
    """按顺序尝试多个搜索引擎，取第一个非空结果。"""

    def __init__(self, engines: list[Engine]) -> None:
        self.engines = engines

    def search(self, query: str) -> list[dict[str, str]]:
        for engine in self.engines:
            try:
                results = engine.search(query)
            except Exception:  # 单引擎失败不影响整体
                continue
            if results:
                return results
        return []

    def collect_signals(self, query: str) -> dict:
        """检索并聚合信号：结果列表 + 评分候选 + 创立年份候选。"""
        from .websearch import extract_founded_year, extract_rating

        results = self.search(query)
        ratings: list[float] = []
        years: list[int] = []
        for r in results:
            text = f'{r["title"]} {r["snippet"]}'
            rating = extract_rating(text)
            if rating is not None and rating not in ratings:
                ratings.append(rating)
            year = extract_founded_year(text)
            if year is not None and year not in years:
                years.append(year)
        return {
            "results": results,
            "rating_candidates": ratings,
            "founded_year_candidates": years,
        }


def create_collector(proxy: str | None = None, engines: list[Engine] | None = None):
    if engines is not None:
        return FallbackCollector(engines)
    return FallbackCollector(
        [DuckDuckGoCollector(proxy=proxy), BingCollector(proxy=proxy)]
    )


__all__ = [
    "BingCollector",
    "DuckDuckGoCollector",
    "FallbackCollector",
    "create_collector",
]
