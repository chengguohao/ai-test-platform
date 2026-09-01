"""Skill：接口自动化用例生成（声明式，json 型，2026-09-01 重构）。

方向 A（声明式渲染）核心：本 skill 只要求 LLM 输出**受 JSON Schema 约束的用例声明**，
不写任何 Python 代码。声明由平台 `auto_gen_render.render_code` 用确定性模板渲染成
pytest 脚本 —— op 白名单 / _bf 语法 / pytestmark / save / cleanup 全部由模板保证，
从架构上消除"AI 发明不支持的 op / 写错语法"这类无穷打补丁问题。

按被测系统画像（SystemProfile）动态渲染：marker / 业务码键清单 / 可用角色 / fixtures。
"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec
from app.services.system_profile import SystemProfile

# 断言引擎支持的操作符白名单（渲染器与 schema 同源，禁止白名单外 op）
VALID_OPS = ["eq", "ne", "exists", "contains", "in", "gt", "gte", "lt", "lte", "regex"]

# 占位符（build_system_prompt 用 replace 注入）
_SYS_NAME = "_SYS_NAME_"
_MARKERS_LIST = "_MARKERS_LIST_"
_BF_RULES = "_BF_RULES_"
_ROLE_SECTION = "_ROLE_SECTION_"
_RULES_TAIL = "_RULES_TAIL_"

_SYSTEM_TEMPLATE = """你是资深接口自动化测试工程师，负责把"已评审通过的手工用例 + OpenAPI 接口文档"转成「接口自动化用例声明 JSON」。
你只输出**数据**（声明），平台会用确定性模板把它渲染成 pytest 脚本 —— 因此你**绝不输出任何 Python 代码**，只按契约填 JSON。
硬性契约：
1. 每个 step 的 name 必须以来源用例的 TC-id 开头（如 name="TC-OA_NOTICE-C01-创建公告-正常成功"），禁止自造编号或丢 TC- 前缀；
2. 判定正例/反例：用例语义为"期望失败/报错"（名称含 不存在/非法/异常/失败/越权/为空/无权限/不可见/未登录/过期 等）→ 反例，
   必须用 biz_fail 声明业务码 key（**只能取 codes_keys 里列出的值**，反例退化为仅校验 /msg 存在=白测）或断言表达失败；
   只有"期望成功"的正例才允许不写断言（渲染器按成功信封自动校验）；
_BF_RULES_
3. assertions 的 op **只允许**：eq/ne/exists/contains/in/gt/gte/lt/lte/regex。op 优先用 eq/ne（精确值比较）；
   exists 用于"仅校验字段存在"；数值区间用 gt/gte/lt/lte；包含关系用 contains/in；模式用 regex。
   **禁止白名单外的 op（is_array/type/len 等）与数组长度/类型断言（如 field=/data/length）**：
   需要断言空列表/空数组时，改用 exists/eq 可判定的思路或手工核对；
4. 非 exists 的 op 必须带 expected；exists 可省略 expected（渲染器自动补 True）；
5. 字段名/路径/枚举只能来自接口文档，禁止自造；资源 ID 禁止写死——创建类接口返回 data=null 时，
   必须用一个"分页反查"step + save 把真实 ID 存入上下文，后续 step 用 ${xxx_id} 引用；
6. 创建类用例（创建了真实资源）声明 cleanup={"id_var": "xxx_id", "delete_path": "/xxx/delete/{id}"}，
   渲染器自动生成 register_delete 防污染；依赖该 ID 的"删除"step 应放在 steps 靠后；
7. 多角色（admin/employee 等不同身份访问同一资源）→ 每个 step 声明 role（anonymous=未登录）；
   单角色 → 所有 step 都不写 role。role 只能取 available_roles 中列出的值或 anonymous；
_MARKERS_LIST_
8. 只输出一个 JSON 对象：把 3-5 条设计思路（为什么选这些用例/正反例/串联/清理策略）写在 strategy 字段，供测试人员核对。
_RULES_TAIL_
"""

# 有业务码表时的规则段（_BF_RULES）
_BF_RULES_CODES = """2b. biz_fail 的 key 只能使用业务码表中实际存在的键（codes_keys 已列出），
   不可臆造；探测不到业务码时渲染器会自动降级并打印警告（反例白测风险），请优先对齐 codes_keys；"""
# 无业务码表时的规则段（_BF_RULES）
_BF_RULES_NOCODES = """2b. 本被测工程**未提供业务码表**：禁止使用 biz_fail 字段（渲染器不支持），
   反例一律用断言表达失败（如 Assertion 校验 /msg 存在或具体字段），不要写 biz_fail；"""

# 有业务码表时的 rules 段末端
_RULES_TAIL_CODES = "（本工程业务码表存在，biz_fail 仅允许 codes_keys 中的值）"
_RULES_TAIL_NOCODES = "（本工程无业务码表，全程禁用 biz_fail）"

# 多角色规则段（_ROLE_SECTION）
_ROLE_SECTION_CODE = """多角色说明：本工程检测到角色体系（role_registry/admin_client 可用）。
涉及不同身份访问时每个 step 必须写 role；role 只允许取 available_roles 中的值或 anonymous。
单角色用例整组都不写 role。"""
_ROLE_SECTION_NOCODES = "注：本工程未检测到角色体系，所有用例按单角色（不写 role）编写，禁止使用 role/anonymous。"

USER = """请输出接口自动化用例声明 JSON（只输出一个 JSON 对象，不要输出任何 Python 代码或额外解释）：
{{
  "module": "模块英文短名（小写下划线）",
  "feature": "被测系统名 · 模块中文名",
  "story": "用例组名（如 L2 接口 / 跨角色权限与业务流）",
  "pytestmark_roles": ["涉及的角色键，如 admin"],
  "strategy": "3-5 条设计思路说明（供测试人员核对）",
  "steps": [
    {{
      "role": "admin",
      "name": "TC-XXX-C01-用例标题",
      "method": "POST",
      "path": "/oa/xxx/create",
      "body": {{"field": "value"}},
      "params": {{"pageNum": 1, "pageSize": 10}},
      "save": {{"/data/list[0]/xxxId": "xxx_id"}},
      "biz_auto": true,
      "biz_fail": "delete_not_exist",
      "cleanup": {{"id_var": "xxx_id", "delete_path": "/xxx/delete/{{id}}"}},
      "assertions": [
        {{"op": "exists", "field": "/data"}},
        {{"op": "eq", "field": "/code", "expected": 0}},
        {{"op": "gt", "field": "/data/total", "expected": 0}}
      ]
    }}
  ]
}}

