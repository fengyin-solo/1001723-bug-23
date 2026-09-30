"""数据仓库：内存表 + JSON 文件落盘，保证保存后刷新、重启仍是同一份数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
首次启动以示例数据初始化并写入数据文件；之后每次增改都原子落盘，避免只改内存拷贝。
"""
from __future__ import annotations

import json
import os
import tempfile
from threading import RLock
from typing import Any

from app.seed import SEED_ROWS

DATA_FILE = os.environ.get("APP_DATA_FILE", os.path.join(os.getcwd(), "data", "store.json"))


class Store:
    def __init__(self) -> None:
        self._lock = RLock()
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._tables = self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self) -> dict[str, list[dict[str, Any]]]:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    tables = {
                        name: [dict(row) for row in rows]
                        for name, rows in payload.items()
                        if isinstance(rows, list)
                    }
                    if tables:
                        return tables
            except (json.JSONDecodeError, OSError, ValueError):
                # 数据文件损坏时退回示例数据，宁可重来也不能让服务起不来
                pass
        tables = {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}
        self._flush(tables)
        return tables

    def _flush(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        directory = os.path.dirname(DATA_FILE)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # 先写临时文件再原子替换，避免写到一半进程退出导致历史数据丢失
        fd, tmp_path = tempfile.mkstemp(prefix=".store-", suffix=".json", dir=directory or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(tables, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DATA_FILE)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def persist(self) -> None:
        """把当前内存表整体落盘。"""
        self._ensure_loaded()
        with self._lock:
            self._flush(self._tables)

    def module_names(self) -> list[str]:
        self._ensure_loaded()
        with self._lock:
            return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        self._ensure_loaded()
        with self._lock:
            for row in self.rows(module):
                if int(row.get("id", 0)) == entry_id:
                    return row
        return None

    def overview(self) -> dict[str, object]:
        self._ensure_loaded()
        with self._lock:
            modules: list[dict[str, object]] = []
            for name in self.module_names():
                rows = self.rows(name)
                modules.append({
                    "name": name,
                    "created": len(rows),
                    "pending": sum(1 for row in rows if row.get("pending")),
                    "abnormal": sum(1 for row in rows if row.get("abnormal")),
                })
            cards = [
                {"label": "业务模块", "value": len(modules)},
                {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
                {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
                {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
            ]
            return {"cards": cards, "modules": modules}


store = Store()
