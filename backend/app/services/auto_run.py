"""一键跑工作流编排：需求校验 → 生成用例 → 自动评审 → 自动化生成 → 执行 → 失败 AI 修复循环。

全程后台线程执行，进度通过 task_progress（key = auto_run:{run_id}）供前端轮询。
执行阶段复用 execution API 的 _execute_async 后台线程（延迟导入避免循环依赖）。
"""
from __future__ import annotations

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal
from app.services import case_gen as case_gen_svc
from app.services import task_progress
from app.services import auto_gen as auto_gen_svc

MAX_FIX_ROUNDS = 3


def _llm_config(db: Session, project_id: int) -> dict | None:
    """项目绑定的 AI 模型配置（同 ai_gen._project_llm_config，服务内独立实现避免循环导入）。"""
    p = db.get(models.Project, project_id)
    if not p or not p.ai_model_id:
        return None
    m = db.get(models.AiModelConfig, p.ai_model_id)
    if not m or not m.enabled:
        return None
    return {"base_url": m.base_url, "api_key": m.api_key,
            "model": m.model, "temperature": m.temperature}


def _stages(db: Session, run_id: int) -> list[models.StageState]:
    return db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id).order_by(models.StageState.idx)).scalars().all()


def _advance_stage(db: Session, run: models.WorkflowRun, st: models.StageState) -> None:
    """把当前阶段置 success，并推进下一个 pending 阶段为 running（编排内部使用，不做前置校验）。"""
    st.status = "success"
    stages = _stages(db, run.id)
    nxt = next((s for s in stages if s.status == "pending" and s.enabled), None)
    if nxt:
        nxt.status = "running"
        run.current_stage_idx = nxt.idx
        run.status = "running"
    elif all(s.status in ("success", "skipped") for s in stages):
        run.status = "success"
    db.commit()


def check_ready(db: Session, run_id: int) -> tuple[bool, str, str]:
    """一键执行前置校验。返回 (ok, msg, mode)：

    mode 含义：
      full       —— 需求文档 + 接口文档齐全，可全自动跑完（含自动化生成与执行）
      cases_only —— 只有需求文档，自动执行到「生成用例」为止，等用户上传接口文档
    """
    req = db.execute(select(models.Artifact).where(
        models.Artifact.run_id == run_id,
        models.Artifact.type == "requirement").limit(1)).scalar_one_or_none()
    if not req:
        return False, "请先在「需求分析」阶段上传需求文档，再使用一键执行", ""
    # 摘要：requirement 阶段 meta.summary 或 requirement_summary 工件任一存在即可
    st = db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id,
        models.StageState.stage_type == "requirement").limit(1)).scalar_one_or_none()
    has_summary = bool((st.meta or {}).get("summary")) if st else False
    if not has_summary:
        sm = db.execute(select(models.Artifact).where(
            models.Artifact.run_id == run_id,
            models.Artifact.type == "requirement_summary").limit(1)).scalar_one_or_none()
        has_summary = sm is not None
    if not has_summary:
        return False, "请先在「需求分析」阶段生成需求摘要，再使用一键执行", ""
    # 接口文档：有则全流程，无则只跑到用例评审
    api = db.execute(select(models.Artifact).where(
        models.Artifact.run_id == run_id,
        models.Artifact.type == "api_doc").limit(1)).scalar_one_or_none()
    if api:
        return True, "", "full"
    return True, "", "cases_only"


# ---------------- 执行提交与等待（复用 execution API 后台线程） ----------------

