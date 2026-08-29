"""JSON 文件存储层。

数据库文件形如 {"schema_version": 1, "restaurants": [...]}，
写入时保持中文可读（ensure_ascii=False）、字段顺序稳定。
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Restaurant

SCHEMA_VERSION = 1


class Database:
    """基于单个 JSON 文件的文档库。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._restaurants: list[Restaurant] = []

    # ------------------------------------------------------------------ load
    def load(self) -> "Database":
        if not self.path.exists():
            self._restaurants: list[Restaurant] = []
            return self
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"数据库文件不是合法 JSON：{self.path}（{exc}）") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"数据库 schema_version 不受支持：期望 {SCHEMA_VERSION}，"
                f"得到 {raw.get('schema_version') if isinstance(raw, dict) else '无'}"
            )
        self._restaurants = [Restaurant.from_dict(item) for item in raw.get("restaurants", [])]
        return self

    # ------------------------------------------------------------------ save
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "restaurants": [r.to_dict() for r in self._restaurants],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------- mutations
    def upsert(self, restaurant: Restaurant) -> None:
        for i, existing in enumerate(self._restaurants):
            if existing.id == restaurant.id:
                self._restaurants[i] = restaurant
                self.save()
                return
        self._restaurants.append(restaurant)
        self.save()

    def remove(self, restaurant_id: str) -> bool:
        before = len(self._restaurants)
        self._restaurants = [r for r in self._restaurants if r.id != restaurant_id]
        if len(self._restaurants) < before:
            self.save()
            return True
        return False

    # ----------------------------------------------------------------- query
    @property
    def restaurants(self) -> list[Restaurant]:
        """当前内存中的全部记录（未排序，按插入/文件顺序）。"""
        return list(self._restaurants)

    def get(self, restaurant_id: str) -> Restaurant | None:
        return next((r for r in self._restaurants if r.id == restaurant_id), None)

    def list_all(self) -> list[Restaurant]:
        # 以 id 排序保证确定性（中文按拼音排序需额外依赖，暂不引入）。
        return sorted(self._restaurants, key=lambda r: r.id)

    def __len__(self) -> int:
        return len(self._restaurants)
