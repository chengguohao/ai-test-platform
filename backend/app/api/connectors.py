"""连接器 API：注册/测试/拉取（MCP 优先，自由接入自研平台）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.connectors import REGISTRY, get_connector
from app.db import get_db

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

CONNECTOR_KINDS = [
    {"kind": "local", "name": "本地上传", "desc": "上传文件（最常用，零配置）"},
    {"kind": "paste", "name": "粘贴文本", "desc": "快速录入需求/接口/知识库摘录"},
    {"kind": "url_fetch", "name": "URL 抓取", "desc": "Swagger/OpenAPI/可访问知识库页"},
    {"kind": "mcp", "name": "MCP Server", "desc": "注册外部自研平台（业界 agent 标准，拉实据反幻觉）"},
    {"kind": "http", "name": "通用 HTTP", "desc": "轻量兜底，URL+认证+解析路径拉任意 REST"},
    {"kind": "smtp", "name": "SMTP 邮件", "desc": "评审通知/报告链接（动作仍在平台内）"},
]


@router.get("/kinds")
def list_kinds():
    return [k for k in CONNECTOR_KINDS if k["kind"] in REGISTRY]


@router.get("", response_model=list[schemas.ConnectorOut])
def list_connectors(project_id: int = 0, db: Session = Depends(get_db)):
    return db.execute(select(models.ConnectorConfig).where(
        models.ConnectorConfig.project_id == project_id).order_by(models.ConnectorConfig.id)).scalars().all()


@router.post("", response_model=schemas.ConnectorOut, status_code=201)
def create_connector(body: schemas.ConnectorIn, db: Session = Depends(get_db)):
    if body.kind not in REGISTRY:
        raise HTTPException(400, f"未注册连接器类型: {body.kind}")
    errors = get_connector(body.kind).validate_config(body.cfg)
    if errors:
        raise HTTPException(422, {"message": "配置校验失败", "errors": errors})
    c = models.ConnectorConfig(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{connector_id}", response_model=schemas.ConnectorOut)
def update_connector(connector_id: int, body: schemas.ConnectorIn, db: Session = Depends(get_db)):
    c = db.get(models.ConnectorConfig, connector_id)
    if not c:
        raise HTTPException(404, "连接器不存在")
    c.name, c.cfg, c.enabled = body.name, body.cfg, body.enabled
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{connector_id}")
def delete_connector(connector_id: int, db: Session = Depends(get_db)):
    c = db.get(models.ConnectorConfig, connector_id)
    if not c:
        raise HTTPException(404, "连接器不存在")
    db.delete(c)
    db.commit()
    return {"message": "deleted"}


class FetchIn(BaseModel):
    kind: str
    cfg: dict = {}
    params: dict = {}


@router.post("/fetch")
def fetch(f: FetchIn):
    """调用一个接入源/连接器拉取内容（测试连通或正式导入）。"""
    try:
        payload = get_connector(f.kind).fetch(f.cfg, f.params)
        return {"text": payload.text[:200_000], "name": payload.text_name,
                "files": [str(p) for p in payload.files], "ref": payload.ref}
    except Exception as e:  # noqa: BLE001 结构化错误返回给前端
        raise HTTPException(400, f"拉取失败: {e}")


@router.get("/mcp/{connector_id}/tools")
def mcp_tools(connector_id: int, db: Session = Depends(get_db)):
    c = db.get(models.ConnectorConfig, connector_id)
    if not c or c.kind != "mcp":
        raise HTTPException(404, "MCP 连接器不存在")
    try:
        return {"tools": get_connector("mcp").list_tools(c.cfg)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"连接 MCP Server 失败: {e}")


class PushIn(BaseModel):
    connector_id: int
    payload: dict = {}


@router.post("/push")
def push(p: PushIn, db: Session = Depends(get_db)):
    """推送/通知（如 SMTP 评审邮件）。"""
    c = db.get(models.ConnectorConfig, p.connector_id)
    if not c:
        raise HTTPException(404, "连接器不存在")
    try:
        return get_connector(c.kind).push(c.cfg, p.payload)
    except NotImplementedError:
        raise HTTPException(400, f"连接器 {c.kind} 不支持推送")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"推送失败: {e}")
