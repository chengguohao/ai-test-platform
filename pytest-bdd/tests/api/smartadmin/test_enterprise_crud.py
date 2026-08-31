"""SmartAdmin MVP: OA-企业 /oa/enterprise 模块 L2 接口声明式 ApiCase 9 条。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/api/smartadmin/test_enterprise_crud.py`

执行顺序（parametrize 按列表顺序，用 `ctx` (module 级 ScenarioContext) 串联 ent_id:
  [C1] 创建企业 → 成功 save id 到 ctx ent_id
  [C2] 创建同名企业 → 失败 biz_fail(dup_enterprise)
  [P1] 分页查询无关键字 → biz_ok + data.total 存在
  [P2] 分页查询关键字=企业A名 → biz_ok + data.list[0].enterpriseName 命中
  [D1] 详情查询 ent_id → biz_ok + data.enterpriseName == 企业A
  [U1] 修改 ent_id → biz_ok + data.enterpriseName == "企业A_已修改"
  [X1] 删除 ent_id → biz_ok
  [X2] 删除不存在超大 id → biz_fail(delete_not_exist)
  [U-AUTH] 独立 test 函数：新 ApiClient 不登录访问 GET get/1 → biz_fail(unauth)

业务码（dup/delete_not_exist/unauth）由 conftest 里 session 级 autouse fixture 首次
探测出来并写入 `tests.api.smartadmin.conftest.SA_CODES`。探测不到（SA_PASSWORD 空
或 SmartAdmin 离线）则自动 SKIP。
"""
from __future__ import annotations

import os
import time

import allure
import pytest

from support.api_case import ApiCase, Assertion, run_case
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import SA_CODES  # 探测到的业务失败信封 code 共享

# 唯一前缀：保证两次运行企业名不冲突（两次全跑间隔至少 1 秒即可）
_UNIQ = time.strftime("MVP_%m%d%H%M%S_")
ENT_A_NAME = f"{_UNIQ}企业A"
ENT_A_UPDATED_NAME = f"{_UNIQ}企业A_已修改"
ENT_A_PHONE = "13800138" + f"{abs(hash(ENT_A_NAME)) % 10000:04d}"  # 避免手机号重复校验
# 统一社会信用代码 18 位数字字母组合，MVP 用随机位即可（不做校验位）但保证字段合法格式
_USCC_BASE = "91" + f"{abs(hash(ENT_A_NAME)) % (10**14):014d}Y"


def _create_body(name: str) -> dict:
    """企业创建/更新 body 工厂。字段名来自 OpenAPI schema EnterpriseCreateForm。"""
    suffix = f"{abs(hash(name)) % 10**8:08d}"
    return {
        "enterpriseName": name,
        "contact": "张三",
        "contactPhone": "139" + suffix[:8],
        "disabledFlag": False,
        "unifiedSocialCreditCode": "9111" + suffix + "Y",
    }


# ---------------------------------------------------------------------------
# 9 条声明式 ApiCase（parametrize 顺序执行）
# 注意：该后端 create 成功返回 data=null（不回传实体），主键字段是 enterpriseId。
# 因此创建后需用「分页反查」拿到真实 enterpriseId 存入 ctx，供 D1/U1/X1 串联。
# ---------------------------------------------------------------------------
CASES: list[ApiCase] = [
    # C1：创建企业A（biz_ok 由信封守卫自动追加；响应 data=null，不做字段断言）
    ApiCase(
        name="企业-C1-创建成功",
        method="POST",
        path="/oa/enterprise/create",
        body=_create_body(ENT_A_NAME),
        assertions=[],
    ),
    # C1F：分页反查刚创建的企业 → save enterpriseId 到 ctx ent_id
    ApiCase(
        name="企业-C1-分页反查id",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": 10, "keywords": ENT_A_NAME},
        save={"/data/list[0]/enterpriseId": "ent_id"},
        assertions=[
            Assertion(expected=1, op="gte", field="/data/total",
                      reason="按企业名精确反查应至少命中 1 条"),
            Assertion(expected=ENT_A_NAME, op="eq", field="/data/list[0]/enterpriseName",
                      reason="反查首条 enterpriseName 应与创建入参一致（CLOSE 前缀区分重名）"),
        ],
    ),
    # C2：创建同名企业A，预期 biz_fail（duplicate name）
    ApiCase(
        name="企业-C2-创建重名失败",
        method="POST",
        path="/oa/enterprise/create",
        body=_create_body(ENT_A_NAME),  # 同名
        biz_auto=False,  # 失败 case：不要自动追加 biz_ok
        # assertions 在 test 函数里动态按 SA_CODES["dup_enterprise"] 注入
        assertions=[],
    ),
    # P1：分页查询（空关键字），断言 data.total 存在
    ApiCase(
        name="企业-P1-分页查询-空参数",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total",
                      reason="分页返回 data.total 必须存在"),
            Assertion(expected=0, op="gte", field="/data/pageNum",
                      reason="分页返回 data.pageNum >= 0"),
        ],
    ),
    # P2：分页查询，关键字=ENT_A_NAME，断言 list[0].enterpriseName 包含关键字
    ApiCase(
        name="企业-P2-分页查询-关键字搜索",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": 10, "keywords": ENT_A_NAME},
        assertions=[
            Assertion(expected=1, op="gte", field="/data/total",
                      reason="关键字精确匹配应至少命中 1 条"),
            Assertion(expected=ENT_A_NAME, op="in", field="/data/list[0]/enterpriseName",
                      reason=f"搜索结果首条 enterpriseName 应包含关键字「{ENT_A_NAME}」"),
        ],
    ),
    # D1：按 C1F save 的 ent_id 查询详情
    ApiCase(
        name="企业-D1-详情查询",
        method="GET",
        path="/oa/enterprise/get/${ent_id}",
        assertions=[
            Assertion(expected=ENT_A_NAME, op="eq", field="/data/enterpriseName",
                      reason="详情 enterpriseName 与创建入参一致"),
        ],
    ),
    # U1：修改 ent_id 名 → ENT_A_UPDATED_NAME（update 表单主键字段为 enterpriseId；响应 data=null）
    ApiCase(
        name="企业-U1-修改成功",
        method="POST",
        path="/oa/enterprise/update",
        body=dict(
            _create_body(ENT_A_UPDATED_NAME),
            enterpriseId="${ent_id}",  # ScenarioContext 绑定前一步反查的 enterpriseId
        ),
        assertions=[],  # biz_ok 自动由 run_case 信封守卫追加
    ),
    # U1F：修改后分页反查，验证新企业名已生效（update 不回传实体，需二次查询确认）
    ApiCase(
        name="企业-U1-分页验证修改生效",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": 10, "keywords": ENT_A_UPDATED_NAME},
        assertions=[
            Assertion(expected=1, op="gte", field="/data/total",
                      reason="修改后按新名称查询应命中 1 条"),
            Assertion(expected=ENT_A_UPDATED_NAME, op="eq", field="/data/list[0]/enterpriseName",
                      reason="修改后首条企业名应等于更新后的值"),
        ],
    ),
    # X1：删除 ent_id（GET /delete/{id}，SmartAdmin 删除是 GET）
    ApiCase(
        name="企业-X1-删除成功",
        method="GET",
        path="/oa/enterprise/delete/${ent_id}",
        assertions=[],  # biz_ok 自动由 run_case 信封守卫追加
    ),
    # X2：删除不存在的超大 id → biz_fail(delete_not_exist)
    ApiCase(
        name="企业-X2-删除不存在id-失败",
        method="GET",
        path="/oa/enterprise/delete/999999999",
        biz_auto=False,  # 失败 case：不要自动追加 biz_ok
        assertions=[],  # 动态注入 delete_not_exist 断言
    ),
]

