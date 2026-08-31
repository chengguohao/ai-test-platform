"""SmartAdmin L2 接口测试：RBAC 跨角色业务流（企业模块权限序列）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/api/smartadmin/test_role_access_flow.py`

演示「管理员新增 → 填报员修改 → 审核员审核 → 打回(越权拒绝) → 填报员重提 → 管理员报送/最终删除」：
  - admin   : 创建企业A + 分页反查 enterpriseId（save ent_id）→ 全部权限
  - reporter: 详情查询（可见）+ 修改企业（填报员负责修改）→ 可读写所负责数据
  - auditor : 详情查询（审核阶段只读 OK）+ 尝试修改（越权，断言 biz_fail(forbidden)）
  - reporter: 重新修改（打回后重提）
  - admin   : 删除（报送/归档语义）

与 test_enterprise_crud.py 同款「parametrize 展开 + module 级 ctx 串联」模式：
  - 每个 FlowStep = 一条**独立 pytest 节点**（PyCharm 左侧每条接口一节点，可单独看结果）
  - 批量跑时按声明顺序执行完整业务流，save/${var} 跨步骤传值
  - 之所以不用"单个 test 函数 + 流程引擎(run_flow_as)"：PyCharm 左侧只有 1 个节点，
    parametrize 展开是 PyCharm 原生支持的，与 test_enterprise_crud.py 体验完全一致

说明：企业模块无真实"审核/打回/报送"接口，此处以「角色权限序列 + 越权断言」表达
阶段语义；真实审批流接口接入后只需替换对应操作步骤，框架不变。

依赖：.env SA_ROLES_JSON 需配置 reporter / auditor 账号（缺任意角色则该用例 SKIP）。
"""
from __future__ import annotations

import time

import allure
import pytest

from support.api_case import ApiCase, Assertion, FlowStep, run_case
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import SA_CODES

pytestmark = [pytest.mark.smartadmin, pytest.mark.api,
              pytest.mark.requires_role("reporter"),
              pytest.mark.requires_role("auditor")]

# 唯一前缀：保证不同批次运行不与企业重名
_TS = time.strftime("RBAC%m%d%H%M%S")
ENT_NAME = f"{_TS}_企业A"
ENT_NAME_FILLED = f"{ENT_NAME}_已填报"
ENT_NAME_RETRY = f"{ENT_NAME}_重提"


def _create_body(name: str) -> dict:
    suffix = f"{abs(hash(name)) % 10**8:08d}"
    return {
        "enterpriseName": name,
        "contact": "填报员甲",
        "contactPhone": "138" + suffix[:8],
        "disabledFlag": False,
        "unifiedSocialCreditCode": "9111" + suffix + "Y",
    }


