"""全局 AI 模型配置：多套供应商/模型 CRUD + 连通测试（key 脱敏）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/ai-models", tags=["ai-models"])


def _mask(key: str) -> str:
    if not key:
        return ""
    return "****" + key[-4:]


def _out(m: models.AiModelConfig) -> dict:
    return {
        "id": m.id, "name": m.name, "base_url": m.base_url, "model": m.model,
        "temperature": m.temperature, "enabled": m.enabled,
        "api_key_masked": _mask(m.api_key),
        "created_at": m.created_at.isoformat(),
    }


@router.get("")
def list_models(db: Session = Depends(get_db)):
    rows = db.execute(select(models.AiModelConfig).order_by(
        models.AiModelConfig.id)).scalars().all()
    return [_out(m) for m in rows]


@router.post("", status_code=201)
def create_model(body: schemas.AiModelIn, db: Session = Depends(get_db)):
    # 名称可重复（同一供应商多型号），但「名称+模型」组合唯一防误建完全重复的两行
    dup = db.execute(select(models.AiModelConfig).where(
        models.AiModelConfig.name == body.name,
        models.AiModelConfig.model == body.model)).scalar_one_or_none()
    if dup:
        raise HTTPException(400, f"已存在相同「名称+模型」配置: {body.name} / {body.model}")
    m = models.AiModelConfig(**body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.put("/{model_id}")
def update_model(model_id: int, body: schemas.AiModelIn, db: Session = Depends(get_db)):
    m = db.get(models.AiModelConfig, model_id)
    if not m:
        raise HTTPException(404, "模型配置不存在")
    dup = db.execute(select(models.AiModelConfig).where(
        models.AiModelConfig.name == body.name,
        models.AiModelConfig.model == body.model)).scalar_one_or_none()
    if dup and dup.id != model_id:
        raise HTTPException(400, f"「名称+模型」已被其他配置占用: {body.name} / {body.model}")
    m.name = body.name
    m.base_url = body.base_url
    m.model = body.model
    m.temperature = body.temperature
    m.enabled = body.enabled
    if body.api_key:  # 空 key = 保持原值不改
        m.api_key = body.api_key
    db.commit()
    return _out(m)


@router.delete("/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(models.AiModelConfig, model_id)
    if not m:
        raise HTTPException(404, "模型配置不存在")
    # 不级联清项目绑定：引用它的项目自动回退全局默认（ai_model_id 保留原值但查不到即走 .env）
    n = db.execute(select(models.Project.id).where(
        models.Project.ai_model_id == model_id)).all()
    db.delete(m)
    db.commit()
    return {"message": "deleted", "bound_projects": len(n),
            "hint": "绑定该配置的项目将自动回退全局默认模型"}


@router.post("/{model_id}/test")
def test_model(model_id: int, db: Session = Depends(get_db)):
    """连通测试：用该配置发一条最小请求（max_tokens=8）验证 base_url/key/model。"""
    from app.services import ai_llm

    m = db.get(models.AiModelConfig, model_id)
    if not m:
        raise HTTPException(404, "模型配置不存在")
    llm_config = {"base_url": m.base_url, "api_key": m.api_key,
                  "model": m.model, "temperature": m.temperature}
    try:
        reply = ai_llm.chat(
            [{"role": "user", "content": "回复：ok"}],
            llm_config=llm_config, max_tokens=8)
        return {"ok": True, "message": f"连通成功，模型回复：{reply[:20]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连通失败：{e}"}
