"""润滑保养业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "lubricate"
REQUIRED_FIELDS = ["保养单号", "保养设备", "润滑点位"]
EDITABLE_FIELDS = ["保养单号", "保养设备", "润滑点位", "油品规格", "加注用量", "保养人员", "保养日期"]
STATUS_FIELD = "保养状态"
DONE_STATUS = "已完成"
STATUS_ORDER = ["待保养", "保养中", "已完成", "已延期"]
ACTION_RULES = {"安排保养": "保养中", "确认完成": "已完成", "标记延期": "已延期"}
NEGATIVE_ACTIONS = []


class LubricateService:
    def __init__(self) -> None:
        self._align_legacy_rows()

    def _align_legacy_rows(self) -> None:
        """历史记录的展示状态列曾写入占位文案，与内部 status 不是同一份。

        按记录当时的 status 口径把展示列对齐一次；油品规格、保养日期、润滑点位等
        历史取值一律原样保留，不做覆盖。
        """
        changed = False
        for row in store.rows(MODULE):
            status = str(row.get("status") or "")
            if status in STATUS_ORDER and row.get(STATUS_FIELD) != status:
                row[STATUS_FIELD] = status
                changed = True
        if changed:
            store.persist()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("保养单号", ""))]
        if status:
            rows = [row for row in rows if row.get(STATUS_FIELD) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.persist()
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, []
        # 先在合并副本上校验，校验不过不动内存里的原记录，更不落盘
        merged = dict(entry)
        for field in EDITABLE_FIELDS:
            if field in values and values.get(field) is not None:
                merged[field] = values.get(field)
        missing = [field for field in REQUIRED_FIELDS if not str(merged.get(field) or "").strip()]
        if missing:
            return None, missing
        entry.update({field: merged[field] for field in EDITABLE_FIELDS})
        store.persist()
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"保养记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于润滑保养可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        # 展示列与内部状态写同一份，页面、接口、首页统计口径一致
        entry[STATUS_FIELD] = target
        # 未完成 = 尚未完成的全部状态（待保养、保养中、已延期）；只有已完成才出未完成数
        entry["pending"] = target != DONE_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        store.persist()
        return entry, f"保养记录已{action}"
