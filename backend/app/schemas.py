"""Pydantic 模型（请求/响应契约）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---- 项目 ----
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    desc: str = ""
    engine_config: dict = {}
    ai_config: dict = {}
    ai_model_id: int = 0   # 0=全局 .env 默认
    vision_model_id: int = 0   # 副模型（多模态视觉模型），0=未勾选，识图时回退主模型/全局
    folder_id: Optional[int] = None   # 所属文件夹（目录树 folders.id），None=未归类


class ProjectOut(ProjectIn):
    id: int
    created_at: datetime


# ---- 目录树文件夹 ----
class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: Optional[int] = None   # None=根级文件夹


class FolderOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    created_at: datetime


class FolderNode(FolderOut):
    """文件夹树节点：children 递归嵌套。"""
    children: list[FolderNode] = []


# ---- AI 模型配置 ----
class AiModelIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""          # 编辑时传空表示不修改
    model: str = "deepseek-chat"
    temperature: float = 0.2
    enabled: bool = True


class AiModelOut(BaseModel):
    id: int
    name: str
    base_url: str
    model: str
    temperature: float
    enabled: bool
    api_key_masked: str        # 仅回显末 4 位
    created_at: datetime


# ---- 流程模板 ----
class StageSpec(BaseModel):
    type: str                       # requirement/api_doc/case_gen/case_review/auto_gen/execute/skill/mcp/custom
    name: str
    enabled: bool = True
    source: str = ""                # upload/paste/url_fetch/mcp/connector
    source_config: dict = {}
    ai_config: dict = {}
    skill_id: str = ""              # skill 类型步骤绑定的 Skill id（模板设计时预选）


class TemplateIn(BaseModel):
    project_id: int
    name: str
    stages: list[StageSpec] = []


class TemplateOut(TemplateIn):
    id: int
    created_at: datetime


# ---- 流程实例 ----
class RunIn(BaseModel):
    project_id: int
    template_id: int
    name: str = ""


class RunOut(BaseModel):
    id: int
    project_id: int
    template_id: int
    template_snapshot: list[StageSpec] = []
    name: str = ""
    status: str
    current_stage_idx: int
    created_at: datetime


# ---- 阶段状态 ----
class StageOut(BaseModel):
    id: int
    run_id: int
    stage_type: str
    stage_name: str
    idx: int
    enabled: bool
    status: str
    meta: dict


# ---- 接入/工件 ----
class ArtifactIn(BaseModel):
    run_id: int
    stage_type: str
    type: str
    name: str
    source: dict = {}


class ArtifactOut(ArtifactIn):
    id: int
    file_path: str
    version: int
    status: str
    created_at: datetime


class ReviewIn(BaseModel):
    run_id: int
    result: str                        # approved / returned
    reason: str = ""
    action: str = ""                   # regenerate / reupload
    reviewer: str = ""


class ConnectorIn(BaseModel):
    project_id: int = 0
    kind: str
    name: str
    cfg: dict = {}
    enabled: bool = True


class ConnectorOut(ConnectorIn):
    id: int
    created_at: datetime


# ---- 执行 ----
class ExecutionOut(BaseModel):
    id: int
    run_id: int
    status: str
    env_check: dict
    summary: dict
    allure_dir: str
    report_dir: str
    error_log: str
    created_at: datetime


class Msg(BaseModel):
    message: str
    data: Optional[Any] = None
