"""全局配置（.env 驱动，见根目录 .env.example）。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]          # ai-test-platform/
load_dotenv(BASE_DIR / ".env")


@lru_cache
def settings():
    return _Settings()


class _Settings:
    """集中读取环境变量，全部带默认值，便于本地快速起。"""

    # ---- 基础 ----
    APP_NAME = os.getenv("APP_NAME", "AI 测试工作流平台")
    # 默认 SQLite（本地快速起）；生产切 MySQL：mysql+pymysql://user:pass@host:3306/db
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")
    WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(BASE_DIR / "workspaces")))
    UPLOAD_MAX_MB = int(os.getenv("UPLOAD_MAX_MB", "20"))
    ALLOWED_UPLOAD_EXT = {".md", ".docx", ".txt", ".yaml", ".yml", ".json", ".xmind", ".xlsx", ".csv"}
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret")

    # ---- 大模型 API（OpenAI 兼容）----
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
    LLM_PROXY = os.getenv("LLM_PROXY", "")  # 如 http://127.0.0.1:7890

    # ---- 测试执行（复用 pytest-bdd；默认按仓库结构 <repo>/pytest-bdd 推导，本机自定义请写 .env）----
    PYTEST_PROJECT_DIR = Path(os.getenv(
        "PYTEST_PROJECT_DIR", str(BASE_DIR / "pytest-bdd")))
    PYTEST_PYTHON = os.getenv(
        "PYTEST_PYTHON",
        str(BASE_DIR / "pytest-bdd" / ".venv" / "Scripts" / "python.exe"))
    ALLURE_BIN = Path(os.getenv(
        "ALLURE_BIN", str(BASE_DIR / "pytest-bdd" / "tools" / "allure" / "bin" / "allure.bat")))

    # ---- SMTP 邮件（评审通知）----
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "1") == "1"


def workspace_for(project: str, run_id: str | int) -> Path:
    """项目/流程实例工作区路径：workspaces/{project}/{run_id}。"""
    p = settings().WORKSPACE_DIR / str(project) / str(run_id)
    p.mkdir(parents=True, exist_ok=True)
    return p
