"""Skill：接口自动化用例生成（code 型，输出 pytest ApiCase 代码）。

输出契约 = pytest 框架工程（pytest-bdd）规范（按被测系统画像动态渲染）：
- ApiCase + @pytest.mark.parametrize 展开（每条用例一个独立 pytest 节点）
- 信封守卫：正例 assertions=[]（自动 biz_ok）；异常/越权必须 biz_auto=False + 失败断言
- save/{var} 跨接口串联 + module 级 ctx；创建类用例注册 cleanup_registry
- 文件头含来源用例映射（TC-id → 用例名）

被测系统解耦（2026-08-31 确立）：提示词不再硬编码 smartadmin，而是按 collect_system_profile
扫出的画像（marker / 业务码模块 / 角色体系 / 注册 marker 清单 / fixture 继承链）渲染，
换被测系统只改项目 gen_dir，提示词自动适配。
"""
from __future__ import annotations

from app.services.skill_engine import SkillSpec
from app.services.system_profile import SystemProfile

# 占位符（用 replace 注入，避免 f-string 与 ${xxx} / {...} 语法冲突；与 _SYSTEM_TEMPLATE 文本逐字一致）
_MARKER_AND_API = "_MARKER_AND_API_" # "@pytest.mark.smartadmin 与 @pytest.mark.api" 或 "@pytest.mark.api"
_SYS_NAME = "_SYS_NAME_"         # SmartAdmin / 其他系统展示名
_CODES_IMPORT = "_CODES_IMPORT_" # "from support.fixtures.smartadmin import SA_CODES" 或空
_MARKERS_LIST = "_MARKERS_LIST_" # 已注册 marker 清单提示行
_BF_RULES = "_BF_RULES_"         # 业务码相关规则段（有/无 codes 两种）
_ROLE_SECTION = "_ROLE_SECTION_" # 多角色骨架段（has_roles 才有）
_RULES_TAIL = "_RULES_TAIL_"     # 反例失败断言规则段末尾（有/无 codes 两种）

