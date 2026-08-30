"""本地网页文本缓存：SQLite 存储、只保存解码后的正文、默认 7 天有效。

用于加速重复访问（fill/batch 重跑、多轮收割时同 URL 不再联网）。
`cached_opener` 把任意 opener 包装为带缓存的 opener，直接注入各采集器。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_TTL_DAYS = 7.0


class TextCache:
    def __init__(self, path: str | Path, ttl_days: float = DEFAULT_TTL_DAYS) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_days * 86400
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS pages ("
            "url TEXT PRIMARY KEY, fetched_at REAL NOT NULL, text TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, url: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT fetched_at, text FROM pages WHERE url = ?", (url,)
            ).fetchone()
            if row is None:
                return None
            fetched_at, text = row
            if time.time() - fetched_at > self.ttl_seconds:
                self._conn.execute("DELETE FROM pages WHERE url = ?", (url,))
                self._conn.commit()
                return None
            return text

    def put(self, url: str, text: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO pages (url, fetched_at, text) VALUES (?, ?, ?)",
                (url, time.time(), text),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def purge_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM pages WHERE fetched_at < ?", (time.time() - self.ttl_seconds,)
            )
            self._conn.commit()
            return cur.rowcount


class CachedResponse:
    """最小响应仿真：支持 with 语句与 read()，供采集器按原协议消费。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def __enter__(self) -> "CachedResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def cached_opener(cache: TextCache, inner_opener):
    """包装 opener：命中缓存直接返回；未命中抓取后写缓存。"""

    def opener(request, timeout: float = 20):
        url = request.full_url
        text = cache.get(url)
        if text is not None:
            return CachedResponse(text)
        with inner_opener(request, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        cache.put(url, text)
        return CachedResponse(text)

    return opener
