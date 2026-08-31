"""声明式接口 case + 断言引擎（接口用例每模块单文件汇总）。

每个接口定义为一条 ApiCase（含中文名/方法/链接/参数/断言/动态参数），
跨接口业务链用 FlowCase（多步顺序执行，步间 save/${var} 串联），
用例文件只负责声明，运行/匹配/失败原因统一在 run_case / run_flow 里处理：

  - 断言由用户填预期值，运行时用返回内容逐项匹配；
  - 匹配成功接口通过，匹配失败打印失败原因；
  - field 为 None 时校验状态码，否则按 JSON 路径从响应体取值校验。

SmartAdmin 信封扩展：
  Assertion.biz_ok() / biz_fail(code) 生成针对 {ok,code} 的断言列表；
  ApiCase.biz_auto=True + 响应是 SmartAdmin 信封 → run_case 自动前置 biz_ok。
  信封守卫：payload 不是 dict 或不含 "ok" 键（如普通 REST 接口）
  就不追加任何 biz_* 断言，保证旧用例 100% 不被污染。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import allure

from support.fixtures.context import ScenarioContext


@dataclass
class Assertion:
    """一条断言规则。

    field: None => 校验状态码；否则为 JSON 路径，如 /id、/items[0].sku、/errors.items。
    op: eq / ne / contains / exists / gt / gte / lt / lte / in / regex
    """
    expected: Any
    op: str = "eq"
    field: str | None = None
    reason: str | None = None

    # ------------------------------------------------------------------
    # SmartAdmin 信封断言快捷工厂
    # ------------------------------------------------------------------
    @classmethod
    def biz_ok(cls) -> list["Assertion"]:
        """SmartAdmin 统一信封业务成功断言：ok=true 且 code==0。"""
        return [
            cls(expected=True, op="eq", field="/ok", reason="业务信封 ok 字段须为 true（操作成功）"),
            cls(expected=0, op="eq", field="/code", reason="业务信封 code 字段须为 0（操作成功）"),
        ]

    @classmethod
    def biz_fail(cls, code) -> list["Assertion"]:
        """SmartAdmin 统一信封业务失败断言：ok=false 且 code==指定值。"""
        return [
            cls(expected=False, op="eq", field="/ok", reason=f"业务信封 ok 字段须为 false（操作失败，期望 code={code}）"),
            cls(expected=int(code), op="eq", field="/code", reason=f"业务信封 code 字段须为 {code}（与错误语义匹配）"),
        ]


@dataclass
class ApiCase:
    """一个接口用例：把接口信息汇总在一处。"""
    name: str                       # 接口中文名称
    method: str                     # 请求类型
    path: str                       # 接口链接（可含 ${var}）
    assertions: list[Assertion] = field(default_factory=list)
    body: dict | None = None        # 请求体
    params: dict | None = None      # query 参数
    save: dict = field(default_factory=dict)   # 动态参数提取 {"/id": "order_id"}
    # SmartAdmin 扩展：默认自动前置 biz_ok。失败用例或纯 HTTP 语义用例请设 False。
    biz_auto: bool = True


@dataclass
class FlowStep:
    """跨角色业务链中的一步：标注执行身份（role）与接口用例。

    role 对应 .env SA_ROLES_JSON 的角色键（admin/reporter/auditor）；
    run_flow_as 会按 step.role 取对应会话执行 run_case。
    """
    role: str                       # 执行身份：admin / reporter / auditor
    case: ApiCase                   # 该步骤要执行的接口用例
    label: str | None = None        # 可选：步骤中文说明（默认用 case.name）


@dataclass
class FlowCase:
    """一条业务链用例：多步接口按顺序执行，步间用 save + ${var} 串联。

    等价于 BDD 的一条 Gherkin 场景（如 创建 → 查询 → 删除 → 再查 404），
    但纯 pytest 声明；跨角色场景下每一步可指定不同角色（FlowStep.role），
    由 run_flow_as 按角色切换会话执行。
    """
    name: str                       # 业务链中文名称
    steps: list[FlowStep | ApiCase] = field(default_factory=list)


@dataclass
class StepResult:
    """单条断言的求值结果。"""
    ok: bool
    desc: str                       # 人类可读描述（用于打印）
    expected: Any
    actual: Any
    reason: str | None = None


@dataclass
class CaseResult:
    """整个接口 case 的运行结果。"""
    passed: bool
    failure_summary: str | None = None


def _tokenize(path: str) -> list[str | int]:
    """把字段路径切成访问序列。

    「点号」与「斜杠」都作为层级分隔符，兼容两种书写习惯：
      - /data.id             -> ["data", "id"]
      - /data/id             -> ["data", "id"]
      - /items[0].sku        -> ["items", 0, "sku"]
      - errors["items[0].sku"] -> ["errors", "items[0].sku"]
    """
    tokens: list[str | int] = []
    path = path.strip().lstrip("/")
    i, n = 0, len(path)

    def push(buf: str):
        if buf:
            tokens.append(buf)

    while i < n:
        ch = path[i]
        if ch == "[":
            # 找到与这个 [ 配对的 ]：引号内整体消费，`items[0]` 的 ] 在引号里不当作结束
            j = i + 1
            if j < n and path[j] == '"':
                j += 1
                while j < n:
                    if path[j] == "\\":
                        j += 2
                        continue
                    if path[j] == '"':
                        break
                    j += 1
                j += 1  # 越过结束引号
            end = path.find("]", j)
            if end < 0:
                raise ValueError(f"非法的字段路径（缺 ]）: {path}")
            inner = path[i + 1:end]
            tokens.append(int(inner) if inner.strip().isdigit() else inner.strip().strip('"\''))
            i = end + 1
        elif ch in (".", "/"):
            i += 1
        else:
            j = i
            while j < n and path[j] not in (".", "/", "["):
                j += 1
            push(path[i:j])
            i = j
    return tokens


def _dig(data: dict, path: str):
    """从响应 JSON 按路径取值。支持点号层级、数组下标、`["带点号的键"]` 取键。"""
    node: Any = data
    for tok in _tokenize(path):
        if isinstance(tok, int):
            if not isinstance(node, list) or tok >= len(node):
                raise KeyError(f"列表下标越界: {tok}")
            node = node[tok]
        else:
            if not isinstance(node, dict) or tok not in node:
                raise KeyError(f"响应中不存在字段: {tok}")
            node = node[tok]
    return node


_BOOL_WORDS = {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False}


def _coerce_bool_str(exp: object, actual: Any) -> tuple:
    """AI 生成的用例常把布尔期望值写成字符串（如 expected="true"），而
    响应 JSON 里是真正的 bool（True/False），导致 "true" == True 恒为 False。
    仅在 eq/ne 比较前把「字符串布尔字面量」与「布尔量」归一为同一种类型。"""
    if isinstance(exp, str) and exp.lower() in _BOOL_WORDS and not isinstance(actual, str):
        return _BOOL_WORDS[exp.lower()], actual
    if isinstance(actual, str) and actual.lower() in _BOOL_WORDS and not isinstance(exp, str):
        return exp, _BOOL_WORDS[actual.lower()]
    return exp, actual


def _eval(exp: object, actual: Any, op: str) -> bool:
    if op == "eq":
        exp, actual = _coerce_bool_str(exp, actual)
        return bool(exp == actual)
    if op == "ne":
        exp, actual = _coerce_bool_str(exp, actual)
        return bool(exp != actual)
    if op == "exists":
        return bool(actual is not None)
    if op == "contains":
        return actual is not None and exp in (actual or "")
    if op == "in":
        return actual is not None and actual in exp
    if op == "gt":
        return bool(actual is not None and actual > exp)
    if op == "gte":
        return bool(actual is not None and actual >= exp)
    if op == "lt":
        return bool(actual is not None and actual < exp)
    if op == "lte":
        return bool(actual is not None and actual <= exp)
    if op == "regex":
        return bool(re.search(str(exp), str(actual or "")))
    raise ValueError(f"不支持的断言操作符: {op}")


def _status_check(assertion: Assertion, status: int) -> bool:
    exp = assertion.expected
    codes = exp if isinstance(exp, (list, tuple)) else [exp]
    return status in codes


def evaluate(assertion: Assertion, status: int, payload: Any) -> StepResult:
    """对单条断言求值，返回可读结果。"""
    if assertion.field is None:
        ok = _status_check(assertion, status)
        expected = assertion.expected
        actual = status
        desc = f"状态码 = {expected}"
    else:
        try:
            actual = _dig(payload, assertion.field)
        except KeyError as exc:
            actual = None
        ok = _eval(assertion.expected, actual, assertion.op)
        expected = assertion.expected
        desc = f"{assertion.field} {assertion.op} {expected}"
    reason = assertion.reason
    if not ok and reason is None:
        reason = f"预期 {desc}，实际值为 {actual}"
    return StepResult(ok=ok, desc=desc, expected=expected, actual=actual, reason=reason)


def run_case(api_client, ctx: ScenarioContext, case: ApiCase) -> CaseResult:
    """执行一个接口 case：发请求 → 逐条断言 → 提取动态参数 → 返回汇总。

    SmartAdmin 信封守卫（本函数唯一的隐式行为，保证非信封响应接口不被污染）：
      1. case.biz_auto 为 True；
      2. payload 是 dict 且含 "ok" 键（即 SmartAdmin 信封）；
      3. case.assertions 中**尚未**显式包含 "/ok" 或 "/code" 字段断言。
      同时满足以上 3 条时，自动在 assertions 列表前面插入 Assertion.biz_ok()。
      如果断言失败用例：请显式 case.biz_auto=False + 写 Assertion.biz_fail(code=X)。
    """
    resp = api_client.request(
        case.method, ctx.bind(case.path),
        params=ctx.bind(case.params), json=ctx.bind(case.body),
        name=case.name, desc=case.name,
    )
    payload = None
    try:
        payload = resp.json()
    except Exception:
        payload = None

    # 信封守卫：只有 SmartAdmin 信封 + biz_auto + 尚未断言 ok/code 才自动追加
    assertions = list(case.assertions)
    _already_has_biz_fields = any(
        a.field is not None and a.field.lstrip("/").startswith(("ok", "code"))
        for a in assertions
    )
    if (
        case.biz_auto
        and isinstance(payload, dict)
        and "ok" in payload
        and not _already_has_biz_fields
    ):
        assertions[0:0] = Assertion.biz_ok()

    steps = [evaluate(a, resp.status_code, payload) for a in assertions]

    # 组装人类可读的「断言数据」（期望信封 code+msg + 用例自身断言字段，全 JSON 合并）：
    #   - code 取断言期望值（biz_ok→0 / biz_fail→业务码 / 用户显式 code）；
    #   - msg 优先取断言期望值；未显式断言（或仅 exists）时展示实际返回的 msg；
    #   - 其余用例断言字段按「最后一段路径」为键合并：eq 展示真实返回值；
    #     比较/条件型断言（gt/lt/contains/regex 等）把操作符写进值（如 "total": "> 0"），
    #     避免把条件断言显示成精确值而误导阅读。
    code_expected, msg_expected = None, None
    for a in assertions:
        _f = (a.field or "").lstrip("/")
        if _f == "code":
            code_expected = a.expected
        elif _f == "msg" and a.op != "exists":
            msg_expected = a.expected
    if msg_expected is None and isinstance(payload, dict) and payload.get("msg") is not None:
        msg_expected = payload.get("msg")
    _env: dict = {}
    if code_expected is not None:
        _env["code"] = code_expected
    if msg_expected is not None:
        _env["msg"] = msg_expected
    _op_sym = {"ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
               "contains": "contains", "in": "in", "regex": "regex", "exists": "exists"}
    for a, s in zip(assertions, steps):
        _f = (a.field or "").lstrip("/")
        if not _f or _f in ("ok", "code", "msg") or _f in _env:
            continue
        key = _f.rstrip("/").split("/")[-1] or _f
        _env[key] = (
            s.actual if a.op == "eq" else
            "exists" if a.op == "exists" else
            f"{_op_sym[a.op]} {a.expected}"
        )
    display_data = json.dumps(_env, ensure_ascii=False) if _env else ""

    api_client.record_assertions(
        case.name,
        [{
            "desc": s.desc, "expected": s.expected,
            "actual": s.actual, "ok": s.ok, "reason": s.reason,
        } for s in steps],
        data=display_data,
    )

    if not case.assertions:
        api_client.mark_expect([], resp.status_code, resp.text)

    # 动态参数：从响应提取字段存入上下文，供后续 case 用 ${var} 引用
    for path_expr, key in case.save.items():
        try:
            ctx.set(key, _dig(payload, path_expr) if payload is not None else None)
        except KeyError:
            ctx.set(key, None)

    if all(s.ok for s in steps):
        return CaseResult(passed=True)
    failed = [s for s in steps if not s.ok]
    summary = case.name + " 断言失败：" + "；".join(
        f"{s.desc}，实际={s.actual}，原因={s.reason}" for s in failed
    )
    return CaseResult(passed=False, failure_summary=summary)


def _flow_parts(step: FlowStep | ApiCase) -> tuple[str | None, ApiCase]:
    """解包 FlowCase.steps 元素：FlowStep -> (role, case)；ApiCase -> (None, case)。"""
    if isinstance(step, FlowStep):
        return step.role, step.case
    return None, step


def run_flow(api_client, ctx: ScenarioContext, flow: FlowCase) -> CaseResult:
    """执行一条业务链：逐步跑 ApiCase，任一步失败即中止并汇总。

    业务链语义：前一步 save 的动态参数供后续步骤 ${var} 引用；
    某步失败后，后续步骤缺少前置数据，不再执行（汇总中注明未执行的步数）。
    每步包一层 allure.step，Allure 报告里呈现与 Gherkin 步骤树等价的层级。
    """
    for idx, item in enumerate(flow.steps, start=1):
        _, case = _flow_parts(item)
        with allure.step(f"步骤 {idx}/{len(flow.steps)} · {case.name}"):
            result = run_case(api_client, ctx, case)
        if not result.passed:
            skipped = len(flow.steps) - idx
            summary = f"[{flow.name}] 第 {idx} 步失败：{result.failure_summary}"
            if skipped:
                summary += f"；后续 {skipped} 步未执行"
            return CaseResult(passed=False, failure_summary=summary)
    return CaseResult(passed=True)


def run_flow_as(role_clients: dict[str, Any],
                ctx: ScenarioContext, flow: FlowCase) -> CaseResult:
    """跨角色执行一条业务链：每步用 step.role 对应的独立会话（独立 token）。

    role_clients 形如 {"admin": ApiClient, "reporter": ApiClient, ...}。
    步骤必须为 FlowStep（带 role）；同 run_flow 语义：save/${var} 跨步串联、
    任一步失败即中止，失败信息包含「[角色]步骤名」便于定位。
    """
    total = len(flow.steps)
    for idx, item in enumerate(flow.steps, start=1):
        role, case = _flow_parts(item)
        if role is None:
            return CaseResult(passed=False, failure_summary=f"[{flow.name}] 第 {idx} 步未声明 role（需 FlowStep）")
        client = role_clients.get(role)
        if client is None:
            return CaseResult(passed=False,
                              failure_summary=f"[{flow.name}] 第 {idx} 步角色会话缺失：role={role}（未配置/未登录）")
        with allure.step(f"步骤 {idx}/{total} · [{role}] {case.name}"):
            result = run_case(client, ctx, case)
        if not result.passed:
            skipped = total - idx
            summary = f"[{flow.name}] 第 {idx} 步失败（角色 {role}）：{result.failure_summary}"
            if skipped:
                summary += f"；后续 {skipped} 步未执行"
            return CaseResult(passed=False, failure_summary=summary)
    return CaseResult(passed=True)