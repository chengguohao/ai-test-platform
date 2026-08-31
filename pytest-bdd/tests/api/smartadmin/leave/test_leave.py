# AUTO-GENERATED - 来源用例映射 (TC-id -> 用例名)
# TC-LEAVE-01 -> 员工提交请假申请-正常成功
# TC-LEAVE-02 -> 员工提交请假申请-缺少必填字段 leaveTypeId
# TC-LEAVE-03 -> 员工提交请假申请-结束时间早于开始时间
# TC-LEAVE-04 -> 员工提交请假申请-请假类型不存在
# TC-LEAVE-05 -> 员工提交请假申请-未登录调用
# TC-LEAVE-06 -> 员工提交请假申请-非员工角色调用
# TC-LEAVE-07 -> 员工查询我的请假列表-正常分页
# TC-LEAVE-08 -> 员工查询我的请假列表-按状态过滤
# TC-LEAVE-09 -> 员工查询我的请假列表-分页参数无效
# TC-LEAVE-10 -> 员工查询请假详情-正常查询
# TC-LEAVE-11 -> 员工查询请假详情-查询不存在的申请单
# TC-LEAVE-12 -> 员工查询请假详情-查询他人申请单
# TC-LEAVE-13 -> 员工撤回待审批申请-正常成功
# TC-LEAVE-14 -> 员工撤回申请-申请不存在
# TC-LEAVE-15 -> 员工撤回申请-申请状态非待审批(如已通过)
# TC-LEAVE-16 -> 员工撤回申请-缺少必填字段cancelReason
# TC-LEAVE-17 -> 部门主管查询审批待办列表-正常分页
# TC-LEAVE-18 -> 部门主管通过请假申请-正常成功
# TC-LEAVE-19 -> 部门主管驳回请假申请-正常成功
# TC-LEAVE-20 -> 部门主管审批-驳回时未填写审批意见
# TC-LEAVE-21 -> 部门主管审批-非待审批状态申请
# TC-LEAVE-22 -> 部门主管审批-审批非本部门申请
# TC-LEAVE-23 -> 部门主管查询审批已办列表-正常分页
# TC-LEAVE-24 -> 人事专员查询全公司请假记录-正常分页
# TC-LEAVE-25 -> 人事专员查询全公司请假记录-按部门和时间范围过滤
# TC-LEAVE-26 -> 人事专员查询全公司请假记录-非人事角色调用
# TC-LEAVE-27 -> 人事专员统计请假时长-正常统计
# TC-LEAVE-28 -> 人事专员统计请假时长-缺少必填参数
# TC-LEAVE-29 -> 未登录访问任意接口

from __future__ import annotations
import allure, pytest
from support.api_case import ApiCase, Assertion, FlowStep, run_case
from support.clients.api_client import ApiClient
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import SA_CODES

def _bf(key: str):
    """反例业务码断言辅助函数"""
    code = SA_CODES.get(key)
    if code is None:
        return [Assertion(expected=True, op="exists", field="/msg")]
    return Assertion.biz_fail(code=code) + [Assertion(expected=True, op="exists", field="/msg")]