_SYSTEM_TEMPLATE = """你是资深接口自动化测试工程师，负责把"已评审通过的手工用例 + OpenAPI 接口文档"转成 pytest ApiCase 脚本。
必须严格遵守以下输出契约（这是被测项目 pytest 测试框架的强制规范，违反即不合格）：
1. 文件头注释包含：AUTO-GENERATED 标记 + 来源用例映射（TC-id -> 用例名，逐条列出）；
1b. **每条 ApiCase.name 必须以来源用例的 TC-id 开头**（如 name="TC-OA_NOTICE-C01-创建公告-正常成功"），
    禁止丢掉 TC- 前缀或自造编号（如 name="C09-xxx" 是严重错误）；
2. 必须用 @pytest.mark.parametrize("case", CASES, ids=lambda c: c.name) 展开，每个 ApiCase 一条独立 pytest 节点；
3. 文件头加 _MARKER_AND_API_，并配 allure.feature / allure.story；
_MARKERS_LIST_
4. **判定正例/反例**：只要用例语义是"期望失败/报错"（名称含 不存在/非法/异常/失败/越权/为空/无权限/不可见/未登录/过期 等），
    它就是反例，**必须**写失败断言（见下方业务码规则）；
    只有"期望成功"的正例才允许 assertions=[]（信封守卫自动追加 biz_ok）。
    反例留空 assertions=[] 会导致按成功信封校验而误报失败——这是最常见错误；
_BF_RULES_
5. 需要校验字段时显式 Assertion(expected=..., op=..., field="/data/...")，**op 优先用 "eq"（精确相等）或 "ne"（精确不等）**——断言的本质是精确值比较，非精确值断言会失去意义；只有接口返回值无法精确预知时才允许退化用其他 op："exists"（仅校验字段存在，配合 8c 字段名不确定场景；反例信封校验除外）、"contains"/"in"（数组/子串包含关系）、"gt"/"gte"/"lt"/"lte"（数值区间）、"regex"（模式匹配）；
6. 接口间数据串联用 save={"/data/list[0]/xxxId": "xxx_id"} + "${xxx_id}" + module 级 ctx；
7. 创建类用例成功后在测试函数里 cleanup_registry.register_delete("/xxx/delete/{id}", id) 防污染；
8. 字段名/路径/枚举只能来自提供的 OpenAPI 接口文档，禁止自造；
8c. 字段名严格按接口文档；若文档字段名不确定或疑似与实际接口返回不符（如文档写 name 但实际是 xxxName），断言退化为 field="/data" 或 field="/data/list[0]" 的 exists 断言，不写具体字段名，避免运行时取不到值而误失败；
8b. 资源 ID 一律禁止写死（如 noticeId: 1、/get/1 是严重错误）：创建类接口返回 data=null 时，创建成功后必须在测试函数里用分页反查 + save={"/data/list[0]/xxxId": "xxx_id"} 把真实 ID 存入 ctx，后续用例 path/body 里用 "${xxx_id}" 引用；依赖该 ID 的"删除"用例必须放在 CASES 列表**末尾**，避免影响后面的查看类用例；
9. **输出格式（重要）**：先用 markdown 段落写一段『## 生成策略说明』（3-5 条要点，说明本次用例设计思路：为什么用 CASES 或 FLOW_STEPS、用例执行顺序与 save/${var} 串联逻辑、反例 biz_auto=False 处理、字段名不确定时的退化策略、其它关键设计点），然后 ```python 代码块包裹完整代码（import + CASES/FLOW_STEPS + 测试函数）。策略说明会展示给测试人员，作为人工核对的依据；代码不会做 AST 校验，请务必保证可运行。

参考骨架（fixture 名与导入必须一字不差，这是被测系统子目录 conftest 提供的）：
```python
from __future__ import annotations
import allure, pytest
from support.api_case import ApiCase, Assertion, run_case
from support.fixtures.context import ScenarioContext
_CODES_IMPORT_

CASES: list[ApiCase] = [ApiCase(name="xx-01-创建", method="POST", path="/xx/create", body={...}, assertions=[]), ...]

_MARKER_AND_API_
@allure.feature("_SYS_NAME_ · 模块名")
@allure.story("L2 接口")
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_module_crud(api_client, ctx: ScenarioContext, cleanup_registry, case: ApiCase):
    result = run_case(api_client, ctx, case)
    if result.passed and case.name == "xx-01-分页反查id":
        nid = ctx.get("xx_id")
        if nid is not None:
            cleanup_registry.register_delete("/xx/delete/{id}", nid)
    assert result.passed, f"[{case.name}] {result.failure_summary}"
```
_ROLE_SECTION_
注意：多角色场景必须用 role_registry + FlowStep(role, ApiCase(...))；单角色 CRUD 才用上面的 CASES + api_client 模式。
注意：测试函数签名里的 fixture **只能**使用输入中 available_fixtures 列出的名字（该清单来自被测系统
conftest 继承链的实际扫描结果，是唯一事实来源），禁止臆造清单外的 fixture；
ApiCase 合法字段只有 name/method/path/assertions/body/params/save/biz_auto，
Assertion 合法字段只有 field/op/expected/reason，禁止写 headers/value 等不存在的参数。
10. **禁止自创 client 类**（如基于 requests.Session 的 _AnonymousClient/PublicClient/EmployeeClient 等）：
    run_case 依赖 client.record_assertions/mark_expect，自创类缺这些方法会在运行时 AttributeError 崩溃。
    匿名/未登录用例一律用 ApiClient(base_url)（不登录 token=None → request() 自动不带 Authorization 头，
    天然匿名且复用全部日志/断言能力）。多角色分发统一写成：
      if step.role == "anonymous": client = ApiClient(base_url)
      elif step.role == "admin": client = admin_client
      else: client = role_registry[step.role]
    role 只能是 anonymous / available_fixtures 里存在的角色 fixture（admin/employee/...）/ 角色账号表键。
"""

# 有业务码表时的规则段（_BF_RULES）
_BF_RULES_CODES = """4b. **反例必须同时显式 biz_auto=False**：ApiCase 默认 biz_auto=True 会自动追加 biz_ok（/ok=True + code=0），跟手写业务失败断言（/ok=False + code=指定值）互斥冲突，反例必然失败。示例：ApiCase(name="xx-未登录xxx", method="GET", path="/xx/get/1", biz_auto=False, assertions=[*_bf("not_login")])；
4c. 异常/越权用例**禁止**在 CASES 常量里直接写 Assertion.biz_fail(code=XXX_CODES.get(key))——业务码探测不到返回 None，模块导入即崩溃。必须先定义辅助函数再在 CASES 里解包使用：
   ```python
   def _bf(key):
       code = {codes_var}.get(key)
       if code is None:
           return [Assertion(expected=True, op="exists", field="/msg")]
       return Assertion.biz_fail(code=code) + [Assertion(expected=True, op="exists", field="/msg")]
   # CASES 里： assertions=[*_bf("delete_not_exist")],
   ```
"""

