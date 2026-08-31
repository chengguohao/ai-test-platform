"""项目 CRUD + 复制。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.workflow import ensure_default_template
from app.db import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(folder_id: int | None = None, db: Session = Depends(get_db)):
    """项目列表：folder_id 不传=全部；0=未归类（folder_id 为空）；>0=该文件夹下项目。"""
    q = select(models.Project).order_by(models.Project.id)
    if folder_id is not None:
        if folder_id == 0:
            q = q.where(models.Project.folder_id.is_(None))
        else:
            q = q.where(models.Project.folder_id == folder_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(body: schemas.ProjectIn, db: Session = Depends(get_db)):
    if db.execute(select(models.Project).where(models.Project.name == body.name)).scalar_one_or_none():
        raise HTTPException(400, f"项目已存在: {body.name}")
    p = models.Project(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    ensure_default_template(db, p.id)
    return p


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


@router.put("/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: int, body: schemas.ProjectIn, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post("/{project_id}/copy", response_model=schemas.ProjectOut, status_code=201)
def copy_project(project_id: int, db: Session = Depends(get_db)):
    """复制项目：配置 + 流程模板。

    流程实例不复制——新项目从零开始跑流程（需求、用例、工件都是空的），
    只继承被测系统/执行引擎配置与流程模板结构。
    """
    src = db.get(models.Project, project_id)
    if not src:
        raise HTTPException(404, "项目不存在")

    # 新名称：原名-副本 / 原名-副本2 …（保证 unique 不冲突）
    base = f"{src.name}-副本"
    name, n = base, 2
    while db.execute(select(models.Project).where(models.Project.name == name)).scalar_one_or_none():
        name = f"{base}{n}"
        n += 1

    new = models.Project(name=name, desc=src.desc,
                         engine_config=dict(src.engine_config or {}),
                         ai_config=dict(src.ai_config or {}),
                         ai_model_id=src.ai_model_id,
                         vision_model_id=src.vision_model_id,
                         folder_id=src.folder_id)
    db.add(new)
    db.flush()

    # 流程模板（结构一并复制；实例从零开始）
    for t in db.execute(select(models.WorkflowTemplate).where(
            models.WorkflowTemplate.project_id == src.id)).scalars():
        db.add(models.WorkflowTemplate(project_id=new.id, name=t.name, stages=t.stages))

    db.commit()
    db.refresh(new)
    return new


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """删除项目：级联清理模板、流程实例（阶段/用例集/评审/工件/执行记录）与工作区目录。"""
    import shutil
    from app.config import settings

    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    # 收集该项目全部流程实例，级联删除实例级数据
    run_ids = [r.id for r in db.execute(select(models.WorkflowRun).where(
        models.WorkflowRun.project_id == project_id)).scalars()]
    for rid in run_ids:
        for m in (models.StageState, models.CaseSet, models.ReviewRecord,
                  models.Artifact, models.ExecutionRun):
            for row in db.execute(select(m).where(m.run_id == rid)).scalars():
                db.delete(row)
        db.delete(db.get(models.WorkflowRun, rid))
    for t in db.execute(select(models.WorkflowTemplate).where(
            models.WorkflowTemplate.project_id == project_id)).scalars():
        db.delete(t)
    db.delete(p)
    db.commit()

    # 删除整个项目工作区（含所有实例的工件/日志/报告文件）
    ws = settings().WORKSPACE_DIR / p.name
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    return {"message": "deleted", "runs_removed": len(run_ids)}
