"""到货验收使用的本地 JSON 持久化仓库。

项目其他模块仍使用内存示例数据；验收台账要求刷新和重启后仍能追溯，因此单独把
到货批次与受其影响的备件数量落盘。文件缺失时由 service 用存量数据初始化。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonArchive:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(tables, file, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
