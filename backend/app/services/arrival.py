"""到货验收台账业务规则。

一个到货批次一条记录，状态沿「待验收 → 验收中 → 已入库 → 质保生效」流转：
- 开箱记录没填完不许跳级到已入库；
- 已入库（或质保生效）再点验收，必须退回验收中并回滚已入库存；
- 同一批次登记两次只留最早那条，后一次并成补充记录；
- 验收结论同步到备件待办，合格入库数量累加到备件当前存量；
- 质保自实际入库当日起算；存量批次按送货日期回填，沿用历史判定。
列表与详情都读 store 里同一份数据；每次写操作落 JSON 快照，刷新、重启后依旧。
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "arrival"
TODO_MODULE = "spare_part_todo"
SPARE_MODULE = "spare_parts"

STATUS_ORDER = ["待验收", "验收中", "已入库", "质保生效"]
REQUIRED_FIELDS = ["到货批号", "送货日期", "备件编号", "送货数量"]
UNBOXING_FIELDS = ["开箱人", "开箱日期", "外观检查", "附件核对"]

CONCLUSION_QUALIFIED = "合格"
CONCLUSION_REJECTED = "不合格"

# 一个状态下可执行的动作：已入库/质保生效可「再验收」退回验收中。
STATUS_ACTIONS: dict[str, list[str]] = {
    "待验收": ["填写开箱记录", "开始验收"],
    "验收中": ["填写开箱记录", "填写验收结论", "确认入库"],
    "已入库": ["再验收", "质保生效"],
    "质保生效": ["再验收"],
}


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def add_months(day: str, months: int) -> str:
    """质保截止日 = 质保起算日 + 质保月数（按自然月，落回当月最后一天）。"""
    try:
        start = date.fromisoformat(day)
    except (TypeError, ValueError):
        return ""
    month_index = (start.month - 1) + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day)).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


class ArrivalService:
    # ---------------- 读取：列表与详情同源 ----------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        batch_no: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("到货批号", ""))
                or keyword in str(row.get("送货单号", ""))
                or keyword in str(row.get("备件编号", ""))
            ]
        if batch_no:
            rows = [row for row in rows if str(row.get("到货批号", "")) == batch_no]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 最早登记的排前面，同批号补充记录也按这个顺序挂在主记录附近。
        rows.sort(key=lambda row: int(row.get("id", 0)))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def find_by_batch(self, batch_no: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("到货批号", "")).strip() == batch_no.strip():
                return row
        return None

    # ---------------- 到货登记：同批号去重，后者并为补充 ----------------
    def register(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """登记到货。返回 (记录, 说明, 是否为新建)。

        同一到货批号重复登记时不再新增主记录，而是把后一次提交并进已有批次的
        补充记录里，追责时最早那条始终是主记录。
        """
        batch_no = str(values.get("到货批号") or "").strip()
        delivery_day = str(values.get("送货日期") or "").strip()
        part_no = str(values.get("备件编号") or "").strip()
        quantity = _to_int(values.get("送货数量"))

        missing = [
            name
            for name, value in (
                ("到货批号", batch_no),
                ("送货日期", delivery_day),
                ("备件编号", part_no),
                ("送货数量", values.get("送货数量")),
            )
            if value in (None, "")
        ]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", False
        if quantity <= 0:
            return None, "送货数量必须为大于 0 的整数", False

        existing = self.find_by_batch(batch_no)
        if existing is not None:
            note = (
                f"重复登记（{_now()}）：送货单号 {str(values.get('送货单号') or '').strip() or '未填'}，"
                f"本次送货 {quantity} 件，接收人 {str(values.get('接收人') or '').strip() or '未填'}；"
                f"沿用最早登记的主记录，本条作为补充记录"
            )
            existing.setdefault("补充记录", []).append({"时间": _now(), "内容": note})
            existing["流转记录"].append({"时间": _now(), "动作": "重复登记并批", "说明": note})
            store.persist()
            return existing, f"批次 {batch_no} 已存在，本次登记已并入补充记录", False

        rows = store.rows(MODULE)
        entry = {
            "id": store.next_id(MODULE),
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
            "到货批号": batch_no,
            "送货单号": str(values.get("送货单号") or "").strip(),
            "备件编号": part_no,
            "备件名称": str(values.get("备件名称") or "").strip(),
            "规格型号": str(values.get("规格型号") or "").strip(),
            "供应商": str(values.get("供应商") or "").strip(),
            "承运方": str(values.get("承运方") or "").strip(),
            "接收人": str(values.get("接收人") or "").strip(),
            "送货数量": quantity,
            "送货日期": delivery_day,
            "质保月数": _to_int(values.get("质保月数"), 12) or 12,
            "存量批次": False,
            "开箱记录": {},
            "验收结论": {},
            "入库数量": 0,
            "入库日期": "",
            "质保起算日": "",
            "质保截止日": "",
            "补充记录": [],
            "流转记录": [{"时间": _now(), "动作": "到货登记", "说明": f"凭送货单登记到货 {quantity} 件"}],
            "关联待办": [],
        }
        rows.append(entry)
        todo_id = self._upsert_todo(entry, f"到货待验收：{quantity} 件" + (f"（送货单 {entry['送货单号']}）" if entry["送货单号"] else ""), "到货登记", "待处理")
        entry["关联待办"] = [todo_id]
        store.persist()
        return entry, f"到货批次 {batch_no} 已登记，状态为待验收", True

    def add_supplement(self, entry_id: int, content: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        content = content.strip()
        if not content:
            return None, "补充内容不能为空"
        entry.setdefault("补充记录", []).append({"时间": _now(), "内容": content})
        entry["流转记录"].append({"时间": _now(), "动作": "补充记录", "说明": content})
        store.persist()
        return entry, "补充记录已追加"

    # ---------------- 开箱记录：填完才能往已入库走 ----------------
    def save_unboxing(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        if entry["status"] not in ("待验收", "验收中"):
            return None, "开箱记录只能在待验收或验收中填写；已入库批次请先发起再验收"

        record = {
            "开箱人": str(values.get("开箱人") or "").strip(),
            "开箱日期": str(values.get("开箱日期") or "").strip(),
            "外观检查": str(values.get("外观检查") or "").strip(),
            "附件核对": str(values.get("附件核对") or "").strip(),
            "开箱备注": str(values.get("开箱备注") or "").strip(),
        }
        if record["外观检查"] not in ("", "完好", "破损", "受潮"):
            return None, "外观检查只支持：完好、破损、受潮"
        if record["附件核对"] not in ("", "一致", "短缺", "错发"):
            return None, "附件核对只支持：一致、短缺、错发"
        entry["开箱记录"] = record

        complete = self._unboxing_complete(entry)
        # 开箱记录任一项落字即视为开始验收；待验收 → 验收中，不允许停在中间直接入库。
        if complete:
            entry["status"] = "验收中"
            entry["abnormal"] = False
            entry["流转记录"].append({"时间": _now(), "动作": "开箱完成", "说明": "开箱记录填写完整，待补验收结论"})
        else:
            entry["status"] = "验收中"
            entry["abnormal"] = True
            entry["流转记录"].append({"时间": _now(), "动作": "开始验收", "说明": "开箱记录尚未填完"})
        self._upsert_todo(entry, self._todo_text(entry), "验收中", "待处理", abnormal=not complete)
        store.persist()
        if not complete:
            return entry, "开箱记录还没填完（开箱人、开箱日期、外观检查、附件核对均为必填），暂不能入库"
        return entry, "开箱记录已填完，可填写验收结论并确认入库"

    @staticmethod
    def _unboxing_complete(entry: dict[str, Any]) -> bool:
        record = entry.get("开箱记录") or {}
        return all(str(record.get(field) or "").strip() for field in UNBOXING_FIELDS)

    # ---------------- 验收结论 ----------------
    def save_conclusion(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        if entry["status"] != "验收中":
            return None, "只有验收中的批次可以填写验收结论"
        if not self._unboxing_complete(entry):
            return None, "开箱记录没填完，不能下验收结论"

        result = str(values.get("结论") or "").strip()
        if result not in (CONCLUSION_QUALIFIED, CONCLUSION_REJECTED):
            return None, "验收结论只支持：合格、不合格"

        delivered = _to_int(entry.get("送货数量"))
        qualified = _to_int(values.get("合格数量"), delivered)
        rejected = _to_int(values.get("不合格数量"))
        if result == CONCLUSION_QUALIFIED:
            if qualified <= 0 or qualified > delivered:
                return None, f"合格数量需在 1~{delivered} 之间"
            rejected = delivered - qualified
        else:
            qualified = 0
            if rejected <= 0 or rejected > delivered:
                rejected = delivered

        handling = str(values.get("处理方式") or "").strip()
        if result == CONCLUSION_REJECTED and not handling:
            return None, "不合格批次必须填写退货/换货/索赔等处理方式"

        conclusion = {
            "结论": result,
            "验收人": str(values.get("验收人") or "").strip(),
            "验收日期": str(values.get("验收日期") or "").strip() or _today(),
            "合格数量": qualified,
            "不合格数量": rejected,
            "处理方式": handling,
            "结论说明": str(values.get("结论说明") or "").strip(),
        }
        entry["验收结论"] = conclusion
        entry["abnormal"] = result == CONCLUSION_REJECTED
        action = "验收合格" if result == CONCLUSION_QUALIFIED else "验收不合格"
        entry["流转记录"].append(
            {
                "时间": _now(),
                "动作": action,
                "说明": f"合格 {qualified} 件 / 不合格 {rejected} 件" + (f"，{handling}" if handling else ""),
            }
        )
        self._upsert_todo(
            entry,
            f"验收结论已出（{result}）：合格 {qualified} 件 / 不合格 {rejected} 件，待入库",
            "验收中",
            "待处理",
            abnormal=result == CONCLUSION_REJECTED,
        )
        store.persist()
        return entry, f"验收结论已记录：{result}（合格 {qualified} / 不合格 {rejected}）"

    # ---------------- 确认入库：门槛 + 库存 + 质保起算 ----------------
    def confirm_stock_in(self, entry_id: int, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        if entry["status"] != "验收中":
            if entry["status"] == "待验收":
                return None, "批次还在待验收，请先填写开箱记录进入验收中"
            return None, "只有验收中的批次可以确认入库；已入库批次如需改动请先发起再验收"
        if not self._unboxing_complete(entry):
            return None, "开箱记录没填完，不许跳级到已入库"
        conclusion = entry.get("验收结论") or {}
        if not conclusion:
            return None, "尚未填写验收结论，不能入库"
        if conclusion.get("结论") != CONCLUSION_QUALIFIED:
            return None, "验收不合格的批次不能入库，请先走退货/换货/索赔处理"

        qualified = _to_int(conclusion.get("合格数量"))
        stock_qty = _to_int(values.get("入库数量"), qualified)
        if stock_qty <= 0 or stock_qty > qualified:
            return None, f"入库数量需在 1~{qualified} 之间（不能超过合格数量）"
        stock_day = str(values.get("入库日期") or "").strip() or _today()

        # 入库数量同步到备件当前存量（找到对应备件就累加，找不到也不阻断验收台账）。
        self._apply_spare_stock(entry["备件编号"], stock_qty)

        entry["入库数量"] = stock_qty
        entry["入库日期"] = stock_day
        # 质保期按实际入库那天起算，而不是送货日。
        entry["质保起算日"] = stock_day
        entry["质保截止日"] = add_months(stock_day, _to_int(entry.get("质保月数"), 12))
        entry["status"] = "已入库"
        entry["pending"] = False
        entry["abnormal"] = False
        entry["流转记录"].append(
            {
                "时间": _now(),
                "动作": "入库",
                "说明": f"合格 {stock_qty} 件入库，质保自 {stock_day} 起算至 {entry['质保截止日']}",
            }
        )
        self._upsert_todo(entry, f"到货验收合格并入库：{stock_qty} 件（质保 {entry['质保起算日']} 起）", "已入库", "已完成")
        store.persist()
        return entry, f"已入库 {stock_qty} 件，质保自 {stock_day} 起算"

    # ---------------- 再验收：已入库必须退回验收中 ----------------
    def reopen_for_inspection(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        if entry["status"] not in ("已入库", "质保生效"):
            return None, "只有已入库或质保生效的批次可以再验收"

        stocked = _to_int(entry.get("入库数量"))
        if stocked > 0:
            # 已加进备件存量的入库数量先回滚，等重新入库再按新数量加回。
            self._apply_spare_stock(entry["备件编号"], -stocked)

        previous = entry["status"]
        entry["status"] = "验收中"
        entry["pending"] = True
        entry["abnormal"] = False
        note = f"{previous}批次再验收，退回验收中；已回滚入库 {stocked} 件的存量"
        entry["流转记录"].append({"时间": _now(), "动作": "再验收", "说明": note})
        self._upsert_todo(entry, f"批次再验收：请重新核对结论与入库数量（原入库 {stocked} 件已回滚）", "验收中", "待处理")

        entry["入库数量"] = 0
        entry["入库日期"] = ""
        entry["质保起算日"] = ""
        entry["质保截止日"] = ""
        store.persist()
        return entry, note

    def activate_warranty(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"
        if entry["status"] != "已入库":
            return None, "只有已入库批次可以标记质保生效"
        entry["status"] = "质保生效"
        entry["流转记录"].append(
            {"时间": _now(), "动作": "质保生效", "说明": f"质保 {entry['质保起算日']} ~ {entry['质保截止日']}"}
        )
        store.persist()
        return entry, f"质保已生效（{entry['质保起算日']} ~ {entry['质保截止日']}）"

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        """路由层统一入口：按动作名分发到具体规则。"""
        values = values or {}
        if action in ("开始验收",):
            return self.save_unboxing(entry_id, values)
        if action in ("填写开箱记录", "开箱记录"):
            return self.save_unboxing(entry_id, values)
        if action in ("填写验收结论", "验收结论"):
            return self.save_conclusion(entry_id, values)
        if action == "确认入库":
            return self.confirm_stock_in(entry_id, values)
        if action == "再验收":
            return self.reopen_for_inspection(entry_id)
        if action == "质保生效":
            return self.activate_warranty(entry_id)
        return None, f"动作「{action}」不属于到货验收可执行范围"

    # ---------------- 备件存量联动 ----------------
    @staticmethod
    def _apply_spare_stock(part_no: str, delta: int) -> None:
        part = None
        for row in store.rows(SPARE_MODULE):
            if str(row.get("备件编号", "")).strip() == part_no:
                part = row
                break
        if part is None:
            return
        current = _to_int(part.get("当前存量"))
        current = max(0, current + delta)
        part["当前存量"] = current
        safety = _to_int(part.get("安全存量"))
        if current <= 0:
            part["status"] = "已用尽"
            part["备件状态"] = "已用尽"
        elif safety and current < safety:
            part["status"] = "低于安全量"
            part["备件状态"] = "低于安全量"
        else:
            part["status"] = "存量充足"
            part["备件状态"] = "存量充足"

    # ---------------- 备件待办联动 ----------------
    @staticmethod
    def _todo_text(entry: dict[str, Any]) -> str:
        if not ArrivalService._unboxing_complete(entry):
            return f"开箱记录未填完，验收结论待填写：{entry.get('送货数量')} 件"
        if not entry.get("验收结论"):
            return f"开箱完成，验收结论待填写：{entry.get('送货数量')} 件"
        conclusion = entry["验收结论"]
        return (
            f"验收结论已出（{conclusion.get('结论')}）："
            f"合格 {conclusion.get('合格数量')} 件 / 不合格 {conclusion.get('不合格数量')} 件，待入库"
        )

    def _upsert_todo(
        self,
        entry: dict[str, Any],
        text: str,
        stage: str,
        status: str,
        *,
        abnormal: bool = False,
    ) -> int:
        """每个到货批次在备件待办里只维护一条：随验收推进更新，不重复堆待办。"""
        todos = store.rows(TODO_MODULE)
        linked = [tid for tid in entry.get("关联待办", []) if store.find(TODO_MODULE, tid)]
        todo = store.find(TODO_MODULE, linked[0]) if linked else None
        is_done = status == "已完成"
        if todo is None:
            todo = {
                "id": store.next_id(TODO_MODULE),
                "pending": not is_done,
                "abnormal": abnormal,
                "备件编号": entry.get("备件编号", ""),
                "备件名称": entry.get("备件名称", ""),
                "到货批号": entry.get("到货批号", ""),
                "关联到货": entry.get("id"),
                "事项": text,
                "触发环节": stage,
                "状态": status,
                "到期日": "" if is_done else _today(),
                "创建时间": _now(),
                "完成时间": _now() if is_done else "",
            }
            todos.append(todo)
            entry.setdefault("关联待办", []).append(todo["id"])
        else:
            todo.update(
                {
                    "事项": text,
                    "触发环节": stage,
                    "状态": status,
                    "pending": not is_done,
                    "abnormal": abnormal,
                    "完成时间": _now() if is_done else "",
                    "到期日": "" if is_done else (todo.get("到期日") or _today()),
                }
            )
        return int(todo["id"])

    def list_todos(
        self,
        *,
        part_no: str | None = None,
        status: str | None = None,
        pending_only: bool = False,
    ) -> list[dict[str, Any]]:
        rows = list(store.rows(TODO_MODULE))
        if part_no:
            rows = [row for row in rows if str(row.get("备件编号", "")) == part_no]
        if status:
            rows = [row for row in rows if row.get("状态") == status]
        if pending_only:
            rows = [row for row in rows if row.get("pending")]
        rows.sort(key=lambda row: (bool(not row.get("pending")), int(row.get("id", 0))))
        return rows