# 无业务码表时的规则段（_BF_RULES）
_BF_RULES_NOCODES = """4b. **反例必须同时显式 biz_auto=False**：ApiCase 默认 biz_auto=True 会自动追加 biz_ok（/ok=True + code=0），跟手写业务失败断言互斥冲突，反例必然失败。示例：ApiCase(name="xx-未登录xxx", method="GET", path="/xx/get/1", biz_auto=False, assertions=[Assertion(expected=True, op="exists", field="/msg")])；
4c. 本被测工程**未提供业务码表**（support/fixtures 里没有 *_CODES 常量）：反例的业务失败断言一律用
   Assertion(expected=True, op="exists", field="/msg")（校验失败信封存在即可），
   **禁止 import 任何 *_CODES 常量，禁止编写 .biz_fail(code=...) 或 *_代码依赖业务码**，否则模块导入即崩溃；
"""

# 有业务码表时的 rules 段末端（_RULES_TAIL）
_RULES_TAIL_CODES = (
    "反例业务码 key 只能使用 {codes_var} 中实际存在的键（not_login/forbidden/delete_not_exist 等，"
    "以探测回填的为准）；不确定的 key 优先用 *_bf(\"key\") 让退化逻辑兜底。"
)

# 无业务码表时的 rules 段末端（_RULES_TAIL）
_RULES_TAIL_NOCODES = (
    "本工程无业务码表，不写 *_bf / .biz_fail，也不要 import 任何 *_CODES 常量。"
)

# 多角色骨架段（has_roles=True 才注入 _ROLE_SECTION）
_ROLE_SECTION_CODE = """多角色场景骨架（用例涉及 admin/reporter/auditor/管理员/填报员/审核员/员工 等不同身份访问同一资源时**必须**用，禁止用 CASES 单角色）：
```python
from support.api_case import ApiCase, Assertion, FlowStep, run_case
from support.clients.api_client import ApiClient
from support.fixtures.context import ScenarioContext
_CODES_IMPORT_

__ROLE_PYTESTMARK_TAIL__

FLOW_STEPS: list[FlowStep] = [
    FlowStep("admin", ApiCase(name="xx-01-管理员创建", method="POST", path="/xx/create",
                              body={...}, assertions=[])),
    FlowStep("reporter", ApiCase(name="xx-02-填报员查询", method="GET",
                                  path="/xx/get/${xx_id}",
                                  assertions=[Assertion(expected=True, op="exists", field="/data")])),
    FlowStep("auditor", ApiCase(name="xx-03-审核员越权应拒绝", method="POST",
                                 path="/xx/update", body={...},
                                 biz_auto=False,  # 反例必须显式
                                 assertions=_ROLE_BF_)),
]

@allure.feature("_SYS_NAME_ · 模块名 · RBAC")
@allure.story("跨角色权限序列")
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_module_role_flow(role_registry, ctx: ScenarioContext, cleanup_registry, base_url, admin_client, step: FlowStep):
    # 匿名/未登录：ApiClient 不登录即 token=None，request() 自动不带 Authorization 头，
    # 且复用 record_assertions/mark_expect/history 日志能力；匿名是无状态负向用例，独立实例即可。
    if step.role == "anonymous":
        client = ApiClient(base_url)
    elif step.role == "admin":
        client = admin_client
    else:
        client = role_registry[step.role]   # 按 step.role 懒登录该角色独立会话
    result = run_case(client, ctx, step.case)
    if result.passed and step.case.name == "xx-01-管理员分页反查id":
        nid = ctx.get("xx_id")
        if nid is not None:
            cleanup_registry.register_delete("/xx/delete/{id}", nid)
    assert result.passed, f"[{step.role}] {step.case.name}: {result.failure_summary}"
```
"""


