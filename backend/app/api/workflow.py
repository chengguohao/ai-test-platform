"""流程模板 / 流程实例 / 阶段状态 编排。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# 内置阶段类型库（FlowDesigner 左侧卡片来源；desc 面向测试人员，用大白话）
STAGE_LIBRARY = [
    {"type": "requirement", "name": "需求上传", "desc": "提交需求资料：上传文件 / 粘贴文字 / 填链接 / 对接公司平台", "can_skip": False},
    {"type": "api_doc", "name": "接口文档", "desc": "提交接口文档；本需求没有新增接口时可以跳过", "can_skip": True},
    {"type": "case_gen", "name": "生成用例", "desc": "AI 自动把需求（+接口文档/知识库资料）转成测试用例，可预览、可重新生成", "can_skip": False},
    {"type": "auto_gen", "name": "自动化生成", "desc": "AI 按已批准的用例 + 接口文档，自动生成接口自动化脚本", "can_skip": True},
    {"type": "execute", "name": "执行报告", "desc": "检查测试环境 → 自动跑自动化用例 → 生成 Allure 报告", "can_skip": False},
    {"type": "skill", "name": "AI 处理", "desc": "选一种 AI 能力（需求摘要/生成用例/自动化生成等）单独执行，结果存为工件，可插到任意步骤", "can_skip": True},
    {"type": "mcp", "name": "平台取数", "desc": "从已注册的公司平台(MCP)拉一份真实资料存为工件，可插到任意步骤", "can_skip": True},
]

DEFAULT_STAGES = [
    {"type": "requirement", "name": "需求上传", "enabled": True, "source": "", "source_config": {}, "ai_config": {}},
    {"type": "api_doc", "name": "接口文档", "enabled": True, "source": "", "source_config": {}, "ai_config": {}},
    {"type": "case_gen", "name": "生成用例", "enabled": True, "source": "", "source_config": {}, "ai_config": {}},
    {"type": "auto_gen", "name": "自动化生成", "enabled": True, "source": "", "source_config": {}, "ai_config": {}},
    {"type": "execute", "name": "执行报告", "enabled": True, "source": "", "source_config": {}, "ai_config": {}},
]


def ensure_default_template(db: Session, project_id: int) -> None:
    """项目无模板时自动建一个默认模板（5 阶段，可改）。

    项目允许多个模板（设计页可「新建模板」并存多个），因此这里只关心
    「是否已存在任意模板」：用 limit(1) 探测，避免 scalar_one_or_none()
    在项目已有 ≥2 个模板时抛 MultipleResultsFound 导致 GET /templates 500。
    """
    exists = db.execute(select(models.WorkflowTemplate.id).where(
        models.WorkflowTemplate.project_id == project_id).limit(1)).scalar_one_or_none()
    if exists:
        return
    db.add(models.WorkflowTemplate(project_id=project_id, name="默认流程", stages=DEFAULT_STAGES))
    db.commit()


# ---------------- 模板 ----------------
@router.get("/stage-library")
def stage_library():
    return STAGE_LIBRARY


@router.get("/templates", response_model=list[schemas.TemplateOut])
def list_templates(project_id: int, db: Session = Depends(get_db)):
    ensure_default_template(db, project_id)  # 项目无模板时惰性补建默认模板
    return db.execute(select(models.WorkflowTemplate).where(
        models.WorkflowTemplate.project_id == project_id)).scalars().all()


@router.post("/templates", response_model=schemas.TemplateOut, status_code=201)
def create_template(body: schemas.TemplateIn, db: Session = Depends(get_db)):
    t = models.WorkflowTemplate(
        project_id=body.project_id, name=body.name,
        stages=[s.model_dump() for s in body.stages])
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/templates/{template_id}", response_model=schemas.TemplateOut)
def update_template(template_id: int, body: schemas.TemplateIn, db: Session = Depends(get_db)):
    t = db.get(models.WorkflowTemplate, template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    t.name = body.name
    t.stages = [s.model_dump() for s in body.stages]
    db.commit()
    db.refresh(t)
    return t


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = db.get(models.WorkflowTemplate, template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"message": "deleted"}


# ---------------- 流程实例 ----------------
def _next_run_seq(db: Session, project_id: int) -> int:
    """项目内实例序号：已有实例数 + 1，用于自动命名「第 N 轮流程」。"""
    n = len(db.execute(select(models.WorkflowRun.id).where(
        models.WorkflowRun.project_id == project_id)).all())
    return n + 1


@router.post("/runs", response_model=schemas.RunOut, status_code=201)
def create_run(body: schemas.RunIn, db: Session = Depends(get_db)):
    if not db.get(models.Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    t = db.get(models.WorkflowTemplate, body.template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    snapshot = [dict(s) for s in t.stages]
    # 名称：用户填了就用；没填自动「第 N 轮流程」（N=该项目内实例序号，从 1 开始）
    seq = _next_run_seq(db, body.project_id)
    run = models.WorkflowRun(
        project_id=body.project_id, template_id=body.template_id,
        template_snapshot=snapshot, status="pending",
        name=(body.name or "").strip() or f"第 {seq} 轮流程",
        run_no=seq,   # 项目内序号存库：跨项目不连续，仅项目内自洽
    )
    db.add(run)
    db.flush()
    # 实例化每个阶段的状态机（禁用阶段直接 skipped；skill 步骤绑定随模板写入 meta）
    for idx, s in enumerate(snapshot):
        db.add(models.StageState(
            run_id=run.id, stage_type=s.get("type", "custom"),
            stage_name=s.get("name", s.get("type", "")), idx=idx,
            enabled=bool(s.get("enabled", True)),
            status="pending" if s.get("enabled", True) else "skipped",
            meta={"source": s.get("source", ""), "source_config": s.get("source_config", {}),
                  "skill_id": s.get("skill_id", "")}))
    db.commit()
    db.refresh(run)
    return run


@router.get("/runs", response_model=list[schemas.RunOut])
def list_runs(project_id: int, db: Session = Depends(get_db)):
    runs = db.execute(select(models.WorkflowRun).where(
        models.WorkflowRun.project_id == project_id).order_by(models.WorkflowRun.id.desc())).scalars().all()
    return [r for r in runs]


@router.get("/runs/{run_id}", response_model=schemas.RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(models.WorkflowRun, run_id)
    if not r:
        raise HTTPException(404, "流程实例不存在")
    return r


@router.delete("/runs/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    """删除流程实例：级联清理阶段状态、用例集、评审记录、工件（含工作区文件）、执行记录。"""
    import shutil
    from app.config import settings

    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")

    # 删除前收集工件路径与工作区根目录（run 目录下所有文件都属于该实例）
    project = db.get(models.Project, run.project_id)
    art_paths = [a.file_path for a in db.execute(
        select(models.Artifact).where(models.Artifact.run_id == run_id)).scalars()
        if a.file_path]
    ws_dir = settings().WORKSPACE_DIR / str(project.name if project else f"p{run_id}") / str(run_id)

    # 级联删除数据库记录
    for model in (models.StageState, models.CaseSet, models.ReviewRecord,
                  models.Artifact, models.ExecutionRun):
        for row in db.execute(select(model).where(model.run_id == run_id)).scalars():
            db.delete(row)
    db.delete(run)
    db.commit()

    # 删除工作区文件（整个实例目录）与工件指向的散落文件
    removed = 0
    if ws_dir.exists():
        shutil.rmtree(ws_dir, ignore_errors=True)
    for fp in art_paths:
        try:
            p = Path(fp)
            if p.exists() and ws_dir not in p.parents:
                p.unlink(missing_ok=True)
                removed += 1
        except OSError:
            pass
    return {"message": "流程实例已删除", "workspace": str(ws_dir),
            "extra_files_removed": removed}


@router.get("/runs/{run_id}/stages", response_model=list[schemas.StageOut])
def run_stages(run_id: int, db: Session = Depends(get_db)):
    return db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id).order_by(models.StageState.idx)).scalars().all()


class StagePatch(BaseModel):
    status: str = ""
    meta: dict | None = None


# PATCH 只允许这些状态：skipped（跳过）、failed（人工标记失败）、pending（重置）。
# success 必须走 /advance，由后端校验前置条件，防止绕过评审闭环。
_PATCH_ALLOWED = {"skipped", "failed", "pending"}


@router.patch("/runs/{run_id}/stages/{stage_id}")
def update_stage(run_id: int, stage_id: int, body: StagePatch, db: Session = Depends(get_db)):
    st = db.get(models.StageState, stage_id)
    if not st or st.run_id != run_id:
        raise HTTPException(404, "阶段不存在")
    if body.status:
        if body.status not in _PATCH_ALLOWED:
            raise HTTPException(422, f"status 只允许 {_PATCH_ALLOWED}（success 请走 /advance）")
        st.status = body.status
    if body.meta is not None:
        st.meta = {**(st.meta or {}), **body.meta}
    db.commit()
    return {"message": "ok", "status": st.status}


# ---------------- 状态推进：前置条件守卫 ----------------
def _check_stage_prerequisite(db: Session, st: models.StageState) -> None:
    """校验一个阶段是否真的完成了，未完成直接抛 400（守卫，不可绕过）。

    规则（按 stage_type）：
      requirement / api_doc : 必须有对应工件
      case_gen              : 必须有用例集且已评审通过
      auto_gen              : 必须有 auto_file 工件
      execute               : 必须有执行记录且 passed
      skill / mcp           : 有结果工件
    其余类型不校验（自定义阶段）。
    """
    t = st.stage_type
    if t in ("requirement", "api_doc"):
        art = db.execute(select(models.Artifact).where(
            models.Artifact.run_id == st.run_id,
            models.Artifact.type == t).limit(1)).scalar_one_or_none()
        if not art:
            raise HTTPException(400, f"「{st.stage_name}」缺少{'需求' if t == 'requirement' else '接口文档'}工件，不能完成该阶段")
    elif t == "case_gen":
        rows = db.query(models.CaseSet).filter(models.CaseSet.run_id == st.run_id).all()
        if not rows:
            raise HTTPException(400, "「生成用例」尚无用例集，请先生成用例")
        # 生成了什么就必须评审什么——任一已生成类型的用例集未评审通过则不能完成
        pending = _pending_review_types(db, st.run_id)
        if pending:
            label = "、".join("接口测试" if x == "api" else "业务功能" for x in pending)
            raise HTTPException(400, f"「生成用例」的{label}用例集尚未评审通过，请在生成用例页点「评审通过」")
    elif t == "auto_gen":
        # 评审门槛统一收敛到「用例集已批准」：由生成用例页「评审通过」标记 approved。
        # 有接口文档时必须存在已批准的接口测试用例集（自动化脚本依赖接口用例）。
        approved = [c for c in db.query(models.CaseSet).filter(
            models.CaseSet.run_id == st.run_id,
            models.CaseSet.status == "approved").all()]
        if not approved:
            raise HTTPException(400, "「自动化生成」前请先在「生成用例」页标记「评审通过」（代表已检查用例）")
        api_art = db.execute(select(models.Artifact).where(
            models.Artifact.run_id == st.run_id,
            models.Artifact.type == "api_doc").limit(1)).scalar_one_or_none()
        if api_art and not any((c.gen_meta or {}).get("case_type") == "api" for c in approved):
            raise HTTPException(400, "已上传接口文档，需先通过「接口测试用例」：在生成用例页选中接口测试用例后标记评审通过")
    elif t == "execute":
        er = (db.query(models.ExecutionRun).filter(models.ExecutionRun.run_id == st.run_id)
              .order_by(models.ExecutionRun.id.desc()).first())
        if not er:
            raise HTTPException(400, "「执行报告」尚无执行记录，请先执行测试")
        if er.status != "passed":
            raise HTTPException(400, f"「执行报告」最近一次执行状态为 {er.status}，未通过不能推进")
    elif t in ("skill", "mcp"):
        art = db.execute(select(models.Artifact).where(
            models.Artifact.run_id == st.run_id,
            models.Artifact.stage_type == t).limit(1)).scalar_one_or_none()
        if not art:
            raise HTTPException(400, f"「{st.stage_name}」尚无结果工件")


def _pending_review_types(db: Session, run_id: int) -> list[str]:
    """返回「已生成但尚未评审通过」的用例类型列表（business/api）。

    以每个类型最新版用例集的状态为准；返回空列表表示已生成类型全部评审通过。
    """
    rows = db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id).all()
    latest: dict[str, models.CaseSet] = {}
    for c in rows:
        t = (c.gen_meta or {}).get("case_type", "business")
        if t not in latest or c.version > latest[t].version:
            latest[t] = c
    return [t for t, c in latest.items() if c.status != "approved"]


def _case_gen_summary(db: Session, run_id: int) -> dict:
    """生成用例阶段的逐类型状态摘要：business/api 各自是「未生成/待评审/已评审」。

    供前端卡片显示组合文案，例如：
      - 业务已评审 + 接口未生成  -> { business: approved, api: none }（阶段不可完成）
      - 两类型都待评审           -> { business: pending_review, api: pending_review }
      - 两类型都已评审           -> { business: approved, api: approved }（阶段可完成）
    """
    rows = db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id).all()
    latest: dict[str, models.CaseSet] = {}
    for c in rows:
        t = (c.gen_meta or {}).get("case_type", "business")
        if t not in latest or c.version > latest[t].version:
            latest[t] = c
    summary: dict[str, str] = {}
    for t in ("business", "api"):
        cs = latest.get(t)
        if not cs:
            summary[t] = "none"              # 未生成
        elif cs.status == "approved":
            summary[t] = "approved"          # 已评审通过
        else:
            summary[t] = "pending_review"    # 已生成未评审
    return summary


def sync_case_gen_status(db: Session, run_id: int) -> None:
    """生成用例阶段状态同步：生成 / 评审 / 打回重传后调用。

    按每类用例（业务/接口）的生成+评审状态组合：
      - 两类都生成并评审通过 → 阶段置 success 并推进；
      - 任一类型已生成但未评审通过 → 阶段置 pending_review（待评审），
        并把逐类型摘要写入 meta.case_gen_summary 供前端卡片显示组合文案；
      - 任一类型未生成 → 阶段保持待处理（该类型尚未生成，谈不上评审）。
    """
    st = db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id,
        models.StageState.stage_type == "case_gen").limit(1)).scalar_one_or_none()
    if not st:
        return
    summary = _case_gen_summary(db, run_id)
    pending = [t for t, s in summary.items() if s == "pending_review"]
    if pending:
        if st.status != "pending_review":
            st.status = "pending_review"
        meta = {**(st.meta or {}), "pending_review": pending,
                "case_gen_summary": summary}
        meta.pop("error", None)   # 清掉历史失败遗留的 error
        st.meta = meta
        db.commit()
    elif all(s == "approved" for s in summary.values()) and summary:
        try:
            complete_stage_by_type(db, run_id, "case_gen")
        except Exception:  # noqa: BLE001
            pass
    else:
        # 存在未生成类型（业务或接口都没生成）：阶段回待处理，等待用户生成
        if st.status not in ("pending", "running", "returned"):
            st.status = "pending"
        st.meta = {**(st.meta or {}), "case_gen_summary": summary}
        db.commit()


@router.get("/runs/{run_id}/advance")
def advance(run_id: int, db: Session = Depends(get_db)):
    """把当前 running 阶段置 success（先过前置条件守卫），并推进下一个 pending 阶段。"""
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    stages = db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id).order_by(models.StageState.idx)).scalars().all()
    current = next((s for s in stages if s.status == "running"), None)
    if current is not None:
        _check_stage_prerequisite(db, current)
        current.status = "success"
    nxt = next((s for s in stages if s.status == "pending" and s.enabled), None)
    if nxt:
        nxt.status = "running"
        run.current_stage_idx = nxt.idx
        run.status = "running"
    elif all(s.status in ("success", "skipped") for s in stages):
        run.status = "success"
    db.commit()
    return {"message": "ok", "current_stage_idx": run.current_stage_idx, "run_status": run.status}


def complete_stage_by_type(db: Session, run_id: int, stage_type: str) -> None:
    """指定 stage_type 的阶段标记为 success（过守卫），并推进下一个 pending 阶段。

    用于「关键产出已生成」自动推进场景：
      - 生成需求摘要后 -> requirement 阶段 success（ai_gen.summary 调用）
      - 上传接口文档后 -> api_doc 阶段 success（artifacts.upload 调用，仅 type=api_doc）
    与 advance 的差别：advance 找当前 running 阶段；本函数按 stage_type 精准定位，
    避免「阶段未进入 running 但产出已就绪」时无法推进。
    已是 success 的阶段跳过；守卫失败抛 HTTPException 由调用方处理。
    """
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        return
    stages = db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id).order_by(models.StageState.idx)).scalars().all()
    st = next((s for s in stages if s.stage_type == stage_type and s.enabled), None)
    if not st or st.status == "success":
        return
    _check_stage_prerequisite(db, st)
    st.status = "success"
    nxt = next((s for s in stages if s.status == "pending" and s.enabled), None)
    if nxt:
        nxt.status = "running"
        run.current_stage_idx = nxt.idx
        run.status = "running"
    elif all(s.status in ("success", "skipped") for s in stages):
        run.status = "success"
    db.commit()


def mark_stage_status(db: Session, run_id: int, stage_type: str,
                      status: str, error: str | None = None) -> None:
    """生成类接口的实时阶段状态反馈：接口入口置 running，失败置 failed。

    - running：接口开始处理时调用，前端看板即时显示「进行中」
    - failed  : 接口处理失败时调用，error 原因写入阶段 meta 供 UI 展示
    幂等：已是目标状态跳过；进入 running 时清掉上次失败遗留的 error。
    """
    st = db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id,
        models.StageState.stage_type == stage_type).order_by(models.StageState.idx)
    ).scalars().first()
    if not st or st.status == status:
        return
    st.status = status
    if error is not None:
        st.meta = {**(st.meta or {}), "error": error}
    else:
        meta = {**(st.meta or {})}
        meta.pop("error", None)   # 进入 running 时清掉上次失败遗留的错误信息
        st.meta = meta
    db.commit()


def heal_stuck_running(db: Session) -> int:
    """自愈：清除「孤儿进行中」状态（后端启动时调用）。

    生成类接口入口会立即把对应阶段置 running；若接口中途被中断
    （后端重启 / 进程退出，唯一的事故源），后续推进永远不执行，
    阶段就永久停在 running——前端看板表现为多个卡片一直「进行中」。
    后端重启即任务线程全部清空，因此把全部 running 阶段重置为 pending，
    并把已无任何 running 阶段却仍标 running 的实例校正回 pending，
    用户重新操作即可正常推进；success / skipped / pending_review 等终态不受影响。
    """
    fixed = 0
    running_stages = db.execute(select(models.StageState).where(
        models.StageState.status == "running")).scalars().all()
    for st in running_stages:
        if st.enabled:
            st.status = "pending"
            fixed += 1
    # 实例级校正：没有 running 阶段却标 running 的实例 -> 视实例未在运行
    for r in db.execute(select(models.WorkflowRun).where(
            models.WorkflowRun.status == "running")).scalars():
        any_running = db.execute(select(models.StageState.id).where(
            models.StageState.run_id == r.id,
            models.StageState.status == "running", models.StageState.enabled == True).limit(1)).scalar_one_or_none()  # noqa: E712
        if not any_running:
            all_done = db.execute(select(models.StageState.id).where(
                models.StageState.run_id == r.id,
                models.StageState.enabled == True,  # noqa: E712
                models.StageState.status.not_in(("success", "skipped"))).limit(1)).scalar_one_or_none()
            r.status = "success" if not all_done else "pending"
            fixed += 1
    db.commit()
    return fixed
