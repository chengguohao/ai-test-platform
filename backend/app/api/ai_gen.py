"""AI 生成 / 评审闭环 API（Skill + MCP 实据）。"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, storage
from app.services.ai_llm import model_label
from app.db import get_db
from app.services import auto_fix as auto_fix_svc
from app.services import auto_gen as auto_gen_svc
from app.services import case_export, case_gen as case_gen_svc
from app.services import ai_llm, task_progress
from app.services.skill_engine import run_code_skill, run_json_skill
from app.services.skills import SKILLS, get_skill_detail, list_skills

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------- 任务过程进度（前端轮询「思考过程」） ----------------
@router.get("/progress/{task_key}")
def get_progress(task_key: str):
    """长任务过程步骤轮询：key 形如 case_gen:{run_id} / auto_gen:{run_id} / execute:{run_id}。"""
    return task_progress.get(task_key)


# ---------------- 执行失败 AI 修复闭环 ----------------
class AutoFixIn(BaseModel):
    run_id: int
    execution_id: int = 0   # 0=自动取该实例最新一次执行记录
    project_id: int = 0     # 可选：项目绑定模型时优先用它反查配置


def _auto_fix_async(run_id: int, execution_id: int, project_id: int) -> None:
    """后台线程：AI 分析 → 重生成 → 自动重新执行测试（全程进度见 auto_gen:{run_id}）。"""
    from app.db import SessionLocal
    from app.services import auto_fix as auto_fix_svc
    from app.services import task_progress as _tp

    db = SessionLocal()
    pkey = f"auto_gen:{run_id}"
    try:
        llm_cfg = (_project_llm_config(db, project_id) if project_id
                   else _run_id_llm_config(db, run_id))
        auto_fix_svc.run_fix(db, run_id, execution_id, llm_config=llm_cfg, auto_execute=True)
    except Exception as e:  # noqa: BLE001
        try:
            _tp.report(pkey, f"[错误] {e}")
            _tp.finish(pkey, error=str(e))
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


@router.post("/auto-fix")
def auto_fix(body: AutoFixIn, db: Session = Depends(get_db)):
    """Allure/pytest 执行失败后：AI 分析根因 → 打回 → 自动重跑自动化生成 → 自动重新执行测试。

    改为后台线程模式：接口立即返回（避免同步执行 1~5 分钟导致前端请求超时卡死），
    过程与结果通过 GET /api/ai/progress/auto_gen:{run_id} 轮询获取。
    """
    import threading

    # 快速存在性校验（详细业务校验在后台线程内做，失败会写进进度 error）
    run = db.get(models.WorkflowRun, body.run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    if body.execution_id:
        rec = db.get(models.ExecutionRun, body.execution_id)
        if not rec or rec.run_id != body.run_id:
            raise HTTPException(404, "执行记录不存在")
    # 修复上限预校验（后台线程内还有一道，这里先拦住让用户立即看到明确提示）
    st_auto = db.execute(select(models.StageState).where(
        models.StageState.run_id == body.run_id,
        models.StageState.stage_type == "auto_gen").limit(1)).scalar_one_or_none()
    if st_auto and (st_auto.meta or {}).get("fix_rounds", 0) >= 3:
        raise HTTPException(422, "已自动修复 3 轮仍失败，请人工介入检查（日志见执行工件），"
                                 "系统不再自动重跑")
    # 同一实例的修复已在跑 → 拒绝重复启动
    cur = task_progress.get(f"auto_gen:{body.run_id}")
    if cur.get("exists") and not cur.get("done"):
        raise HTTPException(422, "该实例的 AI 修复正在进行中，请等待完成")
    threading.Thread(
        target=_auto_fix_async,
        args=(body.run_id, body.execution_id, body.project_id),
        daemon=True, name=f"auto-fix-{body.run_id}",
    ).start()
    return {"message": "AI 修复已启动：将自动分析根因、重新生成脚本并重新执行测试，"
                       "过程见下方思考过程面板", "started": True}


# ---------------- 一键跑工作流 ----------------
class AutoRunIn(BaseModel):
    run_id: int
    project_id: int


@router.post("/auto-run")
def auto_run(body: AutoRunIn, db: Session = Depends(get_db)):
    """一键执行：自动完成 生成用例→评审→自动化生成→执行测试→失败 AI 修复 全流程。

    前置条件：已上传需求文档且已生成需求摘要（否则 422 提示）。
    模式：有接口文档=full（全自动）；仅有需求文档=cases_only（自动执行到用例评审为止）。
    后台线程执行，进度通过 GET /api/ai/progress/auto_run:{run_id} 轮询。
    """
    import threading

    from app.services import auto_run as auto_run_svc

    run = db.get(models.WorkflowRun, body.run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    if run.status == "success":
        # 仅需求模式完成的实例（自动化生成/执行阶段为 skipped）：上传接口文档后允许续跑全流程
        stages = db.execute(select(models.StageState).where(
            models.StageState.run_id == body.run_id)).scalars().all()
        tail_skipped = any(s.stage_type in ("auto_gen", "execute") and s.status == "skipped"
                           for s in stages)
        if not tail_skipped:
            raise HTTPException(422, "该流程实例已完成；如需重跑请新建流程实例")
    ok, msg, mode = auto_run_svc.check_ready(db, body.run_id)
    if not ok:
        raise HTTPException(422, msg)
    cur = task_progress.get(f"auto_run:{body.run_id}")
    if cur.get("exists") and not cur.get("done"):
        raise HTTPException(422, "一键执行正在进行中，请等待完成")
    auto_run_svc.start(body.run_id, body.project_id, mode=mode)
    if mode == "cases_only":
        return {"message": "一键执行已启动（仅需求文档模式）：自动生成用例并评审；"
                           "上传接口文档后可再次一键执行完成自动化生成与执行测试",
                "started": True, "mode": mode}
    return {"message": "一键执行已启动：生成用例 → 自动评审 → 自动化生成 → 执行测试（失败将自动 AI 修复）",
            "started": True, "mode": mode}


# ---------------- 流程完成总结（AI 文字总结） ----------------
class RunSummaryIn(BaseModel):
    run_id: int
    force: bool = False   # True=忽略缓存重新生成


@router.post("/run-summary")
def run_summary(body: RunSummaryIn, db: Session = Depends(get_db)):
    """所有阶段完成后：汇总全流程数据 → LLM 生成一段人话总结（缓存为工件，不重复调模型）。"""
    run = db.get(models.WorkflowRun, body.run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    stages = db.execute(select(models.StageState).where(
        models.StageState.run_id == body.run_id).order_by(models.StageState.idx)).scalars().all()
    if not stages or not all(s.status in ("success", "skipped") for s in stages):
        raise HTTPException(422, "流程尚未全部完成（存在未完成阶段），暂不能生成执行总结")

    # 缓存：已有 run_summary 工件且不强制刷新 → 直接返回
    cached = (db.query(models.Artifact).filter(
        models.Artifact.run_id == body.run_id, models.Artifact.type == "run_summary")
        .order_by(models.Artifact.id.desc()).first())
    if cached and cached.file_path and not body.force:
        from pathlib import Path as _P
        if _P(cached.file_path).exists():
            return {"message": "已生成过总结（缓存）", "summary": _P(cached.file_path)
                    .read_text(encoding="utf-8", errors="ignore"), "cached": True}

    # 汇总全流程数据喂给 LLM
    case_sets = db.execute(select(models.CaseSet).where(
        models.CaseSet.run_id == body.run_id).order_by(models.CaseSet.version)).scalars().all()
    executions = db.execute(select(models.ExecutionRun).where(
        models.ExecutionRun.run_id == body.run_id).order_by(models.ExecutionRun.id)).scalars().all()
    reviews = db.execute(select(models.ReviewRecord).where(
        models.ReviewRecord.run_id == body.run_id)).scalars().all()
    n_artifacts = db.execute(select(models.Artifact).where(
        models.Artifact.run_id == body.run_id)).scalars().all()

    latest_tree = case_sets[-1].content if case_sets else {}
    n_groups = len(latest_tree.get("groups", []))
    n_cases = sum(len(g.get("cases", [])) for g in latest_tree.get("groups", []))
    fix_rounds = 0
    for st in stages:
        if st.stage_type == "auto_gen":
            fix_rounds = (st.meta or {}).get("fix_rounds", 0)
    exec_lines = [{"id": e.id, "status": e.status, "summary": {k: v for k, v in (e.summary or {}).items()
                    if k != "cases"}} for e in executions]
    # 双口径：
    #   design = 用例集设计覆盖数（生成/评审过的用例树）；
    #   run    = 最近一次执行的 pytest 实际节点数（执行报告口径，可能因多角色展开/skip 与 design 不同）。
    last_exec_summary = executions[-1].summary or {} if executions else {}
    exec_total = last_exec_summary.get("total", 0)
    exec_passed = last_exec_summary.get("passed", 0)

    payload = {
        "实例": {"id": run.id, "名称": run.name, "状态": run.status,
                "创建时间": run.created_at.isoformat()},
        "阶段": [{"名称": s.stage_name, "类型": s.stage_type, "状态": s.status} for s in stages],
        "用例集": {"版本数": len(case_sets),
                   "最新版本": case_sets[-1].version if case_sets else 0,
                   "最新状态": case_sets[-1].status if case_sets else "",
                   "模块": latest_tree.get("module", ""),
                   "功能分组数": n_groups, "用例总数": n_cases,
                   "类型": latest_tree.get("case_type", "")},
        "评审": {"评审记录数": len(reviews),
                 "打回次数": sum(1 for r in reviews if r.result == "returned")},
        "执行": {"总轮次": len(executions), "各轮结果": exec_lines,
                 "最近一次执行": {"实际执行用例数": exec_total, "通过数": exec_passed},
                 "AI自动修复轮数": fix_rounds},
        "工件": {"总数": len(n_artifacts)},
    }
    p = db.get(models.Project, run.project_id)
    llm_cfg = _project_llm_config(db, run.project_id)
    messages = [
        {"role": "system", "content":
            "你是测试项目负责人。基于提供的全流程数据，用中文写一段 150~300 字的执行总结，"
            "面向测试经理汇报本次测试流程。要求：①先说整体结论（通过/经历几轮）；"
            "②点出用例覆盖情况（模块/分组/用例数——注意区分「用例集设计的用例数」与「实际执行的用例数」："
            "如设计了 N 条、实际执行 M 条、通过 K 条，两者可能不同，须如实分别表述，不要混为一谈）；"
            "③执行情况（几轮、失败原因、是否经 AI 自动修复）；"
            "④如有打回/修复过程，说明闭环效果；⑤最后一句风险或建议。只输出总结正文，不要标题和格式化符号。"},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    try:
        text = ai_llm.chat(messages, llm_config=llm_cfg)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"AI 总结生成失败：{e}")

    # 总结存为工件（缓存 + 可下载）
    project = p.name if p else f"p{run.id}"
    path = storage.save_text(project, run.id, "run_summary.txt", text, subdir="summary")
    db.add(models.Artifact(run_id=run.id, stage_type="execute", type="run_summary",
                           name="执行总结.txt", file_path=str(path),
                           source={"source": "ai", "run_status": run.status}))
    db.commit()
    return {"message": "执行总结已生成", "summary": text, "cached": False}


def _project_llm_config(db: Session, project_id: int | None) -> dict | None:
    """查项目绑定的 AI 模型配置；未绑定/被禁用/配置不存在时返回 None（走全局 .env 默认）。"""
    if not project_id:
        return None
    p = db.get(models.Project, project_id)
    if not p or not p.ai_model_id:
        return None
    m = db.get(models.AiModelConfig, p.ai_model_id)
    if not m or not m.enabled:
        return None
    return {"base_url": m.base_url, "api_key": m.api_key,
            "model": m.model, "temperature": m.temperature, "name": m.name}


def _run_id_llm_config(db: Session, run_id: int) -> dict | None:
    """由流程实例反查项目绑定的模型配置（summary 等只有 run_id 的接口用）。"""
    run = db.get(models.WorkflowRun, run_id)
    return _project_llm_config(db, run.project_id) if run else None


@router.get("/skills")
def skills():
    return list_skills()


@router.get("/skills/{skill_id}")
def skill_detail(skill_id: str):
    detail = get_skill_detail(skill_id)
    if not detail:
        raise HTTPException(404, f"未注册的 Skill: {skill_id}，可选 {sorted(SKILLS)}")
    return detail


# ---------------- 需求摘要 ----------------
class SummaryIn(BaseModel):
    run_id: int


@router.post("/summary")
def summary(body: SummaryIn, db: Session = Depends(get_db)):
    from app.api.workflow import mark_stage_status
    llm_cfg = _run_id_llm_config(db, body.run_id)
    mark_stage_status(db, body.run_id, "requirement", "running")
    try:
        out = case_gen_svc.summarize(db, body.run_id, llm_config=llm_cfg)
    except Exception as e:  # noqa: BLE001
        mark_stage_status(db, body.run_id, "requirement", "failed", error=str(e))
        raise HTTPException(400, str(e))
    # 持久化摘要：① 写入 requirement 阶段 meta（抽屉重开 / 刷新页面回显）
    st = db.execute(select(models.StageState).where(
        models.StageState.run_id == body.run_id,
        models.StageState.stage_type == "requirement").order_by(models.StageState.idx)
    ).scalars().first()
    if st:
        st.meta = {**(st.meta or {}), "summary": out}
    # ② 存为 JSON 工件（可下载、有后缀），文件名带时间戳避免覆盖历史摘要
    run = db.get(models.WorkflowRun, body.run_id)
    p = db.get(models.Project, run.project_id) if run else None
    project = p.name if p else f"p{body.run_id}"
    ts = time.strftime("%Y%m%d_%H%M%S")
    text = json.dumps(out, ensure_ascii=False, indent=2)
    path = storage.save_text(project, body.run_id, f"requirement_summary_{ts}.json",
                             text, subdir="summary")
    # 摘要工件版本递增（默认 1，每次都 v1 会导致无法区分第几次生成）
    max_ver = db.execute(select(models.Artifact.version).where(
        models.Artifact.run_id == body.run_id,
        models.Artifact.type == "requirement_summary")).scalars().all()
    db.add(models.Artifact(run_id=body.run_id, stage_type="requirement",
                           type="requirement_summary", name="需求摘要.json",
                           file_path=str(path),
                           version=max(max_ver, default=0) + 1,
                           source={"source": "skill", "skill": "requirement_summary"}))
    db.commit()
    # 摘要生成完成 -> 自动推进 requirement 阶段为 success（过守卫）并启动下一阶段
    # 守卫失败不阻塞摘要返回（通常通过：requirement 工件已存在，summarize 内部已校验）
    from app.api.workflow import complete_stage_by_type
    try:
        complete_stage_by_type(db, body.run_id, "requirement")
    except HTTPException:
        pass
    return {"summary": out, "model": model_label(llm_cfg)}


# ---------------- 生成用例 ----------------
class GenIn(BaseModel):
    run_id: int
    project: str = ""
    evidence: dict | None = None   # MCP/URL 拉到的实据
    case_type: str = "business"    # business=业务功能用例；api=接口测试用例


@router.post("/generate-cases")
def generate_cases(body: GenIn, db: Session = Depends(get_db)):
    from app.api.workflow import mark_stage_status, complete_stage_by_type
    mark_stage_status(db, body.run_id, "case_gen", "running")
    llm_cfg = _run_id_llm_config(db, body.run_id)
    try:
        out = case_gen_svc.generate_cases(db, body.run_id, body.project or f"p{body.run_id}",
                                          evidence=body.evidence, case_type=body.case_type,
                                          llm_config=llm_cfg)
    except Exception as e:  # noqa: BLE001
        mark_stage_status(db, body.run_id, "case_gen", "failed", error=str(e))
        raise HTTPException(400, str(e))
    # 用例集已生成 -> 同步生成用例阶段状态：
    # 新流程置 pending_review（待评审，不自动完成），全部评审通过后由 sync 推进到下一步
    from app.api.workflow import sync_case_gen_status
    sync_case_gen_status(db, body.run_id)
    return {"message": "用例生成成功", "data": out, "model": model_label(llm_cfg)}


# ---------------- 用例导出（XMind / Excel） ----------------
class ExportIn(BaseModel):
    run_id: int
    format: str = "xmind"   # xmind / excel
    project: str = ""
    case_type: str = ""     # business/api；空=导出最新任意类型用例集（旧评审页兼容）


def _pick_case_set(db: Session, run_id: int, case_type: str = ""):
    """按类型挑最新用例集：case_type 非空时只匹配 gen_meta.case_type 相同的；空则取最新任意。"""
    rows = db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id)\
        .order_by(models.CaseSet.version.desc()).all()
    if not case_type:
        return rows[0] if rows else None
    return next((c for c in rows if (c.gen_meta or {}).get("case_type") == case_type), None)


@router.post("/export")
def export_cases(body: ExportIn, db: Session = Depends(get_db)):
    cs = _pick_case_set(db, body.run_id, body.case_type)
    if not cs:
        suffix = f"（{body.case_type}）" if body.case_type else ""
        raise HTTPException(404, f"尚无{suffix}用例集，请先生成用例")
    project = body.project or f"p{body.run_id}"
    if body.format == "excel":
        path = case_export.export_excel(cs.content, storage.workspace_for(project, body.run_id) / "cases" / "cases.xlsx")
        atype, name, ext = "case_excel", "测试用例.xlsx", "xlsx"
    else:
        # XMind 根主题 = 本次需求名称（取最新需求工件名，去掉「需求-」前缀与扩展名）
        root_title = None
        req_art = (db.query(models.Artifact).filter(
            models.Artifact.run_id == body.run_id, models.Artifact.type == "requirement")
            .order_by(models.Artifact.id.desc()).first())
        if req_art and req_art.name:
            from pathlib import Path as _P
            stem = _P(req_art.name).stem
            for prefix in ("需求-", "需求"):
                if stem.startswith(prefix) and len(stem) > len(prefix):
                    stem = stem[len(prefix):]
                    break
            root_title = stem or None
        path = case_export.export_xmind(cs.content,
                                        storage.workspace_for(project, body.run_id) / "cases" / "cases.xmind",
                                        root_title=root_title)
        atype, name, ext = "case_xmind", "测试用例.xmind", "xmind"
    art = models.Artifact(run_id=body.run_id, stage_type="case_gen", type=atype,
                          name=name, file_path=str(path), version=cs.version,
                          source={"source": "export", "format": body.format, "case_type": body.case_type})
    db.add(art)
    db.commit()
    db.refresh(art)
    return {"message": "导出成功", "artifact_id": art.id, "name": name, "format": body.format}


# ---------------- 评审：通过 / 打回 / 重传 ----------------
class ReviewIn(BaseModel):
    run_id: int
    result: str                  # approved / returned
    reason: str = ""
    action: str = ""             # regenerate / reupload
    reviewer: str = ""
    case_type: str = ""          # 按类型批准（business/api）；空=最新任意用例集（旧评审页兼容）


@router.post("/review")
def review(body: ReviewIn, db: Session = Depends(get_db)):
    if body.result == "approved":
        cs = _pick_case_set(db, body.run_id, body.case_type)
        if not cs:
            raise HTTPException(404, "尚无用例集，请先生成用例")
        cs.status = "approved"
        db.add(models.ReviewRecord(run_id=body.run_id, result="approved",
                                   reviewer=body.reviewer))
        db.commit()
        # 评审通过后同步生成用例阶段：新流程全部类型评完自动推进到下一步，未评完保持待评审
        from app.api.workflow import sync_case_gen_status
        sync_case_gen_status(db, body.run_id)
        return {"message": "评审通过，用例集已批准", "status": "approved"}
    # 打回：仍针对最新用例集（打回不区分类型，走旧评审闭环）
    cs = (db.query(models.CaseSet).filter(models.CaseSet.run_id == body.run_id)
          .order_by(models.CaseSet.version.desc()).first())
    if not cs:
        raise HTTPException(404, "尚无用例集")
    if body.result == "returned":
        if not body.reason.strip():
            raise HTTPException(422, "打回必须填写原因")
        cs.status = "returned"
        db.add(models.ReviewRecord(run_id=body.run_id, result="returned",
                                   reason=body.reason, action=body.action,
                                   reviewer=body.reviewer))
        # 打回闭环：把「生成用例」阶段回退到 returned，前端引导用户回到生成用例阶段按原因重新生成
        from app import models as _m
        from sqlalchemy import select as _sel
        st_cg = db.execute(_sel(_m.StageState).where(
            _m.StageState.run_id == body.run_id,
            _m.StageState.stage_type == "case_gen").limit(1)).scalar_one_or_none()
        if st_cg:
            st_cg.status = "returned"
            st_cg.meta = {**(st_cg.meta or {}), "return_reason": body.reason}
        run = db.get(_m.WorkflowRun, body.run_id)
        if run:
            run.status = "returned"
        db.commit()
        return {"message": "已打回，请回到「生成用例」阶段按原因重新生成",
                "status": "returned", "reason": body.reason}
    raise HTTPException(422, "result 只支持 approved / returned")


class RegenerateIn(BaseModel):
    run_id: int
    project: str = ""
    reason: str = ""
    evidence: dict | None = None
    case_type: str = "business"


@router.post("/regenerate")
def regenerate(body: RegenerateIn, db: Session = Depends(get_db)):
    """打回后按原因重新生成（reason 作为上下文传给 skill）。"""
    from app.api.workflow import mark_stage_status
    mark_stage_status(db, body.run_id, "case_gen", "running")
    try:
        out = case_gen_svc.generate_cases(db, body.run_id, body.project or f"p{body.run_id}",
                                          evidence=body.evidence, case_type=body.case_type,
                                          llm_config=_run_id_llm_config(db, body.run_id))
        # 重新生成后同步生成用例阶段：回到待评审（未全通过）或直接推进（全通过）
        from app.api.workflow import sync_case_gen_status
        sync_case_gen_status(db, body.run_id)
        return {"message": "已按打回原因重新生成", "data": out}
    except Exception as e:  # noqa: BLE001
        mark_stage_status(db, body.run_id, "case_gen", "failed", error=str(e))
        raise HTTPException(400, str(e))


@router.get("/case-sets/{run_id}")
def case_sets(run_id: int, db: Session = Depends(get_db)):
    rows = db.execute(select(models.CaseSet).where(models.CaseSet.run_id == run_id)
                      .order_by(models.CaseSet.version.desc())).scalars().all()
    return [{"id": r.id, "version": r.version, "status": r.status, "content": r.content,
             "gen_meta": r.gen_meta, "created_at": r.created_at.isoformat()} for r in rows]


# ---------------- 自动化用例增量生成 ----------------
class AutoGenIn(BaseModel):
    run_id: int
    project_id: int


@router.post("/auto-generate")
def auto_generate(body: AutoGenIn, db: Session = Depends(get_db)):
    """全量覆盖生成自动化用例（后台线程）。

    每次点击 = 基于最新需求 + 接口文档重新生成全部用例并覆盖旧脚本；
    接口立即返回，过程/结果通过 GET /api/ai/progress/auto_gen:{run_id} 轮询 + 阶段 meta 实时显示。
    """
    import threading

    run = db.get(models.WorkflowRun, body.run_id)
    if not run:
        raise HTTPException(404, "流程实例不存在")
    # 生成进行中 → 拒绝重复启动（避免并发重跑）
    cur = task_progress.get(f"auto_gen:{body.run_id}")
    if cur.get("exists") and not cur.get("done"):
        raise HTTPException(422, "自动化生成正在进行中，请等待完成")
    threading.Thread(
        target=_auto_generate_async,
        args=(body.run_id, body.project_id),
        daemon=True, name=f"auto-gen-{body.run_id}",
    ).start()
    return {"message": "自动化生成已启动：全量重新生成用例，过程见下方思考过程面板", "started": True}


def _auto_generate_async(run_id: int, project_id: int) -> None:
    """后台线程：全量覆盖生成自动化用例（进度见 auto_gen:{run_id}）。"""
    from app.db import SessionLocal
    from app.api.workflow import complete_stage_by_type, mark_stage_status
    from app.services import task_progress as _tp

    db = SessionLocal()
    pkey = f"auto_gen:{run_id}"
    try:
        p = db.get(models.Project, project_id)
        if not p:
            raise ValueError(f"项目不存在: {project_id}")
        # 快速失败校验：已上传接口文档时必须有「已评审通过」的接口测试用例集，避免白跑 LLM
        api_art = db.execute(select(models.Artifact).where(
            models.Artifact.run_id == run_id, models.Artifact.type == "api_doc")
            .limit(1)).scalar_one_or_none()
        if api_art:
            approved_api = next((c for c in db.query(models.CaseSet).filter(
                models.CaseSet.run_id == run_id,
                models.CaseSet.status == "approved").all()
                if (c.gen_meta or {}).get("case_type") == "api"), None)
            if not approved_api:
                _tp.report(pkey, "[校验] 已上传接口文档，但接口测试用例尚未评审通过——自动终止，请先在生成用例页评审接口用例")
                mark_stage_status(db, run_id, "auto_gen", "failed",
                                  error="接口测试用例未评审通过：请在生成用例页选中「接口测试用例」后点「评审通过」")
                _tp.finish(pkey, error="接口测试用例未评审通过")
                return
        mark_stage_status(db, run_id, "auto_gen", "running")
        out = auto_gen_svc.generate(db, run_id, p.engine_config or {}, p.name,
                                    llm_config=_project_llm_config(db, project_id))
        # 持久化生成结果到 auto_gen 阶段 meta：抽屉重开 / 刷新页面都能回显
        st = db.execute(select(models.StageState).where(
            models.StageState.run_id == run_id,
            models.StageState.stage_type == "auto_gen").order_by(models.StageState.idx)
        ).scalars().first()
        if st:
            new_meta = {**(st.meta or {}), "auto_result": out}
            # 清掉历史 failed 状态遗留的 error 字段，避免 UI 误显示失败原因
            new_meta.pop("error", None)
            st.meta = new_meta
            db.commit()
        # 推进 auto_gen 阶段状态为 success（走守卫，已 success 幂等；守卫失败不阻塞生成结果返回）
        try:
            complete_stage_by_type(db, run_id, "auto_gen")
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        try:
            mark_stage_status(db, run_id, "auto_gen", "failed", error=str(e))
            _tp.report(pkey, f"[错误] {e}")
            _tp.finish(pkey, error=str(e))
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


# ---------------- 独立 Skill 卡片：运行任意 Skill 并存工件 ----------------
class RunSkillIn(BaseModel):
    run_id: int
    skill_id: str
    inputs: dict = {}
    project: str = ""


@router.post("/run-skill")
def run_skill(body: RunSkillIn, db: Session = Depends(get_db)):
    spec = SKILLS.get(body.skill_id)
    if not spec:
        raise HTTPException(404, f"未注册的 Skill: {body.skill_id}，可选 {sorted(SKILLS)}")
    try:
        if spec.kind == "json":
            out = run_json_skill(spec, body.inputs or {},
                                 llm_config=_run_id_llm_config(db, body.run_id))
            text = json.dumps(out["result"], ensure_ascii=False, indent=2)
            meta = {"attempts": out.get("attempts")}
        else:
            text = run_code_skill(spec, body.inputs or {},
                                  llm_config=_run_id_llm_config(db, body.run_id))
            meta = {}
        fname = f"skill_{spec.id}_{int(time.time())}.txt"
        path = storage.save_text(body.project or f"p{body.run_id}", body.run_id, fname, text, subdir="skills")
        db.add(models.Artifact(run_id=body.run_id, stage_type="skill", type="skill_result",
                               name=f"Skill {spec.name} 结果", file_path=str(path), version=1,
                               source={"source": "skill", "skill": spec.id}))
        db.commit()
        return {"message": f"Skill[{spec.name}] 执行完成", "skill": spec.id, "text": text[:200000], "meta": meta}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
