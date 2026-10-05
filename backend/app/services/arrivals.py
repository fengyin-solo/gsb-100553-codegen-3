"""到货验收台账业务规则。

一个到货批次对应一条主记录；同一批次重复登记时，不新增主记录，只把第二次内容
追加到“补充记录”。状态必须按 待验收 -> 验收中 -> 已入库 -> 质保生效 流转，
已入库记录重新验收会先回到验收中并回退此前入库数量。
"""
from __future__ import annotations

import calendar
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.persistence import JsonArchive
from app.store import store

MODULE = "arrivals"
SPARE_MODULE = "spare_parts"
DATA_FILE = Path(
    os.getenv("ACCEPTANCE_DATA_FILE", Path(__file__).resolve().parents[1] / "data" / "acceptance.json")
)

STATUS_PENDING = "待验收"
STATUS_CHECKING = "验收中"
STATUS_STORED = "已入库"
STATUS_WARRANTY = "质保生效"
STATUS_ORDER = [STATUS_PENDING, STATUS_CHECKING, STATUS_STORED, STATUS_WARRANTY]

CONCLUSION_QUALIFIED = "合格"
CONCLUSION_PARTIAL = "部分合格"
CONCLUSION_UNQUALIFIED = "不合格"
CONCLUSIONS = [CONCLUSION_QUALIFIED, CONCLUSION_PARTIAL, CONCLUSION_UNQUALIFIED]

REQUIRED_REGISTER_FIELDS = ["到货批次", "送货日期", "备件编号", "备件名称", "到货数量"]
OPEN_RECORD_FIELDS = ["开箱人", "开箱日期", "包装检查", "外观检查", "资料附件"]
REQUIRED_ACCEPT_FIELDS = ["验收人", "验收日期", "验收结论"]

DEFAULT_WARRANTY_MONTHS = 12
ACTION_ALIASES = {
    "验收": "开始验收",
    "重新验收": "开始验收",
    "入库": "确认入库",
    "确认质保生效": "质保生效",
}


def add_months(source: date, months: int) -> date:
    """按自然月顺延质保期，到期日自动收敛到当月最后一天。"""
    month_index = source.month - 1 + months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(source.day, last_day))


