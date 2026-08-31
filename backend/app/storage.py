"""工件/文件落盘：workspaces/{project}/{run_id}/... 统一管理。"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import settings, workspace_for


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name).strip("_") or "file"


def save_upload(project: str, run_id: str | int, filename: str, data: bytes, subdir: str = "raw") -> Path:
    """保存上传文件到工作区，返回落盘路径。带扩展名白名单与大小限制。"""
    ext = Path(filename).suffix.lower()
    if ext not in settings().ALLOWED_UPLOAD_EXT:
        raise ValueError(f"不支持的文件类型: {ext}，允许: {sorted(settings().ALLOWED_UPLOAD_EXT)}")
    if len(data) > settings().UPLOAD_MAX_MB * 1024 * 1024:
        raise ValueError(f"文件超过 {settings().UPLOAD_MAX_MB}MB 限制")
    ws = workspace_for(project, run_id) / subdir
    ws.mkdir(parents=True, exist_ok=True)
    path = ws / f"{uuid.uuid4().hex[:8]}_{_safe_name(filename)}"
    path.write_bytes(data)
    return path


def save_text(project: str, run_id: str | int, name: str, text: str, subdir: str = "raw") -> Path:
    ws = workspace_for(project, run_id) / subdir
    ws.mkdir(parents=True, exist_ok=True)
    path = ws / _safe_name(name)
    path.write_text(text, encoding="utf-8")
    return path


def append_log(project: str, run_id: str | int, name: str, lines: str) -> Path:
    """追加写运行日志：workspaces/{project}/{run_id}/logs/{name}.log。

    人类可读、追加式（保留历史轮次），供生成用例/自动化生成/执行失败排查。
    """
    ws = workspace_for(project, run_id) / "logs"
    ws.mkdir(parents=True, exist_ok=True)
    path = ws / (_safe_name(name) + ".log")
    with path.open("a", encoding="utf-8") as f:
        f.write(lines)
    return path


def ensure_abs(path: str | Path) -> str:
    p = Path(path)
    return str(p.resolve())