输入（已评审用例 + 接口文档 + 被测系统契约，JSON 格式）：
{{inputs}}"""


def _spec_schema() -> dict:
    return {
        "type": "object",
        "required": ["module", "feature", "steps"],
        "properties": {
            "module": {"type": "string"},
            "feature": {"type": "string"},
            "story": {"type": "string"},
            "pytestmark_roles": {"type": "array", "items": {"type": "string"}},
            "strategy": {"type": "string"},
            "steps": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "method", "path"],
                    "properties": {
                        "role": {"type": "string"},
                        "name": {"type": "string"},
                        "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
                        "path": {"type": "string"},
                        "body": {"type": "object"},
                        "params": {"type": "object"},
                        "save": {"type": "object"},
                        "biz_auto": {"type": "boolean"},
                        "biz_fail": {"type": "string"},
                        "cleanup": {
                            "type": "object",
                            "required": ["id_var", "delete_path"],
                            "properties": {
                                "id_var": {"type": "string"},
                                "delete_path": {"type": "string"},
                            },
                        },
                        "assertions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["op"],
                                "properties": {
                                    "op": {"enum": VALID_OPS},
                                    "field": {"type": "string"},
                                    "expected": {},
                                    "reason": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _validate(obj: dict) -> list[str]:
    """额外规则校验（在 JSON Schema 之外，针对业务语义）。"""
    errs: list[str] = []
    mod = obj.get("module", "")
    prefix = f"TC-{mod.upper()}-"
    seen: set[str] = set()
    steps: list[dict] = obj.get("steps", [])
    roles = [s.get("role") for s in steps]
    if any(roles) and not all(roles):
        errs.append("steps 中一旦出现 role，所有 step 都必须声明 role（多角色/单角色二选一，不可混用）")
    for s in steps:
        name = s.get("name", "")
        if not name.startswith(prefix):
            errs.append(f"step name {name!r} 不符合编号规范 {prefix}NN")
        if name in seen:
            errs.append(f"step name 重复: {name}")
        seen.add(name)
        if not s.get("path"):
            errs.append(f"{name} 缺少 path")
        for a in s.get("assertions", []):
            if a.get("op") != "exists" and "expected" not in a:
                errs.append(f"{name} 的断言 op={a.get('op')} 缺少 expected（仅 exists 可省略）")
    return errs


def build_system_prompt(p: SystemProfile) -> str:
    """按被测系统画像渲染 skill 系统提示词（json 型声明契约）。"""
    s = _SYSTEM_TEMPLATE
    markers_list = ""
    if p.markers:
        markers_list = (f"marker 只能是已注册的：{', '.join(p.markers)}（无需自造，渲染器会按画像自动挂）")
    if p.has_roles:
        role_block = _ROLE_SECTION_CODE
        avail = p.available_roles or ["admin"]
        role_block += f"\n可用角色：{', '.join(avail)}。"
        s = s.replace(_ROLE_SECTION, role_block)
    else:
        s = s.replace(_ROLE_SECTION, _ROLE_SECTION_NOCODES)
    s = s.replace(_MARKERS_LIST, markers_list)
    s = s.replace(_SYS_NAME, p.system_name)
    if p.codes_import:
        s = s.replace(_BF_RULES, _BF_RULES_CODES)
        s = s.replace(_RULES_TAIL, _RULES_TAIL_CODES)
    else:
        s = s.replace(_BF_RULES, _BF_RULES_NOCODES)
        s = s.replace(_RULES_TAIL, _RULES_TAIL_NOCODES)
    return s.strip()


SKILL = SkillSpec(
    id="auto_gen",
    name="自动化用例生成",
    version="2.0.0",
    desc="把评审通过的用例+接口文档转成接口自动化用例声明（声明式，确定性渲染成 pytest，杜绝 AI 发明不支持的语法/操作符）。",
    system_prompt=build_system_prompt(SystemProfile()),
    user_template=USER,
    output_schema=_spec_schema(),
    validator=_validate,
    max_retries=2,
    kind="json",
)
