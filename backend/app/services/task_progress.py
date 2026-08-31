"""长任务过程进度（内存版）：供前端轮询展示「思考过程」。

设计：
- 每个长任务（用例生成 / 自动化生成 / 执行测试 / AI 修复）用固定 key 标识，
  形如 "case_gen:{run_id}"，同 key 重复启动会重置。
- 过程步骤 append-only，线程安全（生成线程与 HTTP 轮询线程并发读写）。
- 纯内存，重启即清空——过程性数据，允许丢失；最终结果仍以 DB 工件/日志为准。
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
# {task_key: {"steps": [(ts, text), ...], "done": bool, "error": str}}
_tasks: dict[str, dict] = {}
_MAX_STEPS = 500  # 防御性上限，避免异常任务无限撑内存


def start(key: str) -> None:
    """任务开始：重置该 key 的步骤记录。"""
    with _lock:
        _tasks[key] = {"steps": [], "done": False, "error": ""}


def report(key: str, text: str) -> None:
    """任务内上报一步过程（时间戳自动附加）。"""
    with _lock:
        t = _tasks.get(key)
        if t is None:  # 未 start 就 report：自动建，容错
            t = _tasks[key] = {"steps": [], "done": False, "error": ""}
        if len(t["steps"]) < _MAX_STEPS:
            t["steps"].append((time.strftime("%H:%M:%S"), text))


def finish(key: str, error: str = "") -> None:
    """任务结束：标记 done，error 非空表示失败。"""
    with _lock:
        t = _tasks.get(key)
        if t is not None:
            t["done"] = True
            t["error"] = error


def get(key: str) -> dict:
    """读取进度（前端轮询用）。"""
    with _lock:
        t = _tasks.get(key)
        if t is None:
            return {"steps": [], "done": True, "error": "", "exists": False}
        return {
            "steps": [{"ts": ts, "text": txt} for ts, txt in t["steps"]],
            "done": t["done"],
            "error": t["error"],
            "exists": True,
        }