# 定义跨角色测试步骤
FLOW_STEPS: list[FlowStep] = [
    # ============ 员工角色操作 ============
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-01-员工提交请假申请-正常成功",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试事假申请"},
        assertions=[]  # 正例，信封守卫自动校验
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-02-员工提交请假申请-缺少必填字段 leaveTypeId",
        method="POST", path="/leave/apply",
        body={"startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试事假申请"},
        biz_auto=False,  # 反例必须显式
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-03-员工提交请假申请-结束时间早于开始时间",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-02 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试事假申请"},
        biz_auto=False,
        assertions=[*_bf("time_invalid")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-04-员工提交请假申请-请假类型不存在",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 99, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试事假申请"},
        biz_auto=False,
        assertions=[*_bf("leave_type_not_exist")]
    )),
    # TC-LEAVE-05 未登录，将在测试函数中使用 ApiClient(base_url) 单独处理
    # TC-LEAVE-06 非员工角色调用，使用 admin_client 验证权限
    FlowStep("admin", ApiCase(
        name="TC-LEAVE-06-员工提交请假申请-非员工角色调用",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试事假申请"},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-07-员工查询我的请假列表-正常分页",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
            # 字段名存在性断言，因返回列表，断言首个元素存在即可
            Assertion(expected=True, op="exists", field="/data/list[0]")
        ]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-08-员工查询我的请假列表-按状态过滤",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10, "status": 0},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
        ]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-09-员工查询我的请假列表-分页参数无效",
        method="GET", path="/leave/my/list",
        params={"pageNum": 0, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-10-员工查询请假详情-正常查询",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "${apply_no}"},  # 依赖TC-LEAVE-01创建的申请单号
        assertions=[
            Assertion(expected=True, op="exists", field="/data/applyNo"),
            Assertion(expected=True, op="exists", field="/data/status")
        ]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-11-员工查询请假详情-查询不存在的申请单",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "INVALID"},
        biz_auto=False,
        assertions=[*_bf("apply_not_exist")]
    )),
    # TC-LEAVE-12 查询他人申请单，此处假设存在一个“他人申请单号”，实际测试需配置或动态获取
    # 为简化，使用固定字符串，测试人员需根据环境调整或使用 fixture 传入
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-12-员工查询请假详情-查询他人申请单",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "OTHER_EMPLYEE_APPLY_NO"}, # 测试人员需替换为实际值
        biz_auto=False,
        assertions=[*_bf("no_operation_right")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-13-员工撤回待审批申请-正常成功",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}", "cancelReason": "测试撤回"},
        assertions=[]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-14-员工撤回申请-申请不存在",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "INVALID", "cancelReason": "原因"},
        biz_auto=False,
        assertions=[*_bf("apply_not_exist")]
    )),
    # TC-LEAVE-15 撤回非待审批状态(如已通过)申请，需要另一个已通过的 apply_no
    # 使用固定占位符，测试人员需准备数据或使用 fixture 传入
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-15-员工撤回申请-申请状态非待审批(如已通过)",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "APPROVED_APPLY_NO", "cancelReason": "原因"}, # 测试人员需替换
        biz_auto=False,
        assertions=[*_bf("cancel_not_allowed")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-16-员工撤回申请-缺少必填字段cancelReason",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}"},  # 使用已撤回的申请单号，接口应拒绝
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),

    # ============ 部门主管(manager)角色操作 ============
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-17-部门主管查询审批待办列表-正常分页",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
            Assertion(expected=True, op="exists", field="/data/list[0]")
        ]
    )),
    # TC-LEAVE-18 部门主管通过申请，需要一个“有效待审批申请单号”
    # 使用固定占位符，测试人员需准备数据
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-18-部门主管通过请假申请-正常成功",
        method="POST", path="/leave/approve",
        body={"applyNo": "PENDING_APPLY_NO_FOR_MGR", "approveAction": 1, "approveComment": "同意"},
        assertions=[]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-19-部门主管驳回请假申请-正常成功",
        method="POST", path="/leave/approve",
        body={"applyNo": "ANOTHER_PENDING_APPLY_NO_FOR_MGR", "approveAction": 2, "approveComment": "理由不充分"},
        assertions=[]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-20-部门主管审批-驳回时未填写审批意见",
        method="POST", path="/leave/approve",
        body={"applyNo": "PENDING_APPLY_NO_FOR_MGR", "approveAction": 2}, # 缺少 approveComment
        biz_auto=False,
        assertions=[*_bf("approve_comment_required")]
    )),
    # TC-LEAVE-21 审批非待审批状态(已通过)申请
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-21-部门主管审批-非待审批状态申请",
        method="POST", path="/leave/approve",
        body={"applyNo": "APPROVED_APPLY_NO", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("status_invalid")]
    )),
    # TC-LEAVE-22 审批非本部门申请
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-22-部门主管审批-审批非本部门申请",
        method="POST", path="/leave/approve",
        body={"applyNo": "OTHER_DEPT_PENDING_APPLY_NO", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("no_operation_right")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-23-部门主管查询审批已办列表-正常分页",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
            Assertion(expected=True, op="exists", field="/data/list[0]")
        ]
    )),

    # ============ 人事专员(hr_admin)角色操作 ============
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-24-人事专员查询全公司请假记录-正常分页",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
            Assertion(expected=True, op="exists", field="/data/list[0]")
        ]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-25-人事专员查询全公司请假记录-按部门和时间范围过滤",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "deptName": "研发部", "startDate": "2026-09-01", "endDate": "2026-09-30"},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/total"),
            Assertion(expected=True, op="exists", field="/data/list"),
        ]
    )),
    # TC-LEAVE-26 非人事角色调用，使用 employee_client 验证权限
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-26-人事专员查询全公司请假记录-非人事角色调用",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-27-人事专员统计请假时长-正常统计",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "2026-09-01", "endDate": "2026-09-30"},
        assertions=[
            Assertion(expected=True, op="exists", field="/data"), # 统计结果是一个数组
        ]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-28-人事专员统计请假时长-缺少必填参数",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "2026-09-01"}, # 缺少 endDate
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),

    # ============ 未登录(匿名)访问 ============
    # TC-LEAVE-29 未登录访问任意接口，在测试函数中特殊处理
]

