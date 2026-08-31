"""SmartAdmin 验收用例 stepdefs（登录 + 企业 CRUD）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/acceptance/smartadmin/steps/sa_common_steps.py`

所有步骤内部全部委托给 `support.api_case.run_case()`，这样：
  - 日志输出、接口块渲染、信封守卫、biz_ok/biz_fail 自动追加 100% 复用 L2 能力；
  - 后续 AI 生成自动化脚本可以直接照抄这些 step 函数模板。
  - Gherkin 文本可以评审。
"""
from __future__ import annotations

import os
from time import strftime

import pytest
from pytest_bdd import given, parsers, then, when

from support.api_case import ApiCase, Assertion, run_case
from support.clients.api_client import ApiClient
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import encrypt_sa_password


# =========================================================================
# 通用工具函数（Gherkin steps 共用）
# =========================================================================
def _sa_login_envelope(client: ApiClient, password: str | None = None) -> dict | None:
    """手动走一次 SmartAdmin 5 字段登录协议，返回信封（不抛异常，供断言使用）。

    与 conftest 的 _sa_login 区别：
      - 这个版本**不自动成功**，故意返回 raw 信封，用来验证「正确密码成功 / 错误密码失败」。
      - 用 api_client.request() 走，这样 history 里有接口块，日志能看到。
    """
    base = client.base_url.rstrip("/")
    login_name = os.getenv("SA_LOGIN_NAME", "admin").strip()
    real_pwd = password if password is not None else os.getenv("SA_PASSWORD", "").strip()
    device = int(os.getenv("SA_LOGIN_DEVICE", "1").strip() or "1")

    # Step1: GET captcha。这里不用 raw httpx，直接用 request() 让日志里有记录。
    cap_case = ApiCase(
        name="登录-获取验证码",
        method="GET",
        path="/login/getCaptcha",
        biz_auto=False,  # 这里不判业务 ok，只为了 save captchaUuid / captchaText
        assertions=[
            Assertion(expected=True, op="exists", field="/data/captchaUuid"),
            Assertion(expected=True, op="exists", field="/data/captchaText"),
        ],
        save={
            "/data/captchaUuid": "cap_uuid",
            "/data/captchaText": "cap_text",
        },
    )
    ctx_capture = ScenarioContext()
    r = run_case(client, ctx_capture, cap_case)
    if not r.passed:
        pytest.fail(f"获取验证码阶段失败: {r.failure_summary}")
    cap_uuid = ctx_capture.get("cap_uuid")
    cap_text = ctx_capture.get("cap_text")

    # Step2: POST login body
    login_case = ApiCase(
        name="登录-请求",
        method="POST",
        path="/login",
        body={
            "loginName": login_name,
            # 与 sa_login 一致：后端比对的是前端 SM4 加密形态，明文必然报密码错误
            "password": encrypt_sa_password(real_pwd),
            "captchaCode": cap_text,
            "captchaUuid": cap_uuid,
            "loginDevice": device,
        },
        biz_auto=False,  # 外部步骤按「成功/失败」决定断言，不要自动判
        assertions=[],
        save={"/code": "last_login_code", "/ok": "last_login_ok", "/data/token": "last_login_token"},
    )
    r2 = run_case(client, ctx_capture, login_case)
    # 登录成功则把 token 挂到会话上，后续企业步骤请求自动带 Authorization 头
    token = ctx_capture.get("last_login_token")
    if token:
        client.token = token
    # 登录 case 断言我们放到 caller then 步骤里做（Gherkin 语义）
    envelope_body = {"ok": ctx_capture.get("last_login_ok"), "code": ctx_capture.get("last_login_code")}
    # 额外把 envelope 作为属性挂到 client 上，供下一步断言用
    setattr(client, "_bdd_last_login_env", envelope_body)
    return envelope_body


# =========================================================================
# login.feature steps
# =========================================================================
@given("我已拥有 SmartAdmin 的管理员账号密码", target_fixture="_sa_has_creds")
def _step_given_has_creds():
    pwd = os.getenv("SA_PASSWORD", "").strip()
    if not pwd:
        pytest.skip("未配置 SA_PASSWORD，请在项目根 .env 里填写 admin 真实密码")
    return True


@when(parsers.parse("我发起 登录 请求，使用管理员的 {kind} 账号密码组合"))
def _step_when_login(api_client, kind: str):
    if kind == "正确":
        _sa_login_envelope(api_client, password=None)  # None → 用 SA_PASSWORD env
    elif kind == "错误":
        _sa_login_envelope(api_client, password="Wrong@Pass123_故意错误密码")
    else:
        pytest.fail(f"未知登录 kind={kind}（仅支持「正确」或「错误」）")