def submit_execution(db: Session, p: models.Project, run_id: int, module: str) -> int:
    """创建 running 执行记录并启动后台 pytest 线程，返回 execution_id。"""
    from app.api.execution import _execute_async  # 延迟导入：api 层可能仍在加载
    from app.config import workspace_for
    from app.services import executor

    engine = p.engine_config or {}
    ws = workspace_for(p.name, run_id)
    rec = models.ExecutionRun(
        run_id=run_id, status="running",
        env_check=executor.env_check(engine),
        summary={}, allure_dir=str(ws / "allure-results"),
        report_dir="", error_log="",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    threading.Thread(
        target=_execute_async,
        args=(rec.id, p.id, run_id, module),
        daemon=True, name=f"pytest-exec-{rec.id}",
    ).start()
    return rec.id


def wait_execution(db: Session, execution_id: int, timeout: int = 31 * 60) -> models.ExecutionRun | None:
    """轮询等待执行结束（每 3 秒查一次 DB）。

    注意：SQLite 会话的 SELECT 会开启事务快照，expire_all 也会一直读到旧值（实测脏读），
    必须每轮 rollback 结束当前读事务，才能看到执行线程回写的新状态。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        db.rollback()   # 释放读事务快照，读到执行线程提交的最新状态
        rec = db.get(models.ExecutionRun, execution_id)
        if rec and rec.status != "running":
            return rec
        time.sleep(3)
    return None


# ---------------- 一键编排主流程 ----------------

def start(run_id: int, project_id: int, mode: str = "full") -> None:
    """启动一键执行后台线程（调用前必须先通过 check_ready 校验）。

    mode：full=全自动；cases_only=只执行到用例评审（仅需求文档场景）。
    """
    threading.Thread(
        target=_auto_run_async,
        args=(run_id, project_id, mode),
        daemon=True, name=f"auto-run-{run_id}",
    ).start()


def _auto_run_async(run_id: int, project_id: int, mode: str = "full") -> None:
    db = SessionLocal()
    pkey = f"auto_run:{run_id}"
    task_progress.start(pkey)

    def step(text: str) -> None:
        task_progress.report(pkey, text)

    try:
        run = db.get(models.WorkflowRun, run_id)
        p = db.get(models.Project, project_id)
        if not run or not p:
            step("[错误] 流程实例或项目不存在")
            task_progress.finish(pkey, error="实例/项目不存在")
            return
        if run.status == "success":
            # 仅需求模式完成的实例（自动化生成/执行被跳过）允许续跑全流程；其余已完成实例直接结束
            tail_skipped = any(
                s.stage_type in ("auto_gen", "execute") and s.status == "skipped"
                for s in _stages(db, run_id))
            if not tail_skipped:
                step("流程已完成；如需重跑请新建流程实例")
                task_progress.finish(pkey)
                return

        llm_cfg = _llm_config(db, project_id)
        project = p.name
        if mode == "cases_only":
            step(f"===== 一键执行开始（实例 #{run_id}，项目 {project}，"
                 f"仅需求文档模式：执行到生成用例为止）=====")
            # 仅需求模式：预先把 auto_gen / execute 置为 skipped，
            # 让前端进度条从一开始就以 3/3 为分母（requirement→case_gen），
            # 避免执行中途短暂显示 5/5、到生成用例完成才骤变为 3/3。
            # 若用户后续上传接口文档续跑全流程，会走下面的 is_continuation 分支重置为 pending。
            for s in _stages(db, run_id):
                if s.stage_type in ("auto_gen", "execute") and s.status not in ("success", "skipped"):
                    s.status = "skipped"
            db.commit()
        else:
            step(f"===== 一键执行开始（实例 #{run_id}，项目 {project}，全流程模式）=====")

        # 全流程模式续跑：实例曾以「仅需求模式」完成（自动化生成/执行被跳过），
        # 现在接口文档已就绪 → 重置用例生成/评审（改生成 API 用例）与尾部阶段，从生成用例继续
        if mode == "full":
            changed = False
            is_continuation = any(
                s.stage_type in ("auto_gen", "execute") and s.status == "skipped"
                for s in _stages(db, run_id))
            if is_continuation:
                for s in _stages(db, run_id):
                    if s.stage_type in ("case_gen", "auto_gen", "execute"):
                        s.status = "pending"   # 用例阶段也重置：续跑时改生成 API 用例
                        changed = True
                    elif s.stage_type == "api_doc" and s.status == "skipped":
                        s.status = "success"   # check_ready 已确认接口文档工件存在
                        changed = True
                if run.status == "success":
                    run.status = "running"
                    changed = True
                if changed:
                    step("检测到接口文档已上传：续跑全流程（将生成接口测试用例并执行到 Allure 报告）")
                    db.commit()

        for st in _stages(db, run_id):
            if not st.enabled or st.status in ("success", "skipped"):
                continue
            t = st.stage_type

            if t == "requirement":
                step("① 需求阶段：已具备需求工件与摘要，标记完成")
                _advance_stage(db, run, st)

            elif t == "api_doc":
                api = db.execute(select(models.Artifact).where(
                    models.Artifact.run_id == run_id,
                    models.Artifact.type == "api_doc").limit(1)).scalar_one_or_none()
                if api:
                    step("② 接口文档阶段：已有接口文档工件，标记完成")
                    _advance_stage(db, run, st)
                else:
                    step("② 接口文档阶段：未上传接口文档，自动跳过")
                    st.status = "skipped"
                    db.commit()

            elif t == "case_gen":
                # 仅需求文档 → 业务功能用例（手工执行）；有接口文档 → 接口测试用例（供自动化）
                ctype = "business" if mode == "cases_only" else "api"
                cname = "业务功能" if ctype == "business" else "接口测试"
                step(f"③ 生成用例：AI 正在生成{cname}用例（约 1~2 分钟）…")
                out = case_gen_svc.generate_cases(db, run_id, project,
                                                  case_type=ctype, llm_config=llm_cfg)
                tree = out.get("tree", {})
                n = sum(len(g.get("cases", [])) for g in tree.get("groups", []))
                step(f"③ 用例生成完成：v{out.get('version')}，"
                     f"{len(tree.get('groups', []))} 组 {n} 条{cname}用例")
                # 一键执行=自动评审通过：生成后置 approved，保证 auto_gen 守卫（用例集 approved）通过
                cs = (db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id)
                      .order_by(models.CaseSet.version.desc()).first())
                if cs:
                    cs.status = "approved"
                    db.add(models.ReviewRecord(run_id=run_id, result="approved",
                                               reviewer="一键执行"))
                    db.commit()
                # 仅需求文档模式：到生成用例即完成全部任务——剩余阶段置跳过，实例标记完成
                if mode == "cases_only":
                    for s in _stages(db, run_id):
                        if s.enabled and s.status in ("pending", "running"):
                            s.status = "skipped"
                    run.status = "success"
                    run.current_stage_idx = st.idx
                    db.commit()
                    step("===== 仅需求文档模式执行完成：已生成业务功能用例，本次任务全部完成。"
                         "上传接口文档后可再次一键执行，续跑自动化生成与执行测试 =====")
                    task_progress.finish(pkey)
                    return
                _advance_stage(db, run, st)

            elif t == "auto_gen":
                step("⑤ 自动化生成：AI 正在生成 pytest 脚本（约 1~3 分钟）…")
                out = auto_gen_svc.generate(db, run_id, p.engine_config or {}, project,
                                            llm_config=llm_cfg)
                step(f"⑤ 自动化脚本已生成 → {out.get('target', '')}")
                # 生成结果回显到阶段 meta（抽屉重开可见）
                st.meta = {**(st.meta or {}), "auto_result": out}
                db.commit()
                _advance_stage(db, run, st)

            elif t == "execute":
                st.status = "running"
                db.commit()
                cs = (db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id)
                      .order_by(models.CaseSet.version.desc()).first())
                module = (cs.content or {}).get("module", "module") if cs else "module"
                step(f"⑥ 执行测试：提交 pytest 执行（模块 {module}）…")
                eid = submit_execution(db, p, run_id, module)
                rec = wait_execution(db, eid)
                if not rec:
                    step("⑥ 执行等待超时，请到执行报告页查看结果")
                    st.status = "failed"
                    db.commit()
                    task_progress.finish(pkey, error="执行等待超时")
                    return
                s = rec.summary or {}
                step(f"⑥ 执行完成：状态={rec.status}，"
                     f"通过 {s.get('passed', 0)} / 失败 {s.get('failures', 0) + s.get('errors', 0)}")
                if rec.status == "passed":
                    _advance_stage(db, run, st)
                    step("===== 一键执行完成：全流程通过 =====")
                    task_progress.finish(pkey)
                    return
                # 失败 → AI 修复循环（run_fix 内部会自动重新执行测试）
                from app.services.auto_fix import run_fix  # 延迟导入避免循环
                fixed = False
                for i in range(1, MAX_FIX_ROUNDS + 1):
                    step(f"⑥ 执行未通过，启动第 {i} 轮 AI 修复（分析+重生成+自动执行）…")
                    try:
                        out = run_fix(db, run_id, 0, llm_config=llm_cfg, auto_execute=True)
                    except Exception as e:  # noqa: BLE001 超修复上限等
                        step(f"⑥ AI 修复终止：{e}")
                        break
                    if out.get("exec_status") == "passed":
                        step("⑥ AI 修复后执行通过！")
                        _advance_stage(db, run, st)
                        step("===== 一键执行完成：经 AI 修复后全流程通过 =====")
                        fixed = True
                        break
                    if not out.get("regenerated"):
                        step("⑥ AI 判定失败疑似被测系统真实缺陷，停止自动修复，请人工处理")
                        break
                    step(f"⑥ 第 {i} 轮修复后仍未通过，"
                         + ("继续下一轮修复…" if i < MAX_FIX_ROUNDS else "已达修复上限"))
                if not fixed:
                    st.status = "failed"
                    st_auto2 = _stage(db, run_id, "auto_gen")
                    if st_auto2:
                        st_auto2.status = "failed"   # 修复耗尽：自动化生成同样给出 failed 终态
                    run.status = "failed"
                    db.commit()
                    task_progress.finish(pkey, error="执行未通过（AI 修复后仍未通过或已判定系统缺陷）")
                    return
                task_progress.finish(pkey)
                return

            else:
                # skill / mcp / 自定义阶段：一键模式无输入，自动跳过
                step(f"阶段「{st.stage_name}」（{t}）：一键模式自动跳过")
                st.status = "skipped"
                db.commit()

        # 兜底：全部阶段处理完
        run.status = "success"
        db.commit()
        step("===== 一键执行完成 =====")
        task_progress.finish(pkey)
    except Exception as e:  # noqa: BLE001
        try:
            task_progress.report(pkey, f"[异常] {e}")
            task_progress.finish(pkey, error=str(e))
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
