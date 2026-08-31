"""Skill 定义注册表（固定规则/流程/输出契约）。

新增 skill = 在 skills/ 下新增模块并在此登记。这是"减少幻觉、固定输出"的核心。
"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec
from app.services.skills.auto_fix import SKILL as AUTO_FIX
from app.services.skills.auto_gen import SKILL as AUTO_GEN
from app.services.skills.case_gen import SKILL as CASE_GEN
from app.services.skills.summary import SKILL as SUMMARY

SKILLS: dict[str, SkillSpec] = {
    SUMMARY.id: SUMMARY,
    CASE_GEN.id: CASE_GEN,
    AUTO_GEN.id: AUTO_GEN,
    AUTO_FIX.id: AUTO_FIX,
}


def list_skills() -> list[dict]:
    return [{"id": s.id, "name": s.name, "version": s.version, "kind": s.kind, "desc": s.desc}
            for s in SKILLS.values()]


def get_skill_detail(skill_id: str) -> dict | None:
    """Skill 详情（含提示词全文），供 Skill 能力中心查看。"""
    s = SKILLS.get(skill_id)
    if not s:
        return None
    return {
        "id": s.id, "name": s.name, "version": s.version, "kind": s.kind, "desc": s.desc,
        "max_retries": s.max_retries,
        "system_prompt": s.system_prompt,
        "output_schema": s.output_schema,
    }
