"""Skill：执行失败根因分析（Allure/pytest 失败后的 AI 检查）。"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec

SYSTEM = """你是资深自动化测试工程师。用户会提供 pytest 执行失败的日志摘要、逐用例失败明细和当前自动化脚本代码。
你的任务是做「根因分析」：判断失败是脚本问题（断言写错/数据准备问题/依赖缺失/业务码配置错）
还是被测系统真实缺陷。只基于提供的材料下结论，不要臆造日志里不存在的错误。
严格按输出契约输出 JSON。"""

USER = """请分析以下 pytest 执行失败材料，输出固定结构的 JSON：
{{
  "root_causes": [
    {{"case": "失败用例名或 TC-id", "cause": "根因一句话", "is_script_bug": true,
      "evidence": "日志中的关键证据（截取原文片段）"}}
  ],
  "overall_conclusion": "整体结论一句话：主要是脚本问题还是系统缺陷",
  "regen_instructions": "给重新生成自动化脚本的具体修改指令（写给生成器看的要点清单，逐条列出，没有脚本问题则写空字符串）"
}}

失败材料（JSON 格式）：
{inputs}"""

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["root_causes", "overall_conclusion", "regen_instructions"],
    "properties": {
        "root_causes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["case", "cause", "is_script_bug", "evidence"],
                "properties": {
                    "case": {"type": "string"},
                    "cause": {"type": "string"},
                    "is_script_bug": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
            },
        },
        "overall_conclusion": {"type": "string"},
        "regen_instructions": {"type": "string"},
    },
}

SKILL = SkillSpec(
    id="auto_fix",
    name="执行失败根因分析",
    version="1.0.0",
    desc="Allure/pytest 执行失败后，AI 分析失败日志与脚本代码，输出根因结论和重新生成的修改指令。",
    system_prompt=SYSTEM,
    user_template=USER,
    output_schema=OUTPUT_SCHEMA,
    kind="json",
)