def parse_date(value: Any, field_name: str) -> tuple[date | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, f"{field_name}不能为空"
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, f"{field_name}必须使用 YYYY-MM-DD 日期格式"


def parse_int(value: Any, field_name: str) -> tuple[int | None, str | None]:
    text = str(value if value is not None else "").strip()
    if not text:
        return None, f"{field_name}不能为空"
    try:
        number = int(text)
    except ValueError:
        return None, f"{field_name}必须是整数"
    if number <= 0:
        return None, f"{field_name}必须大于 0"
    return number, None


class ArrivalService:
    def __init__(self) -> None:
        self.archive = JsonArchive(DATA_FILE)
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        data = self.archive.load()
        if not data:
            data = self._build_legacy_data()
            self.archive.save(data)

        arrivals = store.rows(MODULE)
        arrivals.clear()
        arrivals.extend(data.get(MODULE, []))

        spare_rows = store.rows(SPARE_MODULE)
        spare_rows.clear()
        spare_rows.extend(data.get(SPARE_MODULE, []))
        self._loaded = True

    def _persist(self) -> None:
        self.archive.save({
            MODULE: store.rows(MODULE),
            SPARE_MODULE: store.rows(SPARE_MODULE),
        })

    def _build_legacy_data(self) -> dict[str, list[dict[str, Any]]]:
        """用存量送货单回填验收台账；已有判定不重新计算、不改结论。"""
        spare_rows = [dict(row) for row in store.rows(SPARE_MODULE)]
        next_id = max((int(row.get("id", 0)) for row in spare_rows), default=0) + 1

        inverter_part = {
            "id": next_id,
            "status": "存量充足",
            "pending": False,
            "abnormal": False,
            "备件编号": "SPAR-INV-01",
            "备件名称": "逆变器IGBT模块",
            "规格型号": "FF300R12KE3",
            "适用设备": "集中式逆变器",
            "安全存量": 2,
            "当前存量": 10,
            "存放位置": "备件库A-02",
            "备件状态": "存量充足",
            "待办事项": [],
        }
        fuse_part = {
            "id": next_id + 1,
            "status": "低于安全量",
            "pending": True,
            "abnormal": True,
            "备件编号": "SPAR-FUSE-02",
            "备件名称": "汇流箱熔断器",
            "规格型号": "DC1500V/20A",
            "适用设备": "汇流箱",
            "安全存量": 20,
            "当前存量": 0,
            "存放位置": "备件库B-01",
            "备件状态": "低于安全量",
            "待办事项": ["[DD-2026-002] 到货批次待验收"],
        }
        spare_rows.extend([inverter_part, fuse_part])

        arrivals = [
            {
                "id": 1,
                "status": STATUS_WARRANTY,
                "pending": False,
                "abnormal": False,
                "到货批次": "DD-2026-001",
                "送货单号": "SH-2026-0901-01",
                "送货日期": "2026-09-01",
                "供应商": "华能电气",
                "承运单位": "德邦物流",
                "备件编号": "SPAR-INV-01",
                "备件名称": "逆变器IGBT模块",
                "规格型号": "FF300R12KE3",
                "到货数量": 10,
                "合格数量": 10,
                "不合格数量": 0,
                "入库数量": 10,
                "开箱人": "周建",
                "开箱日期": "2026-09-01",
                "包装检查": "包装完好，防震标识齐全",
                "外观检查": "无磕碰、无受潮",
                "资料附件": "合格证、说明书、检测报告齐全",
                "验收人": "李晓峰",
                "验收日期": "2026-09-01",
                "验收结论": CONCLUSION_QUALIFIED,
                "问题说明": "",
                "入库经办人": "王敏",
                "入库日期": "2026-09-01",
                "质保期月数": 12,
                "质保起算日": "2026-09-01",
                "质保到期日": "2027-09-01",
                "补充记录": [],
            },
            {
                "id": 2,
                "status": STATUS_PENDING,
                "pending": True,
                "abnormal": False,
                "到货批次": "DD-2026-002",
                "送货单号": "SH-2026-0920-06",
                "送货日期": "2026-09-20",
                "供应商": "安瑞熔断器",
                "承运单位": "顺丰快运",
                "备件编号": "SPAR-FUSE-02",
                "备件名称": "汇流箱熔断器",
                "规格型号": "DC1500V/20A",
                "到货数量": 30,
                "合格数量": 0,
                "不合格数量": 0,
                "入库数量": 0,
                "开箱人": "",
                "开箱日期": "",
                "包装检查": "",
                "外观检查": "",
                "资料附件": "",
                "验收人": "",
                "验收日期": "",
                "验收结论": "",
                "问题说明": "",
                "入库经办人": "",
                "入库日期": "",
                "质保期月数": 12,
                "质保起算日": "",
                "质保到期日": "",
                "补充记录": [],
            },
        ]
        return {MODULE: arrivals, SPARE_MODULE: spare_rows}

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
            keyword = keyword.strip()
            rows = [
                row for row in rows
                if keyword in str(row.get("到货批次", ""))
                or keyword in str(row.get("备件编号", ""))
                or keyword in str(row.get("备件名称", ""))
                or keyword in str(row.get("送货单号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def _find_by_batch(self, batch_no: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("到货批次", "")).strip() == batch_no:
                return row
        return None

    def _find_spare(self, part_no: str) -> dict[str, Any] | None:
        for row in store.rows(SPARE_MODULE):
            if str(row.get("备件编号", "")).strip() == part_no:
                return row
        return None

    def _ensure_spare(self, values: dict[str, Any]) -> dict[str, Any]:
        part_no = str(values.get("备件编号") or "").strip()
        part = self._find_spare(part_no)
        if part is not None:
            return part
        rows = store.rows(SPARE_MODULE)
        part = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": "低于安全量",
            "pending": True,
            "abnormal": False,
            "备件编号": part_no,
            "备件名称": str(values.get("备件名称") or "").strip(),
            "规格型号": str(values.get("规格型号") or "").strip(),
            "适用设备": str(values.get("适用设备") or "").strip(),
            "安全存量": 0,
            "当前存量": 0,
            "存放位置": "",
            "备件状态": "待验收入库",
            "待办事项": [],
        }
        rows.append(part)
        return part

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        clean = {key: str(value).strip() for key, value in values.items() if value is not None}
        batch_no = clean.get("到货批次", "")
        duplicate = self._find_by_batch(batch_no) if batch_no else None
        if duplicate is not None:
            supplement = {
                "登记时间": datetime.now().isoformat(timespec="seconds"),
                **{key: value for key, value in clean.items() if key != "到货批次"},
            }
            duplicate.setdefault("补充记录", []).append(supplement)
            part_no = clean.get("备件编号", "")
            part = self._find_spare(part_no) if part_no else None
            if part is not None:
                todos = part.setdefault("待办事项", [])
                message = f"[{batch_no}] 收到补充登记，请核对送货单与实物"
                if message not in todos:
                    todos.append(message)
            self._persist()
            return duplicate, "同一到货批次已存在，本次登记已并入补充记录"

        missing = [field for field in REQUIRED_REGISTER_FIELDS if not clean.get(field)]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        delivery_date, error = parse_date(clean.get("送货日期"), "送货日期")
        if error:
            return None, error
        quantity, error = parse_int(clean.get("到货数量"), "到货数量")
        if error:
            return None, error
        warranty_months = DEFAULT_WARRANTY_MONTHS
        if clean.get("质保期月数"):
            warranty_months, error = parse_int(clean.get("质保期月数"), "质保期月数")
            if error:
                return None, error
        assert delivery_date is not None and quantity is not None and warranty_months is not None

        part = self._ensure_spare(clean)
        rows = store.rows(MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
            "到货批次": batch_no,
            "送货单号": clean.get("送货单号", ""),
            "送货日期": delivery_date.isoformat(),
            "供应商": clean.get("供应商", ""),
            "承运单位": clean.get("承运单位", ""),
            "备件编号": clean["备件编号"],
            "备件名称": clean["备件名称"],
            "规格型号": clean.get("规格型号", ""),
            "到货数量": quantity,
            "合格数量": 0,
            "不合格数量": 0,
            "入库数量": 0,
            "开箱人": "",
            "开箱日期": "",
            "包装检查": "",
            "外观检查": "",
            "资料附件": "",
            "验收人": "",
            "验收日期": "",
            "验收结论": "",
            "问题说明": "",
            "入库经办人": "",
            "入库日期": "",
            "质保期月数": warranty_months,
            "质保起算日": "",
            "质保到期日": "",
            "补充记录": [],
        }
        rows.append(entry)
        todos = part.setdefault("待办事项", [])
        message = f"[{batch_no}] 到货批次待验收"
        if message not in todos:
            todos.append(message)
        self._persist()
        return entry, "到货批次已登记，状态为待验收"

    def _missing_open_fields(self, entry: dict[str, Any]) -> list[str]:
        return [field for field in OPEN_RECORD_FIELDS if not str(entry.get(field) or "").strip()]

    def _replace_batch_todos(self, part: dict[str, Any], batch_no: str, message: str) -> None:
        todos = [item for item in part.setdefault("待办事项", []) if f"[{batch_no}]" not in str(item)]
        todos.append(message)
        part["待办事项"] = todos

    def _clear_batch_todos(self, part: dict[str, Any], batch_no: str) -> None:
        part["待办事项"] = [
            item for item in part.setdefault("待办事项", []) if f"[{batch_no}]" not in str(item)
        ]

    def _set_stock(self, part: dict[str, Any], delta: int) -> None:
        try:
            current = int(part.get("当前存量") or 0)
        except (TypeError, ValueError):
            current = 0
        part["当前存量"] = max(0, current + delta)

    def _refresh_spare_status(self, part: dict[str, Any]) -> None:
        try:
            current = int(part.get("当前存量") or 0)
            safe = int(part.get("安全存量") or 0)
        except (TypeError, ValueError):
            current, safe = 0, 0
        low = current < safe
        part["status"] = "低于安全量" if low else "存量充足"
        part["备件状态"] = part["status"]
        part["pending"] = low
        part["abnormal"] = low

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"到货批次 {entry_id} 不存在或已归档"

        clean = {key: str(value).strip() for key, value in values.items() if value is not None}
        action = ACTION_ALIASES.get(action, action)
        if action == "开始验收":
            return self._start_acceptance(entry)
        if action == "保存开箱记录":
            return self._save_open_record(entry, clean)
        if action == "提交验收结论":
            return self._submit_conclusion(entry, clean)
        if action == "确认入库":
            return self._confirm_storage(entry, clean)
        if action == "质保生效":
            return self._activate_warranty(entry, clean)
        return None, f"动作「{action}」不属于到货验收可执行范围"

    def _start_acceptance(
        self, entry: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        current = entry["status"]
        if current == STATUS_CHECKING:
            return entry, "该批次已在验收中"
        if current == STATUS_STORED:
            part = self._find_spare(str(entry.get("备件编号", "")))
            stored_quantity = int(entry.get("入库数量") or 0)
            if part is not None and stored_quantity:
                self._set_stock(part, -stored_quantity)
                self._replace_batch_todos(
                    part,
                    str(entry["到货批次"]),
                    f"[{entry['到货批次']}] 入库后重新验收，已回退入库数量 {stored_quantity} 件",
                )
                self._refresh_spare_status(part)
            entry["入库数量"] = 0
            entry["合格数量"] = 0
            entry["不合格数量"] = 0
            entry["验收结论"] = ""
            entry["验收人"] = ""
            entry["验收日期"] = ""
            entry["问题说明"] = ""
            entry["入库经办人"] = ""
            entry["入库日期"] = ""
            entry["质保起算日"] = ""
            entry["质保到期日"] = ""
            entry["status"] = STATUS_CHECKING
            entry["pending"] = True
            self._persist()
            return entry, "已退回验收中，原入库数量已回退"
        if current != STATUS_PENDING:
            return None, f"{current}状态不能重新开始验收"
        entry["status"] = STATUS_CHECKING
        entry["pending"] = True
        self._persist()
        return entry, "已进入验收中，请完善开箱与验收记录"

    def _save_open_record(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] not in {STATUS_PENDING, STATUS_CHECKING}:
            return None, f"{entry['status']}状态不能修改开箱记录"
        for field in OPEN_RECORD_FIELDS:
            if field in values:
                entry[field] = values[field]

        delivery_date = date.fromisoformat(str(entry["送货日期"]))
        open_text = str(entry.get("开箱日期") or "").strip()
        if open_text:
            open_date, error = parse_date(open_text, "开箱日期")
            if error:
                self._persist()
                return None, error
            assert open_date is not None
            if open_date < delivery_date:
                self._persist()
                return None, "开箱日期不能早于送货日期"

        missing = self._missing_open_fields(entry)
        if missing:
            entry["status"] = STATUS_CHECKING
            self._persist()
            return None, f"开箱记录未填完：{'、'.join(missing)}"
        entry["status"] = STATUS_CHECKING
        entry["pending"] = True
        self._persist()
        return entry, "开箱记录已保存"

    def _submit_conclusion(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != STATUS_CHECKING:
            return None, "只有验收中的批次可以提交验收结论"
        missing_open = self._missing_open_fields(entry)
        if missing_open:
            return None, f"开箱记录未填完，不能完成验收：{'、'.join(missing_open)}"

        for field in REQUIRED_ACCEPT_FIELDS:
            if values.get(field):
                entry[field] = values[field]
        missing = [field for field in REQUIRED_ACCEPT_FIELDS if not str(entry.get(field) or "").strip()]
        if missing:
            return None, f"缺少验收信息：{'、'.join(missing)}"

        accept_date, error = parse_date(entry.get("验收日期"), "验收日期")
        if error:
            return None, error
        open_date = date.fromisoformat(str(entry["开箱日期"]))
        assert accept_date is not None
        if accept_date < open_date:
            return None, "验收日期不能早于开箱日期"

        conclusion = str(entry["验收结论"]).strip()
        if conclusion not in CONCLUSIONS:
            return None, "验收结论只能是合格、部分合格或不合格"
        if values.get("问题说明") is not None:
            entry["问题说明"] = values.get("问题说明", "")

        arrival_quantity = int(entry["到货数量"])
        if conclusion == CONCLUSION_QUALIFIED:
            accepted = arrival_quantity
        elif conclusion == CONCLUSION_UNQUALIFIED:
            accepted = 0
            if not str(entry.get("问题说明") or "").strip():
                return None, "不合格批次必须填写问题说明，便于换货或索赔"
        else:
            accepted_value = values.get("合格数量", entry.get("合格数量"))
            accepted, error = parse_int(accepted_value, "合格数量")
            if error:
                return None, error
            assert accepted is not None
            if accepted >= arrival_quantity:
                return None, "部分合格时，合格数量必须小于到货数量"
            if not str(entry.get("问题说明") or "").strip():
                return None, "部分合格批次必须填写差异或问题说明"

        rejected = arrival_quantity - accepted
        entry["合格数量"] = accepted
        entry["不合格数量"] = rejected
        entry["入库数量"] = 0
        entry["abnormal"] = conclusion != CONCLUSION_QUALIFIED
        entry["pending"] = True

        part = self._find_spare(str(entry["备件编号"]))
        if part is not None:
            batch_no = str(entry["到货批次"])
            if conclusion == CONCLUSION_QUALIFIED:
                message = f"[{batch_no}] 验收合格，{accepted} 件待确认入库"
            elif conclusion == CONCLUSION_PARTIAL:
                message = f"[{batch_no}] 部分合格：{accepted} 件待入库，{rejected} 件待换货或索赔"
            else:
                message = f"[{batch_no}] 验收不合格，{rejected} 件待换货或索赔"
            self._replace_batch_todos(part, batch_no, message)
            part["abnormal"] = conclusion != CONCLUSION_QUALIFIED

        self._persist()
        return entry, f"验收结论已记录：{conclusion}"

    def _confirm_storage(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != STATUS_CHECKING:
            return None, "只有验收中的批次可以确认入库"
        missing_open = self._missing_open_fields(entry)
        if missing_open:
            return None, f"开箱记录未填完，不能入库：{'、'.join(missing_open)}"
        conclusion = str(entry.get("验收结论") or "").strip()
        if conclusion not in CONCLUSIONS:
            return None, "请先提交验收结论"
        try:
            accepted = int(entry.get("合格数量") or 0)
        except (TypeError, ValueError):
            return None, "合格数量不是有效整数，请重新提交验收结论"
        if accepted <= 0:
            return None, "合格数量为 0，不能办理入库"

        if values.get("入库日期"):
            entry["入库日期"] = values["入库日期"]
        if values.get("入库经办人"):
            entry["入库经办人"] = values["入库经办人"]
        if values.get("质保期月数"):
            entry["质保期月数"] = values["质保期月数"]
        if not str(entry.get("入库经办人") or "").strip():
            return None, "入库经办人不能为空"

        inbound_date, error = parse_date(entry.get("入库日期"), "入库日期")
        if error:
            return None, error
        delivery_date = date.fromisoformat(str(entry["送货日期"]))
        assert inbound_date is not None
        if inbound_date < delivery_date:
            return None, "入库日期不能早于送货日期"

        months, error = parse_int(entry.get("质保期月数") or DEFAULT_WARRANTY_MONTHS, "质保期月数")
        if error:
            return None, error
        assert months is not None

        part = self._find_spare(str(entry["备件编号"]))
        if part is None:
            return None, "对应备件不存在，无法更新入库数量"
        self._set_stock(part, accepted)
        self._clear_batch_todos(part, str(entry["到货批次"]))

        entry["入库数量"] = accepted
        entry["入库日期"] = inbound_date.isoformat()
        entry["质保期月数"] = months
        entry["质保起算日"] = inbound_date.isoformat()
        entry["质保到期日"] = add_months(inbound_date, months).isoformat()
        entry["status"] = STATUS_STORED
        entry["pending"] = False
        self._refresh_spare_status(part)
        self._persist()
        return entry, f"已入库 {accepted} 件，质保自实际入库日起算"

    def _activate_warranty(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != STATUS_STORED:
            return None, "只有已入库批次可以确认质保生效"
        if values.get("质保期月数"):
            months, error = parse_int(values["质保期月数"], "质保期月数")
            if error:
                return None, error
            assert months is not None
            entry["质保期月数"] = months
            inbound_date = date.fromisoformat(str(entry["入库日期"]))
            entry["质保到期日"] = add_months(inbound_date, months).isoformat()
        entry["status"] = STATUS_WARRANTY
        entry["pending"] = False
        self._persist()
        return entry, "质保已按实际入库日期生效"
