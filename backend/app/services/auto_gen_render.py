"""确定性渲染器：把「用例声明 JSON」渲染成 pytest ApiCase 脚本（方向 A）。

设计核心（2026-09-01 确立）：LLM 只输出受 JSON Schema 约束的**声明数据**
（接口/字段/断言/业务码引用/save/清理），本模块用固定模板把声明**确定性**
渲染成 pytest 源码。op 白名单、_bf 语法、pytestmark、save/清理逻辑全部由
模板保证 —— 物理上不存在「AI 发明不支持的 op / 写错语法 / 写错字段」的可能，
从架构上消除"无穷打补丁"。

被测系统解耦：marker / 业务码表 / 角色 / fixture 全部取自 SystemProfile 画像。

渲染格式（2026-09-02 重构，参照
pytest-bdd/tests/api/smartadmin/enterprise/test_enterprise1.py 手写样板）：
    FLOW_STEPS: list[FlowStep] = [
        FlowStep("admin", ApiCase(
            name='TC-...',
            method='POST',
            path='/oa/...',
            body={
                'enterpriseName': ...,
                'unifiedSocialCreditCode': ...,
            },
            assertions=[
                Assertion(field='/code', op='eq', expected=0),
                Assertion(field='/data/list', op='exists', expected=True),
            ],
        )),
        ...
    ]
ApiCase 每参数一行（缩进 8），body 字典多行展开（键值对缩进 12，闭 } 缩进 8），
assertions 空 [] / 单条单行 / 多条每条一行（缩进 12，闭 ] 缩进 8），闭 )) 缩进 4。
"""
from __future__ import annotations

import re

from app.services.system_profile import SystemProfile

# 断言引擎支持的操作符白名单（与被测工程 support/api_case.py::_eval 严格一致）
VALID_OPS = {"eq", "ne", "exists", "contains", "in", "gt", "gte", "lt", "lte", "regex"}

# 非账号角色（未登录/游客等）：只允许作为单个 FlowStep 的 role（渲染器按其走无登录客户端），
# 绝不允许进模块级 pytestmark_roles —— 否则整模块用例都被该「无身份」要求污染。
NON_ACCOUNT_ROLES = {"anonymous", "not_login", "notlogin", "unauth", "guest"}

# 业务失败反例辅助函数模板（探测不到业务码时退化为 msg 存在并打印显式警告）
_BF_HELPER = '''def _bf(key):
    """动态业务失败断言：探测不到业务码时退化为「msg 存在」断言，避免导入期 None 崩溃。"""
    code = SA_CODES.get(key)
    if code is None:
        print(f"[反例断言降级] 业务码 {key} 未探测到，仅校验 /msg 存在（反例可能白测，请核对）")
        return [Assertion(expected=True, op="exists", field="/msg",
                          reason=f"业务码 {key} 未探测到，退化为仅校验失败信封")]
    return Assertion.biz_fail(code=code) + [Assertion(expected=True, op="exists", field="/msg")]
'''

# 单行紧凑的最大长度阈值（超过即多行展开）
_SINGLE_LINE_LIMIT = 80

# ---- 用例生命周期排序（数据依赖拓扑 + 增→查→改→删） ----
# 2026-09-02 v2 确立：实体功能存在嵌套（如 企业→员工）时，纯 CRUD 分组会破坏跨组依赖
# （员工 add 引用企业反查 save 的 id，但反查属"查组"、add 属"增组"，硬搬移会把 add 排到反查之前）。
# 解法：Kahn 拓扑排序 —— 步骤若在 path/body/params 引用 ${var}，则该 var 的产出步骤（save）为硬前置；
# 就绪步骤按「增(0)→查(1)→改(2)→删(3) 位次优先，同组按声明顺序」出队，尽量贴近生命周期、由依赖拉正嵌套序。
# 词根按「增/改/删 强语义 → 查兜底」优先级匹配（避免 query/list 等常见词误吃 create/delete）。
_CRUD_WORDS: dict[int, tuple[str, ...]] = {
    0: ("create", "add", "insert", "register", "save", "new"),          # 增 C
    2: ("update", "edit", "modify", "patch", "change", "reset"),        # 改 U
    3: ("delete", "remove", "del", "clear"),                            # 删 D
    1: ("query", "get", "list", "page", "search", "detail", "info",    # 查 R（兜底）
        "export", "lookup", "find", "check", "view", "load", "exist"),
}
_CRUD_RANK_CREATE, _CRUD_RANK_READ, _CRUD_RANK_UPDATE, _CRUD_RANK_DELETE = 0, 1, 2, 3