@then(parsers.parse("业务信封 返回 成功 即 ok=true 且 code={expected_code}"))
def _step_then_login_ok(api_client, expected_code: str):
    env = getattr(api_client, "_bdd_last_login_env", None) or {}
    code = 0 if expected_code == "0" else int(expected_code)
    assert env.get("ok") is True, f"信封 ok={env.get('ok')}，期望 true"
    assert env.get("code") == code, f"信封 code={env.get('code')}，期望 {code}"


@then("业务信封 返回 失败，即 ok=false，且 code 不等于 0")
def _step_then_login_fail(api_client):
    from support.fixtures.smartadmin import SA_CODES  # noqa: F401 留作后续精确断言比较使用
    env = getattr(api_client, "_bdd_last_login_env", None) or {}
    # 没显式探测登录失败码，但根据响应 ok=false 的 code 就是登录失败码。
    assert env.get("ok") is False, (
        f"登录期望失败（ok=false），实际 envelope={env}。"
        "注意：错误密码是否触发了 biz_fail，若返回 biz_ok 说明 SmartAdmin 代码逻辑不同？"
    )
    assert isinstance(env.get("code"), int) and env.get("code") != 0, (
        f"登录失败期望 code!=0，实际 code={env.get('code')}"
    )


# =========================================================================
# enterprise.feature steps
# =========================================================================
@given("SmartAdmin 会话已经完成登录（由 api_client fixture session 级自动登录）")
def _step_given_already_logged_in(api_client):
    """空校验：api_client fixture(session 级) 创建时已经调过 _sa_login。
    如果没密码会在 collection 时 SKIP，不会走到这一步。"""
    return True


@when(parsers.parse("我调用 企业 创建接口，入参 企业名=\"{name}\"，联系人=\"{contact}\"，手机号=\"{phone}\""))
def _step_when_create_ent(api_client, ctx: ScenarioContext,
                          name: str, contact: str, phone: str):
    # Gherkin Examples 里 `${ts_token}` 占位 → ctx.bind 替换
    name = ctx.bind(name)
    contact = ctx.bind(contact)
    phone = ctx.bind(phone)
    uscc = "91" + f"{abs(hash(name)) % 10**14:014d}Y"

    case = ApiCase(
        name="企业-BDD-创建",
        method="POST",
        path="/oa/enterprise/create",
        body={
            "enterpriseName": name,
            "contact": contact,
            "contactPhone": phone,
            "disabledFlag": False,
            "unifiedSocialCreditCode": uscc,
        },
        assertions=[],  # biz_ok 由信封守卫自动追加（该后端 create 返回 data=null）
        save={},
    )
    result = run_case(api_client, ctx, case)
    assert result.passed, f"创建企业失败: {result.failure_summary}"
    # 该后端 create 不回传任何字段，企业名由本步骤直接写入上下文供后续断言用
    ctx.set("last_ent_name", name)


@then("创建 业务信封成功，保存 ent_id 到上下文，并且注册清理")
def _step_then_create_success(ctx: ScenarioContext):
    # 该后端 create 不回传 id，ent_id 由「分页反查」步骤 save（见分页步骤），
    # 这里只断言创建链路成功 + 企业名已写入上下文。
    ent_name = ctx.get("last_ent_name")
    assert ent_name is not None, "上下文 last_ent_name 不存在 — run_case save 没生效"


