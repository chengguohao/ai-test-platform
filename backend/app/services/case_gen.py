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


def _ref_snapshot_of(entry: models.KnowledgeEntry) -> dict:
    """取知识库条目引用骨架；旧数据 ref_snapshot 为空时从完整快照现压（只留关键信息）。"""
    if entry.ref_snapshot:
        return entry.ref_snapshot
    content = entry.content or {}
    return {
        "module": content.get("module", ""), "title": content.get("title", ""),
        "case_type": (entry.case_type or ""), "version": entry.case_version,
        "generated_at": content.get("generated_at", ""),
        "groups": [
            {"name": g.get("name", ""),
             "cases": [{"id": c.get("id", ""), "title": c.get("title", ""),
                        "priority": c.get("priority", ""), "api": c.get("api", "")}
                       for c in (g.get("cases") or [])]}
            for g in (content.get("groups") or [])
        ],
    }


def _knowledge_reference(db: Session, run_id: int, limit: int = 6) -> list[dict]:
    """同项目知识库引用：按模块去重（每模块取最新已归档版本），返回紧凑骨架列表。

    供 AI 生成用例时参考历史用例：既贴合既有功能分组/用例风格，又避免把
    全部历史全文灌入（省 token）。limit 防条数膨胀。
    """
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        return []
    rows = (db.query(models.KnowledgeEntry)
            .filter(models.KnowledgeEntry.project_id == run.project_id)
            .order_by(models.KnowledgeEntry.id.desc()).all())
    latest_by_module: dict[str, models.KnowledgeEntry] = {}
    for e in rows:   # id desc，每模块首个即最新归档
        m = (_ref_snapshot_of(e).get("module") or "").strip()
        m = m or f"p{e.project_id}"
        if m not in latest_by_module:
            latest_by_module[m] = e
    return [_ref_snapshot_of(e) for e in list(latest_by_module.values())[:limit]]


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
    日志与用例树文件均按类型拆分（case_gen_{类型}.log / case_tree_{类型}_v{n}.json，各类型版本独立从 1 计），
    互不混写。路径：workspaces/{project}/{run_id}/logs/ 与 cases/。
    """
    started = time.time()
    log_path: Path | None = None
    pkey = f"case_gen:{run_id}"   # 前端轮询「思考过程」用
    task_progress.start(pkey)
    # 类型中文简称（日志文件名 / 工件名用）：business=业务 / api=接口
    type_label = "业务" if case_type == "business" else "接口"

    def _log(line: str) -> None:
        nonlocal log_path
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        log_path = storage.append_log(project, run_id, f"case_gen_{type_label}", f"[{ts}] {line}\n")
        task_progress.report(pkey, line)   # 同步喂给前端轮询

    def _register_log_artifact() -> None:
        if log_path:
            db.add(models.Artifact(run_id=run_id, stage_type="case_gen", type="gen_log",
                                   name=f"用例生成日志（{type_label}功能）", file_path=str(log_path),
                                   source={"source": "gen_log", "case_type": case_type}))
            db.commit()

    req = _latest_artifact_text(db, run_id, "requirement")
    api = _latest_artifact_text(db, run_id, "api_doc")
    if not req.strip():
        raise ValueError("尚未上传需求工件，请先完成需求阶段")

    # 知识库引用：同项目历史已评审用例的「紧凑参考骨架」（模块级去重，取最新）
    kb_ref = _knowledge_reference(db, run_id)
    if kb_ref:
        _log(f"已引用知识库历史用例 {len(kb_ref)} 条（模块级去重，仅骨架、省 token）作为生成参考，"
             f"模块：{'、'.join(x.get('module') or '?' for x in kb_ref)}")

    # 键序即 prompt 中出现序：稳定内容（接口文档/历史用例参考）排前、易变内容（本次需求）排后，
    # 同项目多轮生成时前缀重复度更高，利于 LLM 服务商的上下文前缀缓存（省 token、降延迟）
    inputs = {
        "api_doc": api[:60000] if api else "",
        "api_doc_present": bool(api),
        "kb_reference": kb_ref,   # 历史用例参考（可能为空列表=无历史）
        "case_type": case_type,
        "requirement": req[:40000],
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
    # 版本递增按类型独立计数：业务 v1/v2…与接口 v1/v2…互不混序
    prev = None
    for c in db.query(models.CaseSet).filter(models.CaseSet.run_id == run_id).all():
        if (c.gen_meta or {}).get("case_type") == case_type:
            if prev is None or c.version > prev.version:
                prev = c
    version = (prev.version + 1) if prev else 1
    tree["version"] = version
    # 类型标记：business / api 必须可区分（标题强制区分，避免两种用例混淆）
    tree["case_type"] = case_type
    title_label = "接口测试用例" if case_type == "api" else "手工测试用例"
    tree["title"] = f"{tree.get('module', '')} {title_label}"
    tree.setdefault("generated_at", time.strftime("%Y-%m-%d %H:%M:%S"))

    # 存用例集 + 工件（文件名与工件名均带类型，版本按类型独立）
    cs = models.CaseSet(run_id=run_id, version=version, status="generated",
                        content=tree, gen_meta={"case_type": case_type, **out, "result": None})
    db.add(cs)
    db.flush()
    workspace_for(project, run_id)  # 确保工作区存在
    path = storage.save_text(project, run_id, f"case_tree_{case_type}_v{version}.json",
                             json.dumps(tree, ensure_ascii=False, indent=2), subdir="cases")
    db.add(models.Artifact(run_id=run_id, stage_type="case_gen", type="case_tree",
                           name=f"{'业务功能' if case_type == 'business' else '接口测试'}用例树 v{version}",
                           file_path=str(path), version=version,
                           source={"source": "skill", "skill": spec.id, "skill_version": spec.version,
                                   "case_type": case_type}))
    groups = len(tree.get("groups", []))
    n_cases = sum(len(g.get("cases", [])) for g in tree.get("groups", []))
    _log(f"[结果] 成功：v{version}，{groups} 组 {n_cases} 条用例，"
         f"共 {out.get('attempts', 1)} 次尝试，耗时 {time.time() - started:.1f}s")
    _register_log_artifact()
    db.commit()
    task_progress.finish(pkey)
    return {"case_set_id": cs.id, "tree": tree, "gen_meta": out, "version": version}
