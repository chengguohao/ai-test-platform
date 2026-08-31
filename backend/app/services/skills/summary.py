"""Skill：需求摘要（固定结构输出）。"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec

SYSTEM = """你是资深测试需求分析师。请严格按输出契约输出 JSON，不要编造需求中不存在的内容。
所有"依据/功能点"必须能在提供的需求文本中找到出处；找不到就写"待确认"，不要臆造。"""

USER = """请分析以下需求，输出固定结构的 JSON（键名与类型必须与要求完全一致）：
{{
  "module": "模块英文短名（小写下划线）",
  "module_cn": "模块中文名",
  "business_points": ["功能点1", "功能点2", ...],
  "roles": ["涉及角色（如管理员/普通用户，无则空数组）"],
  "new_apis": ["本次新增/变更接口清单，如 POST /xxx，无新增接口则空数组"],
  "risks": ["业务风险/边界情况（无则空数组）"],
  "open_questions": ["待确认事项（无则空数组）"]
}}

需求与资料（JSON 格式）：
{inputs}"""

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["module", "module_cn", "business_points", "roles", "new_apis", "risks", "open_questions"],
    "properties": {
        "module": {"type": "string"},
        "module_cn": {"type": "string"},
        "business_points": {"type": "array", "items": {"type": "string"}},
        "roles": {"type": "array", "items": {"type": "string"}},
        "new_apis": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
}

SKILL = SkillSpec(
    id="summary",
    name="需求摘要",
    version="1.0.0",
    desc="把需求文档提炼成结构化摘要（功能点/角色/新增接口/风险/待确认），是生成用例前的第一步。",
    system_prompt=SYSTEM,
    user_template=USER,
    output_schema=OUTPUT_SCHEMA,
    kind="json",
)
