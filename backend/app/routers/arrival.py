"""到货验收台账接口。

一个到货批次一条主记录：到货登记、开箱记录、验收结论、确认入库、再验收。
列表与详情都指向 store 里同一份数据；验收结论同步到备件待办（/spare_parts/todos）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.arrival import ArrivalService

router = APIRouter(prefix="/api/arrival", tags=["到货验收"])

service = ArrivalService()

LIST_FIELDS = [
    "到货批号", "送货单号", "备件编号", "备件名称", "规格型号",
    "供应商", "送货数量", "送货日期", "入库数量", "入库日期",
    "质保起算日", "质保截止日",
]
STATUSES = ["待验收", "验收中", "已入库", "质保生效"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按到货批号、送货单号或备件编号检索"),
    status: str | None = Query(default=None, description="待验收、验收中、已入库、质保生效"),
    batch_no: str | None = Query(default=None, description="按到货批号精确过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """到货列表：与单条详情读同一份数据，只做过滤与分页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, batch_no=batch_no, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """单条到货批次详情（含开箱记录、验收结论、补充记录、流转记录）。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"到货批次 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def register_entry(payload: EntryPayload) -> ActionResult:
    """登记到货批次；同一批号重复登记只留最早一条，后一次并为补充记录。"""
    entry, message, created = service.register(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对批次执行状态动作：开箱记录、验收结论、确认入库、再验收、质保生效。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/supplements", response_model=ActionResult)
def add_supplement(entry_id: int, payload: EntryPayload) -> ActionResult:
    """往已登记批次追加一条补充说明（不改动主记录的判定与时间线）。"""
    content = str(payload.values.get("content") or "").strip()
    entry, message = service.add_supplement(entry_id, content)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export/all")
def export_entries() -> dict[str, Any]:
    """导出台账：返回全量到货批次，便于离线追责翻查。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "arrival", "total": total, "items": items}