_VAR_REF = re.compile(r"\$\{(\w+)\}")


def _crud_rank(step: dict) -> int:
    """按接口路径词根判定步骤的生命周期位次（0增/1查/2改/3删），无法识别兜底归「查」。"""
    path = (step.get("path") or "").lower()
    if path:
        for rank, words in ((0, _CRUD_WORDS[0]), (2, _CRUD_WORDS[2]),
                            (3, _CRUD_WORDS[3]), (1, _CRUD_WORDS[1])):
            if any(w in path for w in words):
                return rank
    return _CRUD_RANK_READ


def _static_depth(path: str) -> int:
    """接口路径的静态段数（剔除 ${id} 动态段）—— 用于判定实体嵌套深浅（子>父）。"""
    return len([p for p in path.split("/") if p and not p.startswith("${")])


def _order_steps(steps: list[dict]) -> list[dict]:
    """按「${var} 数据依赖硬约束 + 增→查→改→删软偏好」稳定拓扑排序（Kahn）。

    硬约束：step 引用的 ${var} 必须由更早的某 step 通过 save 产出，运行期上下文才拿得到值
    —— 天然保证「子实体创建引用父实体 id」的嵌套依赖链（如 企业反查 save → 员工 add 引用）。
    软偏好：
      - 就绪步骤按 (crud_rank, 声明序号) 出队——保持"先建后查再改最后删"生命周期；
      - 删除组内按「路径静态深度降序」出队——子实体（深，/oa/enterprise/employee/delete）先删、
        父实体（浅，/oa/enterprise/delete）后删，体现「先子后父」清理语义（数据依赖表达不了这一层）；
    环（引用成环）不会发生（producer 唯一），兜底按相同 key 追加。
    """

    def _queue_key(i: int):
        rank = _crud_rank(steps[i])
        if rank == _CRUD_RANK_DELETE:
            return (rank, -_static_depth(steps[i].get("path") or ""), i)
        return (rank, 0, i)

    n = len(steps)
    if n <= 1:
        return steps
    deps: list[set[int]] = [set() for _ in range(n)]
    producers: dict[str, int] = {}   # var -> 产出步骤下标
    for i, s in enumerate(steps):
        for var in (s.get("save") or {}).values():
            producers.setdefault(str(var), i)
    for i, s in enumerate(steps):
        text = "".join((s.get("path") or "", str(s.get("body") or ""), str(s.get("params") or "")))
        for var in _VAR_REF.findall(text):
            p = producers.get(var)
            if p is not None and p != i:
                deps[i].add(p)
    ready = [i for i in range(n) if not deps[i]]
    order: list[int] = []
    while ready:
        ready.sort(key=_queue_key)
        i = ready.pop(0)
        order.append(i)
        for j, _ in enumerate(steps):
            if i in deps[j]:
                deps[j].discard(i)
                if not deps[j] and j not in order:
                    ready.append(j)
    if len(order) < n:   # 理论不可达（save/引用无环），防御：剩余按相同 key 补尾
        order.extend(sorted((j for j in range(n) if j not in order), key=_queue_key))
    return [steps[i] for i in order]


