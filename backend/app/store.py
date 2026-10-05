"""数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
为了让到货验收的数据在刷新、重启后依旧，数据会落一份 JSON 快照到
backend/data/store.json：首次启动用示例数据初始化，之后所有写操作都会持久化。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

from app.seed import SEED_ROWS

# backend/data/store.json：放在包外，避免随包发布；删掉这个文件即可回到示例数据。
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "store.json")

# 只作为其它模块联动存储、不单独算作业务模块的内部表。
INTERNAL_TABLES = {"spare_part_todo"}


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: dict[str, list[dict[str, Any]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """优先读持久化快照；文件缺失或损坏时回落到示例数据并立即落盘。"""
        if os.path.exists(_DATA_FILE):
            try:
                with open(_DATA_FILE, "r", encoding="utf-8") as handle:
                    snapshot = json.load(handle)
                tables = {
                    name: [dict(row) for row in rows]
                    for name, rows in snapshot.items()
                    if isinstance(rows, list)
                }
                # 快照里可能缺后来新增的模块，用示例数据补齐。
                for name, rows in SEED_ROWS.items():
                    tables.setdefault(name, [dict(row) for row in rows])
                return tables
            except (json.JSONDecodeError, OSError, ValueError):
                # 快照损坏时不阻断启动，回落到示例数据（下一次写入会覆盖坏文件）。
                pass
        return {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    def persist(self) -> None:
        """把当前全量数据原子写入 JSON 快照（先写临时文件再替换，避免半截文件）。"""
        os.makedirs(_DATA_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="store-", suffix=".json", dir=_DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._tables, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _DATA_FILE)
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def next_id(self, module: str) -> int:
        return max((int(row.get("id", 0)) for row in self.rows(module)), default=0) + 1

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            if name in INTERNAL_TABLES:
                # 备件待办是到货验收的联动表，不单独算作业务模块。
                continue
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
