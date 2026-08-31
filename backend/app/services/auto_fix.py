"""执行失败 AI 修复闭环：失败日志+当前脚本 → AI 根因分析 → 打回 → 自动重跑自动化生成。

闭环流程（对齐用户确认的方案）：
    执行失败 → AI 分析根因（auto_fix skill）→ auto_gen 阶段置 returned（带分析结论）
    → 自动调用 auto_gen.generate（fix_context=分析指令+失败日志）重新生成脚本
    → 完成后 auto_gen 置 running、execute 置 pending，等用户手工点「执行测试」复验。

防死循环：同一流程实例最多自动修复 3 轮（fix_rounds 计数，存 auto_gen 阶段 meta）。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services import auto_gen as auto_gen_svc
from app.services import task_progress
from app.services.skill_engine import run_json_skill
from app.services.skills import auto_fix as skill_auto_fix

MAX_FIX_ROUNDS = 3


def _stage(db: Session, run_id: int, stage_type: str) -> models.StageState | None:
    return db.execute(select(models.StageState).where(
        models.StageState.run_id == run_id,
        models.StageState.stage_type == stage_type).order_by(models.StageState.idx)
    ).scalars().first()


def run_fix(db: Session, run_id: int, execution_id: int,
            llm_config: dict | None = None, auto_execute: bool = False) -> dict:
    """主入口：AI 分析失败 → 打回 → 自动重新生成自动化脚本。

    auto_execute=True：重生成成功后自动提交执行测试并等待结果（返回 exec_status），
    用户无需手工点「执行测试」；False 时由用户手工复验。
    """
    pkey = f"auto_gen:{run_id}"   # 前端轮询「思考过程」用（与自动生成共用面板）
    task_progress.start(pkey)

    def _step(text: str) -> None:
        task_progress.report(pkey, text)

    # 1. 读失败执行记录（execution_id=0 时自动取该实例最新一次执行）
    if execution_id:
        rec = db.get(models.ExecutionRun, execution_id)
        if not rec or rec.run_id != run_id:
            raise ValueError("执行记录不存在")
    else:
        rec = (db.query(models.ExecutionRun).filter(models.ExecutionRun.run_id == run_id)
               .order_by(models.ExecutionRun.id.desc()).first())
        if not rec:
            raise ValueError("该流程实例尚无执行记录，请先执行测试")
    if rec.status == "running":
        raise ValueError("该执行还在进行中，请等执行结束后再修复")
    if rec.status == "passed":
        raise ValueError("该次执行已通过，无需修复")

    run = db.get(models.WorkflowRun, run_id)
    p = db.get(models.Project, run.project_id) if run else None
    project = p.name if p else f"p{run_id}"

    # 2. 防死循环：修复轮次计数
    st_auto = _stage(db, run_id, "auto_gen")
    rounds = (st_auto.meta or {}).get("fix_rounds", 0) if st_auto else 0
    if rounds >= MAX_FIX_ROUNDS:
        if st_auto:
            st_auto.status = "failed"   # 修复耗尽：给出明确终态，避免停在 running/returned
            db.commit()
        raise ValueError(f"已自动修复 {rounds} 轮仍失败，请人工介入检查（日志见执行工件），"
                         f"系统不再自动重跑（上限 {MAX_FIX_ROUNDS} 轮）")

    # 3. 读当前自动化脚本（最新 auto_file 工件）
    code = ""
    art = (db.query(models.Artifact).filter(
        models.Artifact.run_id == run_id, models.Artifact.type == "auto_file")
        .order_by(models.Artifact.id.desc()).first())
    if art and art.file_path and Path(art.file_path).exists():
        code = Path(art.file_path).read_text(encoding="utf-8", errors="ignore")

    failed_cases = [c for c in (rec.summary or {}).get("cases", [])
                    if c.get("status") not in ("通过", "跳过")]
    _step(f"读取失败执行记录 #{rec.id}：失败/错误 {len(failed_cases)} 条，"
          f"当前脚本 {len(code)} 字符")
    _step("调用 AI 分析失败根因（错误日志 + 失败用例 + 当前脚本）…")

    # 4. AI 根因分析
    inputs = {
        "execution_id": execution_id,
        "status": rec.status,
        "summary": rec.summary or {},
        "failed_cases": failed_cases,
        "error_log": (rec.error_log or "")[-12000:],   # 日志尾部最有价值
        "current_code": code[-40000:],                 # 脚本过长取尾部（测试函数集中在后部）
    }
    try:
        analysis = run_json_skill(skill_auto_fix.SKILL, inputs, llm_config=llm_config)
    except Exception as e:  # noqa: BLE001
        task_progress.finish(pkey, error=f"AI 分析失败：{e}")
        raise
    result = analysis["result"]
    _step(f"AI 分析完成：{result.get('overall_conclusion', '')}")

    # 5. 打回：auto_gen 阶段置 returned，记录分析结论与轮次
    if st_auto:
        st_auto.meta = {**(st_auto.meta or {}), "return_reason": result.get("overall_conclusion", ""),
                        "fix_analysis": result, "fix_rounds": rounds + 1,
                        "fix_execution_id": execution_id}
        st_auto.status = "returned"
        db.commit()
    st_exec = _stage(db, run_id, "execute")
    if st_exec:
        st_exec.status = "returned"
        db.commit()

    # 6. 若有脚本问题 → 自动重跑自动化生成（带修复上下文）
    regen_instructions = result.get("regen_instructions", "")
    if not regen_instructions.strip():
        # AI 判定非脚本问题（疑似系统缺陷）：不打回重生成，提示人工处理
        task_progress.finish(pkey)
        return {"message": "AI 分析完成：失败疑似被测系统真实缺陷，未自动重跑生成。"
                           "请查看分析结论，人工处理后再执行测试。",
                "analysis": result, "regenerated": False, "fix_round": rounds + 1}

    _step("检测到脚本问题，正在按修改指令自动重新生成自动化脚本…")
    fix_context = (f"上一轮执行 #{execution_id} 失败。AI 根因分析结论："
                   f"{result.get('overall_conclusion', '')}\n"
                   f"失败用例与根因：{result.get('root_causes', [])}\n"
                   f"重新生成必须遵循的修改指令：\n{regen_instructions}\n"
                   f"pytest 失败日志（末段）：\n{(rec.error_log or '')[-6000:]}")
    engine = (p.engine_config or {}) if p else {}
    out = auto_gen_svc.generate(db, run_id, engine, project,
                                llm_config=llm_config, fix_context=fix_context)

    # 7. 重生成成功：阶段状态恢复
    if st_auto:
        st_auto.status = "running"
        st_auto.meta = {**(st_auto.meta or {}), "auto_result": out}
        db.commit()
    if st_exec:
        st_exec.status = "pending"
        db.commit()

    # 8. 自动执行测试验证修复效果（可选）
    exec_status = None
    if auto_execute and p:
        _step("脚本已重新生成，自动提交执行测试验证修复效果…")
        from app.services import auto_run  # 延迟导入避免循环
        module = out.get("module") or "module"
        eid = auto_run.submit_execution(db, p, run_id, module)
        er = auto_run.wait_execution(db, eid)
        exec_status = er.status if er else "timeout"
        s = (er.summary or {}) if er else {}
        _step(f"修复后执行完成：状态={exec_status}，"
              f"通过 {s.get('passed', 0)} / 失败 {s.get('failures', 0) + s.get('errors', 0)}")
        if exec_status == "passed":
            # 通过：execute 置 running 等用户核对 Allure 后完成；整个修复闭环结束
            if st_exec:
                st_exec.status = "running"
                db.commit()
            _step("修复验证通过！可打开 Allure 报告核对，确认后完成执行阶段")
        else:
            if st_exec:
                st_exec.status = "failed"
                db.commit()
            _step("修复后执行仍未通过，可再次点击「AI 检查修复」或人工排查")

    task_progress.finish(pkey)
    msg = ("AI 已分析失败原因并自动重新生成自动化脚本。"
           + ("已自动重新执行测试。" if auto_execute else "请人工点击「执行测试」复验。"))
    return {"message": msg,
            "analysis": result, "regenerated": True, "fix_round": rounds + 1,
            "auto_result": out, "exec_status": exec_status}