def _fmt_obj(obj, indent: int = 8) -> str:
    """渲染 Python 字面量：短的单行、长的多行展开（对齐 test_enterprise1.py 样板）。

    indent 语义 = 字典/list 所在行的缩进（即 `body={` 这一行的缩进）。
    多行 dict/list：键值对/列表项缩进 indent+4 空格，闭括号缩进 indent 空格
    （与 `xxx=` 行首对齐）。
    短的（repr 长度 <= _SINGLE_LINE_LIMIT）或非 dict/list 类型保持单行。
    """
    single = repr(obj)
    if len(single) <= _SINGLE_LINE_LIMIT or not isinstance(obj, (dict, list)):
        return single
    pad = " " * indent
    inner_pad = " " * (indent + 4)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines = ["{"]
        for k, v in obj.items():
            lines.append(f"{inner_pad}{k!r}: {_fmt_obj(v, indent + 4)},")
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    # list
    if not obj:
        return "[]"
    lines = ["["]
    for item in obj:
        lines.append(f"{inner_pad}{_fmt_obj(item, indent + 4)},")
    lines.append(f"{pad}]")
    return "\n".join(lines)


def _fmt_assertion(a: dict) -> str:
    args = []
    if a.get("field"):
        args.append(f'field={a["field"]!r}')
    args.append(f'op={a["op"]!r}')
    if "expected" in a:
        args.append(f"expected={a['expected']!r}")
    elif a.get("op") == "exists":
        # Assertion.expected 是必填位置参数，exists 语义无预期值 → 兜底 expected=True
        args.append("expected=True")
    if a.get("reason"):
        args.append(f'reason={a["reason"]!r}')
    return "Assertion(" + ", ".join(args) + ")"


def _fmt_assertions(asserts: list[dict]) -> str:
    """渲染 assertions 列表：空 [] / 单条单行 / 多条每条一行（缩进 12，闭 ] 缩进 8）。"""
    if not asserts:
        return "[]"
    if len(asserts) == 1:
        return f"[{_fmt_assertion(asserts[0])}]"
    lines = ["["]
    for a in asserts:
        lines.append(f"            {_fmt_assertion(a)},")
    lines.append("        ]")
    return "\n".join(lines)


def _fmt_api_case(c: dict, has_codes: bool) -> str:
    """渲染 ApiCase 多行格式（参照 test_enterprise1.py 手写样板）：

        ApiCase(
            name='TC-...',
            method='POST',
            path='/oa/...',
            body={
                'a': 1,
                'b': 2,
            },
            assertions=[
                Assertion(...),
                Assertion(...),
            ],
        )
    """
    args: list[str] = [
        f"name={c['name']!r}",
        f"method={c['method']!r}",
        f"path={c['path']!r}",
    ]
    if c.get("body"):
        args.append(f"body={_fmt_obj(c['body'], indent=8)}")
    if c.get("params"):
        args.append(f"params={_fmt_obj(c['params'], indent=8)}")
    if c.get("save"):
        args.append(f"save={_fmt_obj(c['save'], indent=8)}")
    if c.get("biz_fail"):
        # 业务失败反例：biz_auto=False + 解包 _bf("key")（动态业务码，探测不到退化为 msg 存在并打印警告）
        args.append("biz_auto=False")
        if has_codes:
            args.append(f'assertions=[*_bf({c["biz_fail"]!r})]')
        else:
            # 无业务码表的被测工程：退化为仅校验失败信封存在
            args.append('assertions=[Assertion(expected=True, op="exists", field="/msg")]')
    else:
        if "biz_auto" in c:
            args.append(f"biz_auto={str(bool(c['biz_auto']))}")
        if c.get("assertions"):
            args.append(f"assertions={_fmt_assertions(c['assertions'])}")
    body_str = ",\n        ".join(args)
    return "ApiCase(\n        " + body_str + ",\n    )"