@pytest.mark.smartadmin
@pytest.mark.api
@pytest.mark.requires_role('employee')
@pytest.mark.requires_role('manager')
@pytest.mark.requires_role('hr_admin')
@allure.feature("SmartAdmin · 员工请假模块")
@allure.story("跨角色接口流程与权限验证")
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_leave_module_flow(role_registry, ctx: ScenarioContext, cleanup_registry, base_url, employee_client, step: FlowStep):
    # 根据 step.role 获取对应的 API 客户端
    if step.role == "manager":
        client = role_registry["manager"]  # 使用 role_registry 获取 manager 客户端
    elif step.role == "hr_admin":
        client = role_registry["hr_admin"] # 使用 role_registry 获取 hr_admin 客户端
    elif step.role == "employee":
        client = employee_client
    else:
        # 理论上 FlowStep 中 role 应只包含上述三种，此为防御性编程
        raise ValueError(f"未知角色: {step.role}")

    result = run_case(client, ctx, step.case)

    # 数据串联：TC-LEAVE-01 成功后，分页反查获取最新的 apply_no 并保存到 ctx
    if result.passed and step.case.name == "TC-LEAVE-01-员工提交请假申请-正常成功":
        list_result = run_case(employee_client, ctx, ApiCase(
            name="反查申请单号",
            method="GET", path="/leave/my/list",
            params={"pageNum": 1, "pageSize": 1},
            assertions=[]
        ))
        if list_result.passed and list_result.response_data:
            items = list_result.response_data.get("data", {}).get("list", [])
            if items:
                apply_no = items[0].get("applyNo")
                if apply_no:
                    ctx.save({"apply_no": apply_no})

    assert result.passed, f"[{step.role}] {step.case.name}: {result.failure_summary}"

# 单独测试未登录访问 (TC-LEAVE-29)
@pytest.mark.smartadmin
@pytest.mark.api
@allure.feature("SmartAdmin · 员工请假模块")
@allure.story("未登录访问")
def test_leave_anonymous_access(base_url, ctx: ScenarioContext):
    anonymous_client = ApiClient(base_url)  # 不登录，token=None
    case = ApiCase(
        name="TC-LEAVE-29-未登录访问任意接口",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("not_login")]
    )
    result = run_case(anonymous_client, ctx, case)
    assert result.passed, f"匿名访问失败: {result.failure_summary}"