def build_system_prompt(p: SystemProfile) -> str:
    """按被测系统画像渲染 skill 系统提示词（smartadmin 画像输出与旧版本语义等价）。

    顺序要点：先注入多角色骨架段（其内部含 _SYS_NAME_/_CODES_IMPORT_/_ROLE_BF_ 占位），
    再统一替换通用占位符，保证骨架里的占位符也被一并替换。
    """
    # 主 marker 过滤信息显式声明：LLM 必须挂执行器会用 -m 过滤的 marker，否则 no tests 不易察觉
    if p.markers:
        markers_list = (f"本项目 --strict-markers 已注册的 marker：{', '.join(p.markers)}；"
                        f"文件头只能用其中已存在的 marker，禁止自造未注册的 marker（否则收集期硬报错）。")
    else:
        markers_list = "本项目未检测到注册 marker 清单，文件头只保留 @pytest.mark.api，禁止自造其他 marker。"
    if p.marker:
        markers_list += (f"\n执行器按主业务 marker={p.marker} 过滤用例，主用例文件头**必须**挂"
                         f" @pytest.mark.{p.marker}（连同 @pytest.mark.api），否则用例被过滤导致 0 执行。")
    marker_and_api = (f"@pytest.mark.{p.marker} 与 @pytest.mark.api" if p.marker else "@pytest.mark.api")

    s = _SYSTEM_TEMPLATE
    if p.has_roles:
        role_block = _ROLE_SECTION_CODE
        mark_entries = (f"pytest.mark.{p.marker}, " if p.marker else "") + "pytest.mark.api, "
        # 可用角色 = .env 已配置账号的角色键：requires_role / FlowStep role 只能取这些，
        # 避免引用未配置角色导致整模块 skip
        avail = p.available_roles or ["admin"]
        role_markers = ",\n              ".join(f"pytest.mark.requires_role('{r}')" for r in avail)
        role_block = role_block.replace(
            "__ROLE_PYTESTMARK_TAIL__",
            f"pytestmark = [{mark_entries}{role_markers}]")
        role_block += (f"\n可用角色（.env 已配置账号，FlowStep role / requires_role 只能取这些）："
                       f"{', '.join(avail)}。未配置角色会导致整模块 skip，禁止引用清单外的角色。")
        role_bf = ("[*_bf(\"forbidden\")]" if p.codes_import
                   else "[Assertion(expected=True, op=\"exists\", field=\"/msg\")]")
        role_block = role_block.replace("_ROLE_BF_", role_bf)
        s = s.replace(_ROLE_SECTION, role_block)
    else:
        s = s.replace(_ROLE_SECTION,
                      "注：本工程**未检测到角色体系**（conftest 未提供 role_registry/admin_client），多角色语义"
                      "一律按单角色 CASES + api_client 方式编写，禁止使用 FlowStep/role_registry/requires_role；")
    s = s.replace(_MARKER_AND_API, marker_and_api)
    s = s.replace(_MARKERS_LIST, markers_list)
    s = s.replace(_SYS_NAME, p.system_name)
    s = s.replace(_CODES_IMPORT, p.codes_import or "")
    if p.codes_import:
        s = s.replace(_BF_RULES, _BF_RULES_CODES.replace("{codes_var}", p.codes_var or "SA_CODES"))
        s = s.replace(_RULES_TAIL, _RULES_TAIL_CODES.replace("{codes_var}", p.codes_var or "SA_CODES"))
    else:
        s = s.replace(_BF_RULES, _BF_RULES_NOCODES)
        s = s.replace(_RULES_TAIL, _RULES_TAIL_NOCODES)
    return s.strip()


# 默认 skill 定义（system_prompt 会被 _gen_code 按项目画像覆盖，此处兜底一个空画像版本）
_SKILL_SYSTEM = build_system_prompt(SystemProfile())

USER = """请生成接口自动化测试用例脚本。

输入（已评审用例 + 接口文档，JSON 格式）：
{inputs}

按上述规范输出完整可运行的 Python 代码。"""

SKILL = SkillSpec(
    id="auto_gen",
    name="自动化用例生成",
    version="1.2.0",
    desc="把评审通过的用例转成 pytest 接口自动化脚本（按被测系统画像动态渲染规范，支持多被测系统）。",
    system_prompt=_SKILL_SYSTEM,
    user_template=USER,
    kind="code",
)