"""SQLAlchemy 模型（对应方案 §五 核心表）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    desc: Mapped[str] = mapped_column(Text, default="")
    # 被测系统/执行引擎配置（base_url、pytest 项目路径、python、allure 路径等）
    engine_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # AI 配置（model/temperature/proxy 等，可覆盖全局）——保留兼容，实际生效见 ai_model_id
    ai_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 绑定的 AI 模型配置（ai_model_configs.id），0=用全局 .env 默认
    ai_model_id: Mapped[int] = mapped_column(Integer, default=0)
    # 副模型（多模态视觉模型，ai_model_configs.id），0=未勾选，识图时回退主模型/全局
    vision_model_id: Mapped[int] = mapped_column(Integer, default=0)
    # 所属文件夹（左侧目录树 folders.id），NULL=未归类（显示在根/全部视图）
    folder_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Folder(Base):
    """左侧目录树文件夹节点：多级嵌套，父级 parent_id=NULL 表示根级。

    删除文件夹时递归删除其全部子文件夹，其下项目 folder_id 置 NULL（回到未归类，不删除项目）。
    """
    __tablename__ = "folders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AiModelConfig(Base):
    """全局 AI 模型配置：可建多条（不同供应商/模型），项目绑定后覆盖 .env 默认。

    名称可重复（如同一供应商 DeepSeek 名下配 deepseek-v4-flash / deepseek-chat 等多套），
    但「名称+模型(model)」组合唯一，防止误建完全相同的两行。
    """
    __tablename__ = "ai_model_configs"
    __table_args__ = (UniqueConstraint("name", "model", name="uq_ai_model_name_model"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(String(255), default="https://api.deepseek.com/v1")
    api_key: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(128), default="deepseek-chat")
    temperature: Mapped[float] = mapped_column(default=0.2)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # 有序阶段列表：[{type,name,enabled,source,source_config,ai_config}]
    stages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    template_id: Mapped[int] = mapped_column(Integer)
    template_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # 实例化时的模板快照
    # 实例名称（用户新建时填写；空则后端自动「第 N 轮流程」）
    name: Mapped[str] = mapped_column(String(128), default="")
    # 项目内实例序号（从 1 开始，与默认命名「第 N 轮流程」一致；跨项目不连续，仅项目内可读）
    run_no: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed/returned
    current_stage_idx: Mapped[int] = mapped_column(Integer, default=-1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StageState(Base):
    __tablename__ = "stage_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    stage_type: Mapped[str] = mapped_column(String(64))
    stage_name: Mapped[str] = mapped_column(String(128))
    idx: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed/returned/skipped
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # 接入源/打回原因/错误等
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    stage_type: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(64))  # requirement/api_doc/case_tree/approved_cases/auto_file/report/...
    name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[dict] = mapped_column(JSON, default=dict)  # 来源引用（upload/paste/url/mcp/connector）
    status: Mapped[str] = mapped_column(String(32), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CaseSet(Base):
    __tablename__ = "case_sets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="generated")  # generated/reviewed/approved/returned
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # 用例树 JSON（§七）
    gen_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # skill 版本/模型/temp/seed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ReviewRecord(Base):
    __tablename__ = "review_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    stage_type: Mapped[str] = mapped_column(String(64), default="")   # 关联阶段类型（评审记录所属阶段）
    result: Mapped[str] = mapped_column(String(32))  # approved / returned
    reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(32), default="")  # regenerate / reupload
    reviewer: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ExecutionRun(Base):
    __tablename__ = "execution_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/env_fail/running/passed/failed
    env_check: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # passed/failed/errors/skips
    allure_dir: Mapped[str] = mapped_column(String(512), default="")
    report_dir: Mapped[str] = mapped_column(String(512), default="")
    error_log: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, default=0)  # 0=全局
    kind: Mapped[str] = mapped_column(String(64))  # mcp/http/smtp/...
    name: Mapped[str] = mapped_column(String(128))
    cfg: Mapped[dict] = mapped_column(JSON, default=dict)  # 凭据/URL/解析规则（敏感字段加密存储）
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class KnowledgeEntry(Base):
    """知识库：已评审通过的用例集快照（业务功能用例 / 接口测试用例）。

    看板「本次需求完成」把 run 下各类型最新 approved 用例集复制入库；
    内容为完整快照（后续原用例集被覆盖/删除不影响知识库）。
    ref_snapshot 为入库时沉淀的「紧凑参考骨架」，供后续用例生成引用
    （只含 id/标题/优先级/接口等关键信息，不含步骤详情，省 token）。
    """
    __tablename__ = "knowledge_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    project_name: Mapped[str] = mapped_column(String(128), default="")   # 项目卡片名称（入库时快照）
    case_type: Mapped[str] = mapped_column(String(32), default="business")  # business=业务功能用例 / api=接口测试用例
    case_set_id: Mapped[int] = mapped_column(Integer, default=0)   # 来源用例集 id
    case_version: Mapped[int] = mapped_column(Integer, default=0)  # 来源用例集版本
    mod_time: Mapped[str] = mapped_column(String(32), default="")  # 修改时间（用例集生成时间）
    content: Mapped[dict] = mapped_column(JSON, default=dict)      # 用例树完整快照
    ref_snapshot: Mapped[dict] = mapped_column(JSON, default=dict) # 紧凑参考骨架（供生成时引用）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)  # 保存时间