def render_code(spec: dict, profile: SystemProfile) -> str:
    """把声明 spec 渲染成可落盘的 pytest 源码字符串。

    渲染产物由模板保证语法正确；调用方仍可再用 _lint_code 做 compile 兜底（防御性）。
    """
    module = spec.get("module", "module")
    steps: list[dict] = _order_steps(spec.get("steps", []))  # 生命周期重排：增→查(save id)→改→删
    uses_roles = any(s.get("role") for s in steps)
    has_bf = any(s.get("biz_fail") for s in steps)
    has_codes = bool(profile.codes_import)
    cleanups = {s["name"]: s["cleanup"] for s in steps if s.get("cleanup")}

    out: list[str] = []
    out.append('"""')
    out.append("AUTO-GENERATED by pytest-case-generator (declarative renderer)")
    out.append("Source mapping:")
    for s in steps:
        out.append(f"{s['name']} -> {s['name']}")
    out.append('"""')

    # ---- imports ----
    imp = ["from __future__ import annotations", "", "import allure", "import pytest"]
    if uses_roles:
        imp.append("from support.api_case import ApiCase, Assertion, FlowStep, run_case")
        imp.append("from support.clients.api_client import ApiClient")
    else:
        imp.append("from support.api_case import ApiCase, Assertion, run_case")
    imp.append("from support.fixtures.context import ScenarioContext")
    if has_bf and has_codes:
        imp.append(profile.codes_import)
    out.append("\n".join(imp))

    # ---- _bf helper（仅当存在业务失败反例） ----
    if has_bf and has_codes:
        out.append("\n\n" + _BF_HELPER.strip())

    # ---- 资源清理表（创建类用例按声明注册清理） ----
    if cleanups:
        out.append("\n\n# 创建类用例的资源清理规则（渲染器按声明生成）")
        out.append("_CLEANUP = " + _fmt_obj(cleanups, indent=0))

    # ---- pytestmark ----
    markers = []
    if profile.marker:
        markers.append(f"pytest.mark.{profile.marker}")
    markers.append("pytest.mark.api")
    if uses_roles:
        for r in (spec.get("pytestmark_roles") or []):
            if r in NON_ACCOUNT_ROLES:
                continue   # 未登录角色只允许作单 step role，绝不进模块级 requires_role
            markers.append(f"pytest.mark.requires_role('{r}')")
    out.append("\n\npytestmark = [" + ", ".join(markers) + "]")

    # ---- CASES / FLOW_STEPS ----
    if uses_roles:
        out.append("\n\nFLOW_STEPS: list[FlowStep] = [")
        for s in steps:
            out.append(f'    FlowStep({s.get("role")!r}, {_fmt_api_case(s, has_codes)}),')
        out.append("]")
    else:
        out.append("\n\nCASES: list[ApiCase] = [")
        for s in steps:
            out.append("    " + _fmt_api_case(s, has_codes) + ",")
        out.append("]")

    # ---- 测试函数（固定模板，清理逻辑由 _CLEANUP 表驱动） ----
    feature = spec.get("feature") or f"{profile.system_name} · {module}"
    story = spec.get("story") or "L2 接口"
    cleanup_block = """    if result.passed and case.name in _CLEANUP:
        rule = _CLEANUP[case.name]
        cid = ctx.get(rule["id_var"])
        if cid is not None:
            cleanup_registry.register_delete(rule["delete_path"], cid)"""
    if uses_roles:
        cleanup_block = cleanup_block.replace("case.name", "step.case.name").replace(
            "_CLEANUP[case.name]", "_CLEANUP[step.case.name]")
        fn = f'''
@allure.feature({feature!r})
@allure.story({story!r})
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_{module}_role_flow(role_registry, ctx: ScenarioContext, cleanup_registry, base_url, admin_client, step: FlowStep):
    if step.role == "anonymous":
        client = ApiClient(base_url)
    elif step.role == "admin":
        client = admin_client
    else:
        client = role_registry[step.role]
    result = run_case(client, ctx, step.case)
{cleanup_block}
    assert result.passed, f"[{{step.role}}] {{step.case.name}}: {{result.failure_summary}}"
'''
    else:
        fn = f'''
@allure.feature({feature!r})
@allure.story({story!r})
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_{module}_crud(api_client, ctx: ScenarioContext, cleanup_registry, case: ApiCase):
    result = run_case(api_client, ctx, case)
{cleanup_block}
    assert result.passed, f"[{{case.name}}] {{result.failure_summary}}"
'''
    out.append(fn)

    return "\n".join(out).strip() + "\n"
