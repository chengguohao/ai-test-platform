"""FastAPI 入口：注册路由 + CORS + 静态资源（Allure 报告）。"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 允许直接执行本文件（PyCharm 右键 Run 'main' / python main.py）时也能找到 app 包：
# PyCharm 默认把脚本所在目录（backend/app/）加入 sys.path，而 app 包在 backend/ 下，
# 这里把 backend 目录补进 sys.path，保证 from app import ... 两种启动方式都可用。
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import models as _models  # noqa: F401  确保建表
from app.api import ai_gen, ai_models, artifacts, connectors, execution, folders, projects, workflow
from app.db import init_db

# 启动生命周期：建表（用新版 lifespan 替代已弃用的 on_event，消除 DeprecationWarning）
@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI 测试工作流平台", version="1.0.0", lifespan=lifespan)

# 本地开发：前端 Vite 默认 5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (projects.router, workflow.router, artifacts.router, connectors.router,
          ai_gen.router, ai_models.router, execution.router, folders.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "name": "AI 测试工作流平台"}


# 兜底异常日志：未处理异常落盘到 workspaces/backend_errors.log，便于排查 500
import traceback  # noqa: E402

_workspaces = Path(__file__).resolve().parents[2] / "workspaces"
_workspaces.mkdir(parents=True, exist_ok=True)
_ERROR_LOG = _workspaces / "backend_errors.log"


@app.exception_handler(Exception)
async def _unhandled_exc_handler(request: Request, exc: Exception):  # noqa: BLE001
    try:
        with _ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} "
                    f"{request.method} {request.url.path} =====\n")
            f.write(traceback.format_exc())
    except Exception:  # noqa: BLE001  日志本身失败不阻塞响应
        pass
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# Allure 报告静态托管：/reports/{project}/{run_id}/allure-report/
app.mount("/reports", StaticFiles(directory=str(_workspaces)), name="reports")


# PyCharm 直接右键运行入口：Run 'main' 即可启动后端（等价 uvicorn app.main:app）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
