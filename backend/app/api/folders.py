"""目录树文件夹 CRUD：多级嵌套 + 删除时递归清理子文件夹并把项目移回未归类。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/folders", tags=["folders"])


def _build_tree(rows: list[models.Folder], parent_id: int | None = None) -> list[dict]:
    """按 parent_id 递归组树（根级 parent_id=None）。"""
    nodes = []
    for r in rows:
        if (r.parent_id or None) == parent_id:
            nodes.append({
                "id": r.id, "name": r.name, "parent_id": r.parent_id,
                "created_at": r.created_at,
                "children": _build_tree(rows, r.id),
            })
    return nodes


@router.get("", response_model=list[schemas.FolderNode])
def list_folder_tree(db: Session = Depends(get_db)):
    rows = db.execute(select(models.Folder).order_by(models.Folder.id)).scalars().all()
    return _build_tree(list(rows))


@router.post("", response_model=schemas.FolderOut, status_code=201)
def create_folder(body: schemas.FolderIn, db: Session = Depends(get_db)):
    if body.parent_id is not None and not db.get(models.Folder, body.parent_id):
        raise HTTPException(404, "父文件夹不存在")
    f = models.Folder(name=body.name.strip(), parent_id=body.parent_id)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.put("/{folder_id}", response_model=schemas.FolderOut)
def rename_folder(folder_id: int, body: schemas.FolderIn, db: Session = Depends(get_db)):
    f = db.get(models.Folder, folder_id)
    if not f:
        raise HTTPException(404, "文件夹不存在")
    f.name = body.name.strip()
    db.commit()
    db.refresh(f)
    return f


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    """删除文件夹：递归删除全部子文件夹；其下项目 folder_id 置 NULL（不删项目）。"""
    f = db.get(models.Folder, folder_id)
    if not f:
        raise HTTPException(404, "文件夹不存在")

    # 收集该文件夹全部后代 id（含自身）
    all_rows = db.execute(select(models.Folder)).scalars().all()
    ids = [folder_id]
    changed = True
    while changed:
        changed = False
        for r in all_rows:
            if r.parent_id in ids and r.id not in ids:
                ids.append(r.id)
                changed = True

    # 项目移回未归类（folder_id 置 NULL）
    for p in db.execute(select(models.Project).where(models.Project.folder_id.in_(ids))).scalars():
        p.folder_id = None

    for rid in ids:
        db.delete(db.get(models.Folder, rid))
    db.commit()
    return {"message": "deleted", "folders_removed": len(ids)}
