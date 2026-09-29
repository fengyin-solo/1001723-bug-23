"""数据仓库：进程内提供可筛选、可流转的数据，所有变更同步落盘。

存储是一份按业务模块分表的 JSON 文件：首次启动时从示例数据播种并写盘，
之后每次增改都原子替换该文件。刷新页面、重启进程后读到的始终是同一份
数据，不会再出现“内存里的拷贝改了、缓存没落库”的情况。

模块可以注册一个装载后回调（normalize hook），用来把历史数据对齐到
当前口径；回调若改动了数据会被一并写回文件。
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.seed import SEED_ROWS

Normalizer = Callable[[dict[str, list[dict[str, Any]]]], None]


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables = self._load()
        self._normalizers: list[Normalizer] = []

    # ---- 装载与落库 -------------------------------------------------

    def add_normalizer(self, hook: Normalizer) -> None:
        """注册装载后的口径对齐回调，并立即对现有数据执行一次。"""
        with self._lock:
            self._normalizers.append(hook)
            snapshot = {name: [dict(row) for row in rows] for name, rows in self._tables.items()}
            hook(snapshot)
            if snapshot != self._tables:
                self._tables = snapshot
                self._persist_locked()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        path = settings.data_path
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return {
                        str(name): [dict(row) for row in rows if isinstance(row, dict)]
                        for name, rows in data.items()
                        if isinstance(rows, list)
                    }
            except (json.JSONDecodeError, OSError):
                # 落库文件损坏时退回示例数据，绝不让服务起不来。
                pass
        return {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    def _persist_locked(self) -> None:
        """把当前数据原子写回文件：先写临时文件再替换，防止写一半被读到。"""
        path = settings.data_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._tables, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)

    def commit(self) -> None:
        """业务层完成一次增改后调用：把这份权威数据落盘。"""
        with self._lock:
            self._persist_locked()

    # ---- 查询 -------------------------------------------------------

    def module_names(self) -> list[str]:
        with self._lock:
            return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        """返回模块表本体（不是拷贝）：业务层对行的修改就是对权威数据的修改。"""
        with self._lock:
            return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        with self._lock:
            for row in self.rows(module):
                if int(row.get("id", 0)) == entry_id:
                    return row
        return None

    def overview(self) -> dict[str, object]:
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