# 用例名 → 需要的 SA_CODES 键（动态注入 biz_fail 前做检查）
_CODE_LOOKUP = {
    "企业-C2-创建重名失败": "dup_enterprise",
    "企业-X2-删除不存在id-失败": "delete_not_exist",
}


@pytest.mark.smartadmin
@pytest.mark.api
@allure.feature("SmartAdmin · OA企业模块")
@allure.story("接口 L2：CRUD + 异常用例")
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_enterprise_crud_case(api_client, ctx: ScenarioContext, cleanup_registry, case):
    # ---- 失败用例前置：如果 biz_fail code 还没探测到，skip ----
    key = _CODE_LOOKUP.get(case.name)
    if key is not None:
        code = SA_CODES.get(key)
        if code is None:
            pytest.skip(f"session 内未探测到业务码 {key}，跳过该 biz_fail 断言用例")
        # 动态填入 biz_fail 断言（因为 code 探测是 session runtime 才确定）
        case.assertions = Assertion.biz_fail(code=code)
        case.assertions.append(Assertion(expected="错误提示非空", op="exists", field="/msg"))

    result = run_case(api_client, ctx, case)

    # 分页反查用例成功后：ent_id 已入 ctx，注册清理（session teardown 兜底删除）
    if result.passed and case.name == "企业-C1-分页反查id":
        ent_id = ctx.get("ent_id")
        if ent_id is not None:
            cleanup_registry.register_delete("/oa/enterprise/delete/{id}", ent_id)

    assert result.passed, f"[{case.name}] {result.failure_summary}"


@pytest.mark.smartadmin
@pytest.mark.api
@allure.feature("SmartAdmin · 身份认证")
@allure.story("L2 异常：未登录访问企业接口，信封 biz_fail")
def test_enterprise_unauthorized_access(base_url):
    """独立用例：全新 ApiClient 不带任何登录 cookie，访问 OA-企业详情接口。

    用来同时：
      1. 证明 conftest 的 biz_auto 信封守卫 + biz_fail(code=unauth) 断言工作正常；
      2. 若探测到的 unauth code 正确，会触发 request() 内部的自动重登判断
         （但此函数内部新建的 ApiClient 未注册重登 hook，所以响应仍是 biz_fail）。
    """
    from support.clients.api_client import ApiClient
    from support.fixtures.smartadmin import SA_CODES

    pwd = os.getenv("SA_PASSWORD", "").strip()
    if not pwd:
        pytest.skip("SA_PASSWORD 空，smartadmin marker 已经在 collection 级 skip，这里双保险")

    unauth_code = SA_CODES.get("unauth")
    if unauth_code is None:
        pytest.skip("session 内未探测到「未登录业务码 unauth」，跳过该用例")

    client = ApiClient(base_url)
    ctx = ScenarioContext()
    # 故意不要调用 _sa_login，构造一个干净的匿名 ApiClient
    case = ApiCase(
        name="企业-UNAUTH-未登录访问详情",
        method="GET",
        path="/oa/enterprise/get/1",
        biz_auto=False,
        assertions=Assertion.biz_fail(code=unauth_code) + [
            Assertion(expected=True, op="exists", field="/msg", reason="失败场景 msg 字段须非空"),
        ],
    )
    try:
        result = run_case(client, ctx, case)
        assert result.passed, f"[UNAUTH] {result.failure_summary}"
    finally:
        client.close()
