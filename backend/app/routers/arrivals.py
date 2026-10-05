"""到货验收接口：登记到货批次、维护开箱验收记录并驱动状态流转。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.arrivals import ArrivalService

router = APIRouter(prefix="/api/arrivals", tags=["到货验收"])

service = ArrivalService()

LIST_FIELDS = [
    "到货批次", "送货单号", "送货日期", "备件编号", "备件名称", "规格型号",
    "到货数量", "合格数量", "入库数量", "验收结论", "入库日期",
    "质保起算日", "质保到期日",
]
STATUSES = ["待验收", "验收中", "已入库", "质保生效"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按到货批次、送货单或备件检索"),
    status: str | None = Query(default=None, description="待验收、验收中、已入库、质保生效"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """读取到货批次列表；列表与详情都来自同一份持久化台账。"""
    if size > 200:
        size = 200
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条到货批次完整明细。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"到货批次 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一个到货批次；重复批次只补充到最早记录，不新增台账行。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行验收流转动作；所有跳转与数量回退均由 service 统一校验。"""
    action = str(payload.values.pop("action", "") or "").strip()
    if not action:
        return ActionResult(ok=False, message="缺少 action 动作参数")
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
