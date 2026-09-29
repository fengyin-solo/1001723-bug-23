"""润滑保养业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "lubricate"
REQUIRED_FIELDS = ["保养单号", "保养设备", "润滑点位"]
# 允许在保养记录上直接编辑的字段；保养单号、状态不允许在保存入口里改。
EDITABLE_FIELDS = ["保养设备", "润滑点位", "油品规格", "加注用量", "保养人员", "保养日期"]
DISPLAY_STATUS_FIELD = "保养状态"
DONE_STATUS = "已完成"
STATUS_ORDER = ["待保养", "保养中", "已完成", "已延期"]
ACTION_RULES = {"安排保养": "保养中", "确认完成": "已完成", "标记延期": "已延期"}
NEGATIVE_ACTIONS = []

TRUE_VALUES = {"1", "true", "yes", "on", "是"}


def _sync_status(entry: dict[str, Any]) -> None:
    """把同一条记录的内部 status、列表展示的保养状态、首页统计用的 pending 对齐。

    这三处必须是同一份口径：保养状态直接取 status；只有“已完成”不算未完成，
    “已延期”仍属于待处理。
    """
    status = str(entry.get("status") or STATUS_ORDER[0])
    entry["status"] = status
    entry[DISPLAY_STATUS_FIELD] = status
    entry["pending"] = status != DONE_STATUS


def reconcile(tables: dict[str, list[dict[str, Any]]]) -> None:
    """装载历史数据后的口径对齐：只修状态派生字段，业务字段一律保留当时取值。

    无论历史记录是哪个版本写盘的，status / 保养状态 / pending 一律按当前
    口径重算，保证刷新、重启后首页统计和列表条数始终对得上。
    """
    for row in tables.get(MODULE, []):
        if row.get("status") not in STATUS_ORDER:
            row["status"] = STATUS_ORDER[0]
        _sync_status(row)


# 进程启动、读到历史落库数据后先对齐一次：老记录的油品规格、保养日期等业务
# 字段原样保留，只把状态类字段收敛到当前口径，改动会被写回文件。
store.add_normalizer(reconcile)


class LubricateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("保养单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
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
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + EDITABLE_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["abnormal"] = False
        _sync_status(entry)
        rows.append(entry)
        store.commit()
        return entry, []

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """在权威记录本体上做部分更新，未提交的字段保持当时取值不变。

        油品规格、保养日期等以本次提交为准；没传的历史字段（含历史润滑点位
        的原始数据）原样保留。complete 为真时，保存与“确认完成”在同一笔里
        落库，避免页面状态先变、记录没保存的中间态。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"保养记录 {entry_id} 不存在或已归档"

        # 只取本次明确提交的字段：缺失的键保持当时取值，显式传空串才清空。
        changed: dict[str, Any] = {}
        for field in EDITABLE_FIELDS:
            if field not in values:
                continue
            value = values.get(field)
            changed[field] = value.strip() if isinstance(value, str) else value
        merged = {**entry, **changed}
        missing = [
            field
            for field in ("保养设备", "润滑点位")
            if not str(merged.get(field) or "").strip()
        ]
        if missing:
            return None, f"必填字段不能为空：{'、'.join(missing)}"

        entry.update(changed)
        completed = False
        raw_complete = values.get("complete")
        wants_complete = raw_complete is True or (
            isinstance(raw_complete, str) and raw_complete.strip().lower() in TRUE_VALUES
        )
        if wants_complete:
            completed = entry.get("status") != DONE_STATUS
            entry["status"] = DONE_STATUS
            entry["abnormal"] = False
        _sync_status(entry)
        store.commit()
        return entry, "保养记录已保存并确认完成" if completed else "保养记录已保存"

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
        if NEGATIVE_ACTIONS:
            entry["abnormal"] = action in NEGATIVE_ACTIONS
        _sync_status(entry)
        store.commit()
        return entry, f"保养记录已{action}"
