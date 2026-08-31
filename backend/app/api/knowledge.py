"""知识库：已评审用例集快照的存取（看板「本次需求完成」入库 / 列表 / 查看 / 删除）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=list[schemas.KnowledgeOut])
def list_knowledge(project_id: int | None = None, q: str = "", db: Session = Depends(get_db)):
    """知识库列表：project_id 不传=全部项目；q=按项目名称模糊查询。新入库排前。"""
    query = select(models.KnowledgeEntry).order_by(models.KnowledgeEntry.id.desc())
    if project_id:
        query = query.where(models.KnowledgeEntry.project_id == project_id)
    if q.strip():
        query = query.where(models.KnowledgeEntry.project_name.like(f"%{q.strip()}%"))
    return db.execute(query).scalars().all()


@router.delete("/{entry_id}")
def delete_knowledge(entry_id: int, db: Session = Depends(get_db)):
    """删除一条知识库记录（仅删快照，不影响源用例集）。"""
    e = db.get(models.KnowledgeEntry, entry_id)
    if not e:
        raise HTTPException(404, "知识库记录不存在")
    db.delete(e)
    db.commit()
    return {"message": "deleted"}


def _build_ref_snapshot(cs: models.CaseSet) -> dict:
    """从用例集沉淀「紧凑参考骨架」：只保留 id/标题/优先级/接口等关键信息。

    供后续用例生成引用历史用例：够 AI 理解「覆盖过哪些场景、什么风格」，
    相比完整用例树大幅省 token（步骤/前置/数据等细节全部省略）。
    """
    content = cs.content or {}
    return {
        "module": content.get("module", ""),
        "title": content.get("title", ""),
        "case_type": (cs.gen_meta or {}).get("case_type", "business"),
        "version": cs.version,
        "generated_at": content.get("generated_at", ""),
        "groups": [
            {"name": g.get("name", ""),
             "cases": [{"id": c.get("id", ""), "title": c.get("title", ""),
                        "priority": c.get("priority", ""), "api": c.get("api", "")}
                       for c in (g.get("cases") or [])]}
            for g in (content.get("groups") or [])
        ],
    }


class CollectIn(BaseModel):
    run_id: int


@router.post("/collect")
def collect(body: CollectIn, db: Session = Depends(get_db)):
    """看板「本次需求完成」：收集该 run 已评审通过的业务功能/接口用例集快照入库。

    - 每类用例类型各取「最新 approved」的一条复制入库（类型 = gen_meta.case_type）
    - 内容为完整快照，后续源用例集被覆盖/删除不影响知识库
    - 重复点击 = 再次独立入库（多次完成可并存，保存时间区分）
    - 返回 added（本次入库条数）与 missing（未评审通过的用例类型，供前端提示）
    """
    run = db.get(models.WorkflowRun, body.run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    p = db.get(models.Project, run.project_id)
    project_name = p.name if p else f"p{run.project_id}"

    approved = (db.query(models.CaseSet)
                .filter(models.CaseSet.run_id == body.run_id,
                        models.CaseSet.status == "approved")
                .order_by(models.CaseSet.version.desc())
                .all())
    latest_by_type: dict[str, models.CaseSet] = {}
    for cs in approved:   # version desc，每种类型首个即最新
        t = (cs.gen_meta or {}).get("case_type", "business")
        if t not in latest_by_type:
            latest_by_type[t] = cs

    added = 0
    for t, cs in latest_by_type.items():
        db.add(models.KnowledgeEntry(
            project_id=run.project_id, project_name=project_name,
            case_type=t, case_set_id=cs.id, case_version=cs.version,
            mod_time=(cs.content or {}).get("generated_at", ""),
            content=cs.content or {},
            ref_snapshot=_build_ref_snapshot(cs),
        ))
        added += 1
    db.commit()
    missing = [t for t in ("business", "api") if t not in latest_by_type]
    return {"added": added, "missing": missing, "project_name": project_name}