# ---------------------------------------------------------------------------
# 跨角色企业流程（权限序列）：每个 FlowStep 携带执行角色 role，
# 由 parametrize 展开成 N 条独立测试节点（PyCharm 左侧每条接口一节点）。
# ---------------------------------------------------------------------------
FLOW_STEPS: list[FlowStep] = [
    # 1. 管理员：新增企业
    FlowStep("admin", ApiCase(
        name="管理员-创建企业",
        method="POST",
        path="/oa/enterprise/create",
        body=_create_body(ENT_NAME),
        assertions=[],  # biz_ok 信封守卫自动追加（create 返回 data=null）
    )),
    # 2. 管理员：分页反查 enterpriseId（save ent_id）
    FlowStep("admin", ApiCase(
        name="管理员-分页反查id",
        method="POST",
        path="/oa/enterprise/page/query",
        body={"pageNum": 1, "pageSize": 10, "keywords": ENT_NAME},
        save={"/data/list[0]/enterpriseId": "ent_id"},
        assertions=[
            Assertion(expected=1, op="gte", field="/data/total",
                      reason="按企业名反查应命中 1 条"),
            Assertion(expected=ENT_NAME, op="eq", field="/data/list[0]/enterpriseName",
                      reason="反查首条企业名一致"),
        ],
    )),
    # 3. 填报员：详情查询（可见）
    FlowStep("reporter", ApiCase(
        name="填报员-详情查询",
        method="GET",
        path="/oa/enterprise/get/${ent_id}",
        assertions=[
            Assertion(expected=ENT_NAME, op="eq", field="/data/enterpriseName",
                      reason="填报员可读企业详情"),
        ],
    )),
    # 4. 填报员：修改企业（填报员负责修改）
    FlowStep("reporter", ApiCase(
        name="填报员-修改企业(填报)",
        method="POST",
        path="/oa/enterprise/update",
        body=dict(_create_body(ENT_NAME_FILLED), enterpriseId="${ent_id}"),
        assertions=[],  # biz_ok 自动
    )),
    # 5. 审核员：详情查询（审核阶段只读 OK）
    FlowStep("auditor", ApiCase(
        name="审核员-详情查询(审核只读)",
        method="GET",
        path="/oa/enterprise/get/${ent_id}",
        assertions=[
            Assertion(expected=ENT_NAME_FILLED, op="eq", field="/data/enterpriseName",
                      reason="审核员可读企业详情（只读阶段）"),
        ],
    )),
    # 6. 审核员越权尝试修改 → 期望 biz_fail(forbidden)；断言在 test 函数动态注入
    FlowStep("auditor", ApiCase(
        name="审核员-越权修改(应拒绝)",
        method="POST",
        path="/oa/enterprise/update",
        body=dict(_create_body(f"{ENT_NAME}_越权"), enterpriseId="${ent_id}"),
        biz_auto=False,
        assertions=[],  # 动态注入 biz_fail(forbidden)
    )),
    # 7. 填报员：打回后重提
    FlowStep("reporter", ApiCase(
        name="填报员-重新修改(打回重提)",
        method="POST",
        path="/oa/enterprise/update",
        body=dict(_create_body(ENT_NAME_RETRY), enterpriseId="${ent_id}"),
        assertions=[],
    )),
    # 8. 管理员：删除归档（报送/最终操作语义）
    FlowStep("admin", ApiCase(
        name="管理员-删除归档(报送)",
        method="GET",
        path="/oa/enterprise/delete/${ent_id}",
        assertions=[],  # biz_ok 自动
    )),
]

# 越权步骤名 → 需要 SA_CODES 的键（探测不到则 SKIP）
_FORBIDDEN_STEP = "审核员-越权修改(应拒绝)"
# 反查 id 步骤成功后，把 ent_id 注册进清理注册表（session teardown 兜底删除）
_SAVE_ENT_ID_STEP = "管理员-分页反查id"


@allure.feature("SmartAdmin · RBAC 跨角色流程")
@allure.story("企业模块：多角色权限序列 + 越权断言")
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_enterprise_role_access_step(role_registry, ctx: ScenarioContext,
                                     cleanup_registry, step: FlowStep):
    """每个接口步骤 = 一条独立 pytest 节点（PyCharm 左侧每条接口一节点）。

    批量跑时按声明顺序执行完整业务流：管理员→填报员→审核员→(打回)→填报员→管理员，
    save/${var} 通过 module 级 ctx 跨步骤串联（与 test_enterprise_crud.py 同款模式）。
    """
    # 越权步骤：动态注入 biz_fail(forbidden) 断言（业务码 session 运行时才确定）
    if step.label == _FORBIDDEN_STEP or step.case.name == _FORBIDDEN_STEP:
        forbidden_code = SA_CODES.get("forbidden")
        if forbidden_code is None:
            pytest.skip("session 内未探测到越权业务码 forbidden，跳过越权断言步骤")
        step.case.assertions = Assertion.biz_fail(code=forbidden_code)
        step.case.assertions.append(
            Assertion(expected=True, op="exists", field="/msg", reason="拒绝时 msg 非空"))

    # 懒登录该角色的独立会话（独立 token）；role_registry 是 session 级共享缓存
    client = role_registry[step.role]
    result = run_case(client, ctx, step.case)

    # 反查 id 步骤成功后：ent_id 已入 ctx，注册清理（session teardown 兜底删除）
    if result.passed and step.case.name == _SAVE_ENT_ID_STEP:
        ent_id = ctx.get("ent_id")
        if ent_id is not None:
            cleanup_registry.register_delete("/oa/enterprise/delete/{id}", ent_id)

    assert result.passed, f"[{step.role}] {step.case.name}: {result.failure_summary}"


if __name__ == "__main__":  # pragma: no cover
    pass
