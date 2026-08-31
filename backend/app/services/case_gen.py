"""用例生成编排：需求摘要 → 用例树生成（Skill + MCP/URL 实据）。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app import models, storage
from app.config import workspace_for
from app.services import task_progress
from app.services.ai_llm import model_label
from app.services.skill_engine import SkillSpec, run_json_skill
from app.services.skills import case_gen as skill_case_gen
from app.services.skills import summary as skill_summary


def _latest_artifact_text(db: Session, run_id: int, atype: str) -> str:
    """取某流程实例最新指定类型工件的内容（文本）。"""
    art = (db.query(models.Artifact)
           .filter(models.Artifact.run_id == run_id, models.Artifact.type == atype)
           .order_by(models.Artifact.version.desc()).first())
    if not art or not art.file_path:
        return ""
    p = Path(art.file_path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def summarize(db: Session, run_id: int, llm_config: dict | None = None) -> dict:
    """需求摘要：读需求工件 → summary skill。"""
    pkey = f"summary:{run_id}"
    task_progress.start(pkey)
    task_progress.report(pkey, "读取最新需求工件…")
    req = _latest_artifact_text(db, run_id, "requirement")
    if not req.strip():
        task_progress.finish(pkey, error="尚未上传需求工件")
        raise ValueError("尚未上传需求工件，无法生成摘要")
    task_progress.report(pkey, f"需求文本 {len(req)} 字符，使用 AI 模型：{model_label(llm_config)}，调用 AI 生成摘要…")
    spec: SkillSpec = skill_summary.SKILL
    try:
        out = run_json_skill(spec, {"requirement": req[:40000]}, llm_config=llm_config)
    except Exception as e:  # noqa: BLE001
        task_progress.finish(pkey, error=str(e))
        raise
    task_progress.report(pkey, "摘要生成完成")
    task_progress.finish(pkey)
    return out


def generate_cases(db: Session, run_id: int, project: str, evidence: dict | None = None,
                   case_type: str = "business", llm_config: dict | None = None) -> dict:
    """生成用例树：需求(必) + 接口/知识库(有则) + 实据(可选) → case_gen skill → 存 CaseSet。

    case_type: business=业务功能用例（默认，供手测）；api=接口测试用例（供自动化直接转换）。
    全程写 workspaces/{project}/{run_id}/logs/case_gen.log（含每轮校验错误），成功失败都注册日志工件。
    """
    started = time.time()
    log_path: Path | None = None
    pkey = f"case_gen:{run_id}"   # 前端轮询「思考过程」用
    task_progress.start(pkey)

    def _log(line: str) -> None:
        nonlocal log_path
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        log_path = storage.append_log(project, run_id, "case_gen", f"[{ts}] {line}\n")
        task_progress.report(pkey, line)   # 同步喂给前端轮询

    def _register_log_artifact() -> None:
        if log_path:
            db.add(models.Artifact(run_id=run_id, stage_type="case_gen", type="gen_log",
                                   name=f"用例生成日志（{case_type}）", file_path=str(log_path),
                                   source={"source": "gen_log", "case_type": case_type}))
            db.commit()

    req = _latest_artifact_text(db, run_id, "requirement")
    api = _latest_artifact_text(db, run_id, "api_doc")
    if not req.strip():
        raise ValueError("尚未上传需求工件，请先完成需求阶段")

    inputs = {
        "requirement": req[:40000],
        "api_doc": api[:60000] if api else "",
        "api_doc_present": bool(api),
        "case_type": case_type,
    }
    spec: SkillSpec = skill_case_gen.SKILL
    _log(f"===== 用例生成开始（case_type={case_type}, skill={spec.id} v{spec.version}）"
         f"输入：需求 {len(req)} 字符，接口文档 {len(api)} 字符 =====")
    _log(f"使用 AI 模型：{model_label(llm_config)}")

    def _hook(attempt: int, errs: list[str]) -> None:
        if errs:
            head = "；".join(errs[:5]) + (f"…（共 {len(errs)} 项）" if len(errs) > 5 else "")
            _log(f"[第 {attempt} 次尝试] 校验未通过（{len(errs)} 项）：{head}")
        else:
            _log(f"[第 {attempt} 次尝试] 校验通过")

    try:
        out = run_json_skill(spec, inputs, evidence=evidence, log_hook=_hook, llm_config=llm_config)
    except Exception as e:  # noqa: BLE001 失败也留下完整日志供排查
        _log(f"[结果] 失败：{e}")
        _register_log_artifact()
        task_progress.finish(pkey, error=str(e))
        raise
    tree = out["result"]
    # 版本递增：重新生成/打回后再生成都不覆盖历史版本
    prev = (db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id)
            .order_by(models.CaseSet.version.desc()).first())
    version = (prev.version + 1) if prev else 1
    tree["version"] = version
    # 类型标记：business / api 必须可区分（标题强制区分，避免两种用例混淆）
    tree["case_type"] = case_type
    type_label = "接口测试用例" if case_type == "api" else "手工测试用例"
    tree["title"] = f"{tree.get('module', '')} {type_label}"
    tree.setdefault("generated_at", time.strftime("%Y-%m-%d %H:%M:%S"))

    # 存用例集 + 工件
    cs = models.CaseSet(run_id=run_id, version=version, status="generated",
                        content=tree, gen_meta={"case_type": case_type, **out, "result": None})
    db.add(cs)
    db.flush()
    workspace_for(project, run_id)  # 确保工作区存在
    path = storage.save_text(project, run_id, f"case_tree_v{version}.json",
                             json.dumps(tree, ensure_ascii=False, indent=2), subdir="cases")
    db.add(models.Artifact(run_id=run_id, stage_type="case_gen", type="case_tree",
                           name=f"用例树 v{version}", file_path=str(path), version=version,
                           source={"source": "skill", "skill": spec.id, "skill_version": spec.version}))
    groups = len(tree.get("groups", []))
    n_cases = sum(len(g.get("cases", [])) for g in tree.get("groups", []))
    _log(f"[结果] 成功：v{version}，{groups} 组 {n_cases} 条用例，"
         f"共 {out.get('attempts', 1)} 次尝试，耗时 {time.time() - started:.1f}s")
    _register_log_artifact()
    db.commit()
    task_progress.finish(pkey)
    return {"case_set_id": cs.id, "tree": tree, "gen_meta": out, "version": version}
