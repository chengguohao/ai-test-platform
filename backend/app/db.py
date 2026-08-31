"""数据库会话与初始化（SQLite 默认，可切 MySQL）。"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, settings
from app.models import Base

# SQLite 需要 check_same_thread=False 供 FastAPI 线程池使用
_engine = create_engine(
    settings().DATABASE_URL,
    connect_args={"check_same_thread": False} if settings().DATABASE_URL.startswith("sqlite") else {},
)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)

# 供后台线程使用的独立会话工厂（不走 FastAPI 依赖注入）
SessionLocal = _SessionLocal

# 轻量迁移：模型新增列时给已有表补列（create_all 只建新表不 ALTER 旧表）
# 格式：表名 -> {列名: DDL 类型}
_MIGRATE_ADD_COLUMNS = {
    "workflow_runs": {"name": "VARCHAR(128) DEFAULT '' NOT NULL"},
    "projects": {"ai_model_id": "INTEGER DEFAULT 0 NOT NULL",
                 "vision_model_id": "INTEGER DEFAULT 0 NOT NULL",
                 "folder_id": "INTEGER"},
}


def _migrate_add_columns() -> None:
    insp = inspect(_engine)
    with _engine.begin() as conn:
        for table, cols in _MIGRATE_ADD_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _migrate_ai_model_unique() -> None:
    """ai_model_configs 唯一规则迁移：name 唯一 → 「name+model」组合唯一。

    旧库（MySQL）index name 存在 → 先删；再建组合唯一键。
    幂等：任一步骤失败（索引已删/已存在/非 MySQL）都静默跳过，靠应用层查重兜底。
    """
    if not settings().DATABASE_URL.startswith("mysql"):
        return
    with _engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE ai_model_configs DROP INDEX `name`"))
        except Exception:  # noqa: BLE001 索引不存在/已删除
            pass
        try:
            conn.execute(text(
                "ALTER TABLE ai_model_configs ADD CONSTRAINT uq_ai_model_name_model "
                "UNIQUE (name, model)"))
        except Exception:  # noqa: BLE001 约束已存在
            pass


def init_db() -> None:
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=_engine)
    _migrate_add_columns()
    _migrate_ai_model_unique()


def get_db():
    db: Session = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
