"""Skill：测试用例生成（固定流程 + 固定输出契约，核心反幻觉 skill）。

执行流程（固化）：
  ① 从需求提取功能点与角色
  ② 依据可选接口文档/知识库实据（evidence）
  ③ 按覆盖清单枚举用例：每个功能点至少 1 正例 + 1 反例/边界/权限异常
  ④ 按输出契约输出用例树 JSON
"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec, canonical

SYSTEM = """你是资深测试工程师，负责根据需求与接口文档生成手工测试用例。
反幻觉硬约束：
1. 用例里的接口路径、字段、枚举值**只能**来自提供的接口文档/实据，禁止自造；
2. 每个功能点至少覆盖：正常成功、异常/边界、权限或空值等负面场景；
3. 步骤与预期必须具体、可执行、可验收；优先级只能是 高/中/低；
4. 用例 id 使用 TC-{MOD}-NN 编号（{MOD}=模块短名大写），同一模块内不允许重复；
5. 需求与接口没提到的内容不得臆造，必要时用 remark 标注"待确认"。
6. steps 与 expects 都不得为空；业务功能用例允许多个步骤对应一条综合预期（数量不必相等，
   但每条预期必须能对应到具体步骤）；接口测试用例尽量做到步骤与预期一一对应。

用例类型（由输入 case_type 决定，务必严格区分）：
- case_type="business"（业务功能用例，默认）：站在用户操作视角，描述"在页面上/业务流程里怎么操作、看到什么结果"。
  steps 写业务操作步骤（如"进入通知公告列表→点击新增→填写标题…"），expects 写业务可见结果（如"列表新增一条记录"）。
  api 字段仅当该用例确实对应某接口时填写，否则留空。这类用例供手工测试人员执行。
- case_type="api"（接口测试用例）：站在接口调用视角，每条用例对应一个具体接口的请求/响应校验。
  api 字段必填（METHOD /path），steps 写请求构造与调用，expects 写响应字段/业务码校验。这类用例供接口自动化直接转换。
请严格按输出契约输出 JSON。"""

USER = """请按输出契约生成手工测试用例树 JSON：
{{
  "module": "模块英文短名（小写下划线）",
  "title": "模块中文名 + 手工测试用例",
  "groups": [
    {{
      "name": "功能分组名",
      "cases": [
        {{
          "id": "TC-XXX-C01",
          "title": "用例标题",
          "precondition": "前置条件（无则空串）",
          "data": "测试数据（无则空串）",
          "steps": ["步骤1", "步骤2"],
          "expects": ["预期结果1", "预期结果2"],
          "priority": "高",
          "api": "POST /path 或空",
          "remark": ""
        }}
      ]
    }}
  ]
}}

输入（需求 + 可选接口/知识库实据，JSON 格式）：
{inputs}"""


def _case_tree_schema() -> dict:
    return {
        "type": "object",
        "required": ["module", "title", "groups"],
        "properties": {
            "module": {"type": "string"},
            "title": {"type": "string"},
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "cases"],
                    "properties": {
                        "name": {"type": "string"},
                        "cases": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["id", "title", "steps", "expects", "priority"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "precondition": {"type": "string"},
                                    "data": {"type": "string"},
                                    "steps": {"type": "array", "items": {"type": "string"}},
                                    "expects": {"type": "array", "items": {"type": "string"}},
                                    "priority": {"enum": ["高", "中", "低"]},
                                    "api": {"type": "string"},
                                    "remark": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _validate(obj: dict) -> list[str]:
    errs = []
    seen: set[str] = set()
    mod = obj.get("module", "")
    prefix = f"TC-{mod.upper()}-"
    for g in obj.get("groups", []):
        for c in g.get("cases", []):
            cid = c.get("id", "")
            if not cid.startswith(prefix):
                errs.append(f"用例 id {cid!r} 不符合编号规范 {prefix}NN")
            if cid in seen:
                errs.append(f"用例 id 重复: {cid}")
            seen.add(cid)
            if not c.get("steps"):
                errs.append(f"{cid} 缺少 steps")
            if not c.get("expects"):
                errs.append(f"{cid} 缺少 expects")
            # 注意：不再强制 steps 与 expects 数量相等——业务功能用例允许
            # 多个步骤对应一条综合预期（数量不等是合法形态），只要求两边都非空。
    if not obj.get("groups"):
        errs.append("groups 为空：没有任何用例，请按覆盖清单补充")
    return errs


SKILL = SkillSpec(
    id="case_gen",
    name="用例生成",
    version="1.2.0",
    desc="根据需求+接口文档自动生成测试用例（业务功能用例/接口测试用例），带反幻觉校验与自动重试。",
    system_prompt=SYSTEM,
    user_template=USER,
    output_schema=_case_tree_schema(),
    validator=_validate,
    max_retries=2,
    kind="json",
)
