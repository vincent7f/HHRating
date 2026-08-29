"""采集器包：网络信号辅助收集（human-in-the-loop）。

`create_collector()` 返回多引擎回退采集器（DuckDuckGo → 必应），
首个返回非空结果的引擎胜出；单引擎报错自动尝试下一个。
"""
from __future__ import annotations

from typing import Protocol

from .bing import BingCollector
from .so360 import So360Collector
from .sogou import SogouCollector
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
        """检索并聚合信号：结果列表 + 评分/创立年份/点评数候选。"""
        from .websearch import extract_founded_year, extract_rating, extract_review_count

        results = self.search(query)
        ratings: list[float] = []
        years: list[int] = []
        counts: list[int] = []
        for r in results:
            text = f'{r["title"]} {r["snippet"]}'
            for extract, sink in (
                (extract_rating, ratings),
                (extract_founded_year, years),
                (extract_review_count, counts),
            ):
                value = extract(text)
                if value is not None and value not in sink:
                    sink.append(value)
        return {
            "results": results,
            "rating_candidates": ratings,
            "founded_year_candidates": years,
            "review_count_candidates": counts,
        }


def create_collector(proxy: str | None = None, engines: list[Engine] | None = None):
    if engines is not None:
        return FallbackCollector(engines)
    # 360/搜狗对中文多词查询最可靠（必应/DDG 在部分代理环境下会丢弃中文词项）
    return FallbackCollector(
        [
            So360Collector(proxy=proxy),
            SogouCollector(proxy=proxy),
            DuckDuckGoCollector(proxy=proxy),
            BingCollector(proxy=proxy),
        ]
    )


__all__ = [
    "BingCollector",
    "DuckDuckGoCollector",
    "FallbackCollector",
    "So360Collector",
    "SogouCollector",
    "create_collector",
]
