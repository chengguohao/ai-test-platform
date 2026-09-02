"""执行与报告 API：环境自检 → pytest（后台线程）→ Allure → 失败分级。

pytest 一次最长可跑 30 分钟，绝不能在 HTTP 请求里同步等待：
POST /run 立即返回 execution_id（status=running），后台线程跑完回写记录，
前端轮询 GET /detail/{execution_id} 拿进度与结果。
全程写 workspaces/{project}/{run_id}/logs/execute.log（pytest + Allure 输出），并注册为可下载工件。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, storage
from app.config import workspace_for
from app.db import SessionLocal, get_db
from app.services import executor, task_progress

router = APIRouter(prefix="/api/exec", tags=["execution"])


@router.post("/env-check")
def env_check(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return executor.env_check(p.engine_config or {})


class RunIn(BaseModel):
    run_id: int
    module: str
    project_id: int
    target_file: str = ""   # 用户指定目标脚本文件（相对 pytest 项目根）；空=跑整个模块目录


def _execute_async(execution_id: int, project_id: int, run_id: int, module: str,
                   target_file: str = "") -> None:
    """后台线程：跑 pytest + Allure，把结果回写到执行记录（独立 DB 会话）。"""
    db = SessionLocal()
    log_path = None
    pkey = f"execute:{run_id}"   # 前端轮询「思考过程/执行进度」用
    task_progress.start(pkey)
    try:
        p = db.get(models.Project, project_id)
        rec = db.get(models.ExecutionRun, execution_id)
        if not p or not rec:
            return
        engine = p.engine_config or {}
        ws = workspace_for(p.name, run_id)

        def _log(line: str) -> None:
            nonlocal log_path
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            log_path = storage.append_log(p.name, run_id, "execute", f"[{ts}] {line}\n")
            task_progress.report(pkey, line)   # 同步喂给前端轮询

        _log(f"===== 执行开始 #{execution_id}（module={module}, "
             + (f"目标文件={target_file}, " if target_file else "")
             + f"工作区={ws}）=====")
        env = rec.env_check or {}
        if env.get("items"):
            bad = [i for i in env["items"] if not i.get("ok")]
            _log(f"[环境自检] {'全部通过' if not bad else '存在问题: ' + '; '.join(i.get('detail', '') for i in bad)}")
        try:
            result = executor.run_pytest(engine, module, ws, target_file=target_file)
            _log(f"[pytest] 状态={result.get('status')}，摘要={result.get('summary')}")
            if result.get("error_log"):
                _log("[pytest 输出（末尾 4000 字）]\n" + result["error_log"][-4000:])
            report_dir = ws / "allure-report"
            if result.get("allure_dir") and Path(result["allure_dir"]).exists():
                try:
                    _, allure_out = executor.generate_allure(Path(result["allure_dir"]), report_dir)
                    result["report_dir"] = str(report_dir)
                    _log(f"[allure] 报告已生成 → {report_dir}"
                         + (f"\n[allure 输出]\n{allure_out[-3000:]}" if allure_out else ""))
                except Exception as e:  # noqa: BLE001
                    result["report_dir"] = ""
                    result["error_log"] = (result.get("error_log", "")
                                           + f"\n[Allure] {e}")
                    _log(f"[allure] 生成失败：{e}")
            rec.status = result.get("status", "failed")
            rec.summary = result.get("summary", {})
            # 逐用例明细（中文结构化），供平台直接展示，不依赖 Allure 英文报告
            try:
                rec.summary = {**rec.summary,
                               "cases": executor.parse_junit_cases(ws / "junit.xml")}
            except Exception:  # noqa: BLE001
                pass
            rec.allure_dir = result.get("allure_dir", "")
            rec.report_dir = result.get("report_dir", "")
            rec.error_log = result.get("error_log", "")
        except Exception as e:  # noqa: BLE001 任何异常都不能让记录永远停在 running
            rec.status = "failed"
            rec.error_log = (rec.error_log or "") + f"\n[后台执行异常] {e}"
            _log(f"[结果] 后台执行异常：{e}")
        _log(f"[结果] 执行结束 #{execution_id}，状态={rec.status}")
        # 执行日志注册为工件（前端工件列表可直接下载查看）
        if log_path:
            db.add(models.Artifact(run_id=run_id, stage_type="execute", type="exec_log",
                                   name=f"执行日志 #{execution_id}", file_path=str(log_path),
                                   source={"source": "exec_log", "execution_id": execution_id}))
        # 执行阶段实时终态：passed -> success（过守卫推进）；否则 failed（原因写入 meta）。
        # 仅当阶段仍处于 running 时处理——一键执行(auto_run)场景由编排器自行管理阶段状态。
        from app.api.workflow import complete_stage_by_type
        st = db.execute(select(models.StageState).where(
            models.StageState.run_id == run_id,
            models.StageState.stage_type == "execute").order_by(models.StageState.idx)
        ).scalars().first()
        if st and st.status == "running":
            if rec.status == "passed":
                try:
                    complete_stage_by_type(db, run_id, "execute")
                except Exception as e:  # noqa: BLE001
                    st.status = "failed"
                    st.meta = {**(st.meta or {}), "error": f"执行已通过但阶段推进失败：{e}"}
                    db.commit()
            else:
                st.status = "failed"
                st.meta = {**(st.meta or {}), "error": f"最近一次执行状态为 {rec.status}，未通过"}
                # 同步实例整体状态：手动执行失败要反映到 run.status，
                # 否则实例停留在 success 会导致前端「一键执行」按钮被隐藏
                run_rec = db.get(models.WorkflowRun, run_id)
                if run_rec:
                    run_rec.status = "failed"
                db.commit()
        db.commit()
        task_progress.finish(pkey)
    finally:
        db.close()


@router.post("/run")
def run(body: RunIn, db: Session = Depends(get_db)):
    p = db.get(models.Project, body.project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    engine = p.engine_config or {}
    ws = workspace_for(p.name, body.run_id)
    # 先落一条 running 记录，再交给后台线程执行
    rec = models.ExecutionRun(
        run_id=body.run_id, status="running",
        env_check=executor.env_check(engine),
        summary={}, allure_dir=str(ws / "allure-results"),
        report_dir="", error_log="",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    # 执行阶段实时状态：提交即置 running，前端看板立刻显示「进行中」
    from app.api.workflow import mark_stage_status
    mark_stage_status(db, body.run_id, "execute", "running")
    threading.Thread(
        target=_execute_async,
        args=(rec.id, body.project_id, body.run_id, body.module, body.target_file),
        daemon=True, name=f"pytest-exec-{rec.id}",
    ).start()
    return {"execution_id": rec.id, "result": {"status": "running",
                                               "message": "已提交后台执行，请轮询 /api/exec/detail/{}".format(rec.id)}}


@router.get("/runs/{run_id}")
def list_runs(run_id: int, db: Session = Depends(get_db)):
    return db.execute(select(models.ExecutionRun).where(
        models.ExecutionRun.run_id == run_id).order_by(models.ExecutionRun.id.desc())).scalars().all()


@router.get("/detail/{execution_id}")
def detail(execution_id: int, db: Session = Depends(get_db)):
    r = db.get(models.ExecutionRun, execution_id)
    if not r:
        raise HTTPException(404, "执行记录不存在")
    return {
        "id": r.id, "run_id": r.run_id, "status": r.status,
        "env_check": r.env_check, "summary": r.summary,
        "allure_dir": r.allure_dir, "report_dir": r.report_dir,
        "error_log": r.error_log,
    }
