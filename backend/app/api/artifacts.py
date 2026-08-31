"""工件（artifact）：上传/列表/下载。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, storage
from app.config import settings
from app.db import get_db

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("", response_model=list[schemas.ArtifactOut])
def list_artifacts(run_id: int, db: Session = Depends(get_db)):
    return db.execute(select(models.Artifact).where(
        models.Artifact.run_id == run_id).order_by(models.Artifact.id)).scalars().all()


@router.post("/upload", response_model=schemas.ArtifactOut, status_code=201)
async def upload_artifact(
    run_id: int = Form(...),
    stage_type: str = Form(...),
    type: str = Form(...),
    name: str = Form(""),
    project: str = Form(""),
    has_images: str = Form("false"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()
    filename = file.filename or name
    path = storage.save_upload(project or f"p{run_id}", run_id, filename, data)
    art = models.Artifact(
        run_id=run_id, stage_type=stage_type, type=type,
        name=name or filename, file_path=str(path),
        source={"source": "upload", "filename": filename})
    db.add(art)
    db.commit()
    db.refresh(art)
    # 上传接口文档 -> 自动推进 api_doc 阶段为 success（过守卫）并启动下一阶段
    # 仅对 type=api_doc 触发；其它类型工件上传不自动改阶段状态
    if type == "api_doc":
        from app.api.workflow import complete_stage_by_type
        try:
            complete_stage_by_type(db, run_id, "api_doc")
        except HTTPException:
            pass
    # 需求文档勾选「包含图片」-> 后台线程启动多模态规范化（与 auto_generate 先例一致）
    # 只处理 docx 内嵌图；接口立即返回，进度见 req_vision:{run_id}
    if type == "requirement" and has_images.strip().lower() == "true":
        import threading
        from app.services import vision as vision_svc
        threading.Thread(
            target=vision_svc.normalize_requirement_async,
            args=(run_id, None),
            daemon=True, name=f"req-vision-{run_id}",
        ).start()
    return art


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: int, db: Session = Depends(get_db)):
    art = db.get(models.Artifact, artifact_id)
    if not art or not art.file_path:
        raise HTTPException(404, "工件不存在")
    # 下载文件名无后缀时，从实际存储路径补全扩展名（否则浏览器下载的文件打不开）
    name = art.name or "download"
    if "." not in os.path.basename(name):
        ext = os.path.splitext(art.file_path)[1]
        if ext:
            name = f"{name}{ext}"
    return FileResponse(art.file_path, filename=name)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: int, db: Session = Depends(get_db)):
    art = db.get(models.Artifact, artifact_id)
    if not art:
        raise HTTPException(404, "工件不存在")
    db.delete(art)
    db.commit()
    return {"message": "deleted"}