@when(parsers.parse("我调用 企业 分页查询接口，关键字=\"{keywords}\"，pageSize={page_size:d}"))
def _step_when_page_query(api_client, ctx: ScenarioContext, cleanup_registry, keywords: str, page_size: int):
    keywords = ctx.bind(keywords)
    case = ApiCase(
        name="企业-BDD-分页查询",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": page_size, "keywords": keywords},
        assertions=[
            Assertion(expected=1, op="gte", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list[0]"),
        ],
        save={
            "/data/list[0]/enterpriseId": "page_first_ent_id",
            "/data/list[0]/enterpriseName": "page_first_ent_name",
            "/data/total": "page_total",
        },
    )
    # 存 keywords 到 ctx，供下一步断言"企业名包含关键字"
    ctx.set("expected_keywords", keywords)
    result = run_case(api_client, ctx, case)
    assert result.passed, f"分页查询失败: {result.failure_summary}"
    # 创建接口不回传 id，这里反查到真实 enterpriseId 后注册清理（session teardown 兜底删除）
    ent_id = ctx.get("page_first_ent_id")
    if ent_id is not None:
        cleanup_registry.register_delete("/oa/enterprise/delete/{id}", ent_id)


@then(parsers.parse("分页 业务信封成功，返回 total>=1，且第 1 条记录企业名包含 \"{keywords}\""))
def _step_then_page_ok(ctx: ScenarioContext, keywords: str):
    keywords = ctx.bind(keywords)
    total = ctx.get("page_total")
    first = ctx.get("page_first_ent_name")
    assert isinstance(total, int) and total >= 1, f"total={total} 期望 >=1"
    assert keywords in str(first), f"第 1 条企业名 {first} 不包含关键字 {keywords}"


# =========================================================================
# RBAC 多角色通用步骤：以 {角色} 身份调用 企业 {操作} 接口（role_access_flow.feature）
# =========================================================================
def _resolve_ent_id(client, name: str) -> int | None:
    """按企业名分页反查 enterpriseId（创建接口不回传 id）。"""
    resp = client.request("POST", "/oa/enterprise/page/query",
                          json={"pageNum": 1, "pageSize": 10, "keywords": name},
                          name=f"反查[{name}]")
    try:
        body = resp.json()
    except Exception:
        return None
    lst = (body.get("data") or {}).get("list") or []
    return lst[0].get("enterpriseId") if lst else None


@when(parsers.re(r'以 "(?P<role>[^"]+)" 身份调用 企业 (?P<op>创建|详情|修改|删除)接口，企业名="(?P<name>[^"]*)"'))
def _step_when_role_enterprise_op(role_registry, ctx: ScenarioContext,
                                  role: str, op: str, name: str):
    """通用跨角色企业操作：创建 / 详情 / 修改 / 删除，身份由 role 决定（独立 token 会话）。

    采用 parsers.re 匹配，兼容企业名里的 `${ts_token}` 占位符（运行时由 ctx.bind 替换）。
    结果（ok/code）写入 ctx.role_last_env，供 then 步骤断言。
    """
    client = role_registry[role]  # 懒登录对应角色（缺失账号时 pytest.skip）
    name = ctx.bind(name)
    ctx.set("role_last_env", None)

    if op == "创建":
        body = {
            "enterpriseName": name,
            "contact": "填报员甲",
            "contactPhone": "1380000" + f"{abs(hash(name)) % 10000:04d}",
            "disabledFlag": False,
            "unifiedSocialCreditCode": "9111" + f"{abs(hash(name)) % 10**8:08d}" + "Y",
        }
        resp = client.request("POST", "/oa/enterprise/create", json=body, name=f"[{role}]创建企业")
    elif op == "详情":
        ent_id = _resolve_ent_id(client, name) or ctx.get("ent_id")
        resp = client.request("GET", f"/oa/enterprise/get/{ent_id}", name=f"[{role}]详情查询")
    elif op == "修改":
        ent_id = _resolve_ent_id(client, name) or ctx.get("ent_id")
        body = {
            "enterpriseName": name,
            "contact": "修改人-" + role,
            "contactPhone": "1390000" + f"{abs(hash(name)) % 10000:04d}",
            "disabledFlag": False,
            "unifiedSocialCreditCode": "9111" + f"{abs(hash(name)) % 10**8:08d}" + "Y",
            "enterpriseId": ent_id,
        }
        resp = client.request("POST", "/oa/enterprise/update", json=body, name=f"[{role}]修改企业")
    elif op == "删除":
        ent_id = _resolve_ent_id(client, name) or ctx.get("ent_id")
        resp = client.request("GET", f"/oa/enterprise/delete/{ent_id}", name=f"[{role}]删除企业")
    else:
        pytest.fail(f"未知企业操作 op={op}（支持：创建/详情/修改/删除）")

    try:
        env = resp.json()
    except Exception:
        env = None
    ctx.set("role_last_env", env if isinstance(env, dict) and "ok" in env else None)
    ctx.set("role_last_ok", bool(env and env.get("ok") is True and env.get("code") == 0))


@then("业务信封 返回成功")
def _step_then_role_op_ok(ctx: ScenarioContext):
    ok = ctx.get("role_last_ok")
    env = ctx.get("role_last_env") or {}
    assert ok is True, f"期望业务信封成功(ok=true,code=0)，实际 env={env}"


@then("业务信封 返回失败（越权无权限）")
def _step_then_role_op_forbidden(ctx: ScenarioContext):
    from support.fixtures.smartadmin import SA_CODES

    env = ctx.get("role_last_env") or {}
    code = SA_CODES.get("forbidden")
    assert env.get("ok") is False, f"期望越权拒绝(ok=false)，实际 env={env}"
    if code is not None:
        assert env.get("code") == code, f"期望拒绝码={code}，实际={env.get('code')}，env={env}"
