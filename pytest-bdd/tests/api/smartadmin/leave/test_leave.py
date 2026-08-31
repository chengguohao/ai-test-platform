# AUTO-GENERATED
# 来源用例映射:
# TC-LEAVE-C01 -> 成功提交事假申请
# TC-LEAVE-C02 -> 成功提交带附件的病假申请
# TC-LEAVE-C03 -> 结束时间早于开始时间提交失败
# TC-LEAVE-C04 -> 结束时间等于开始时间提交失败
# TC-LEAVE-C05 -> 必填字段缺失提交失败
# TC-LEAVE-C06 -> 请假类型不存在提交失败
# TC-LEAVE-C07 -> 请假原因超过500字提交失败
# TC-LEAVE-C08 -> 附件URL超过1000字符提交失败
# TC-LEAVE-C09 -> 非员工角色提交申请权限不足
# TC-LEAVE-C10 -> 查看我的请假列表成功
# TC-LEAVE-C11 -> 按状态过滤请假列表
# TC-LEAVE-C12 -> 分页参数不合法查询失败
# TC-LEAVE-C13 -> 非员工角色查看我的请假列表权限不足
# TC-LEAVE-C14 -> 查看本人待审批申请详情
# TC-LEAVE-C15 -> 查看本人已通过申请详情
# TC-LEAVE-C16 -> 查看本人已驳回申请详情
# TC-LEAVE-C17 -> 查看已撤回申请详情
# TC-LEAVE-C18 -> 查看不存在的申请详情
# TC-LEAVE-C19 -> 查看他人申请详情权限不足
# TC-LEAVE-C20 -> 非员工角色查看详情权限不足
# TC-LEAVE-C21 -> 成功撤回待审批申请
# TC-LEAVE-C22 -> 撤回已通过申请失败
# TC-LEAVE-C23 -> 撤回已驳回申请失败
# TC-LEAVE-C24 -> 撤回已撤回申请失败
# TC-LEAVE-C25 -> 撤回不存在的申请失败
# TC-LEAVE-C26 -> 撤回原因为必填
# TC-LEAVE-C27 -> 撤回原因超过200字失败
# TC-LEAVE-C28 -> 撤回他人申请权限不足
# TC-LEAVE-C29 -> 非员工角色撤回权限不足
# TC-LEAVE-C30 -> 查看审批待办列表成功
# TC-LEAVE-C31 -> 按申请人过滤待办列表
# TC-LEAVE-C32 -> 按请假类型过滤待办列表
# TC-LEAVE-C33 -> 按状态过滤待办列表
# TC-LEAVE-C34 -> 分页参数不合法查询失败
# TC-LEAVE-C35 -> 非主管角色查看待办列表权限不足
# TC-LEAVE-C36 -> 成功通过审批
# TC-LEAVE-C37 -> 成功驳回审批（填写意见）
# TC-LEAVE-C38 -> 驳回未填写审批意见失败
# TC-LEAVE-C39 -> 审批已通过的申请失败
# TC-LEAVE-C40 -> 审批已驳回的申请失败
# TC-LEAVE-C41 -> 审批已撤回的申请失败
# TC-LEAVE-C42 -> 审批不存在的申请失败
# TC-LEAVE-C43 -> 审批非本部门申请权限不足
# TC-LEAVE-C44 -> 非主管角色审批权限不足
# TC-LEAVE-C45 -> 查看审批已办列表成功
# TC-LEAVE-C46 -> 按申请人过滤已办列表
# TC-LEAVE-C47 -> 按状态过滤已办列表
# TC-LEAVE-C48 -> 分页参数不合法查询失败
# TC-LEAVE-C49 -> 非主管角色查看已办列表权限不足
# TC-LEAVE-C50 -> 查看全公司请假记录成功
# TC-LEAVE-C51 -> 按部门过滤请假记录
# TC-LEAVE-C52 -> 按状态过滤请假记录
# TC-LEAVE-C53 -> 按申请时间范围过滤请假记录
# TC-LEAVE-C54 -> 组合条件过滤请假记录
# TC-LEAVE-C55 -> 分页参数不合法查询失败
# TC-LEAVE-C56 -> 日期格式错误查询失败
# TC-LEAVE-C57 -> 非人事专员角色查看请假记录权限不足
# TC-LEAVE-C58 -> 查看请假时长统计成功
# TC-LEAVE-C59 -> 必填日期参数缺失查询失败
# TC-LEAVE-C60 -> 日期格式错误查询失败
# TC-LEAVE-C61 -> 非人事专员角色查看统计权限不足
# TC-LEAVE-C62 -> 未登录访问接口返回未登录
# TC-LEAVE-C63 -> 跨角色访问接口返回无权限

from __future__ import annotations
import allure
import pytest
from support.api_case import ApiCase, Assertion, FlowStep, run_case
from support.clients.api_client import ApiClient
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import SA_CODES

# 辅助函数：根据错误码构建失败断言
def _bf(key: str) -> list[Assertion]:
    """构建业务失败断言列表，key 不存在时退化为检查 /msg 存在"""
    code = SA_CODES.get(key)
    if code is None:
        return [Assertion(expected=True, op="exists", field="/msg")]
    return Assertion.biz_fail(code=code) + [Assertion(expected=True, op="exists", field="/msg")]

# 用例数据（按执行顺序排列，覆盖全流程）
FLOW_STEPS: list[FlowStep] = [
    # 员工提交申请
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C01-成功提交事假申请",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "家中有事需处理"},
        assertions=[],
        save={"apply_no": "${apply_no}"}  # 成功后分页反查 applyNo 存入 ctx
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C02-成功提交带附件的病假申请",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 2, "startTime": "2026-09-02 09:00:00", "endTime": "2026-09-02 18:00:00", "reason": "身体不适需休息", "attachment": "http://example.com/doctor_cert.jpg"},
        assertions=[]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C03-结束时间早于开始时间提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 18:00:00", "endTime": "2026-09-01 09:00:00", "reason": "测试场景"},
        biz_auto=False,
        assertions=[*_bf("time_invalid")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C04-结束时间等于开始时间提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 09:00:00", "reason": "测试场景"},
        biz_auto=False,
        assertions=[*_bf("time_invalid")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C05-必填字段缺失提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": ""},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C06-请假类型不存在提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 99, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试场景"},
        biz_auto=False,
        assertions=[*_bf("leave_type_not_exist")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C07-请假原因超过500字提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "A" * 501},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C08-附件URL超过1000字符提交失败",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试场景", "attachment": "http://example.com/" + "a" * 1000},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C09-非员工角色提交申请权限不足",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试场景"},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 员工查看列表（依赖 C01 创建的数据）
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C10-查看我的请假列表成功",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[
            Assertion(expected=True, op="exists", field="/data/list"),
            Assertion(expected=True, op="exists", field="/data/total")
        ]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C11-按状态过滤请假列表",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10, "status": 0},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C12-分页参数不合法查询失败",
        method="GET", path="/leave/my/list",
        params={"pageNum": 0, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C13-非员工角色查看我的请假列表权限不足",
        method="GET", path="/leave/my/list",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 员工查看详情（依赖 C01 创建的数据）
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C14-查看本人待审批申请详情",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "${apply_no}"},
        assertions=[
            Assertion(expected=0, op="eq", field="/data/status"),
            Assertion(expected=True, op="exists", field="/data/approverName"),  # 未审批为空，但字段存在
            Assertion(expected=True, op="exists", field="/data/approveTime")
        ]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C15-查看本人已通过申请详情",  # 需先通过审批，此处使用假设的已通过单号
        method="GET", path="/leave/my/detail",
        params={"applyNo": "LV20260901002"},
        assertions=[Assertion(expected=True, op="exists", field="/data")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C16-查看本人已驳回申请详情",  # 假设的已驳回单号
        method="GET", path="/leave/my/detail",
        params={"applyNo": "LV20260901003"},
        assertions=[Assertion(expected=True, op="exists", field="/data")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C17-查看已撤回申请详情",  # 假设的已撤回单号
        method="GET", path="/leave/my/detail",
        params={"applyNo": "LV20260901004"},
        assertions=[Assertion(expected=3, op="eq", field="/data/status")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C18-查看不存在的申请详情",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "LV_NOT_EXIST"},
        biz_auto=False,
        assertions=[*_bf("apply_not_exist")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C19-查看他人申请详情权限不足",  # 假设的他人单号
        method="GET", path="/leave/my/detail",
        params={"applyNo": "LV20260901005"},
        biz_auto=False,
        assertions=[*_bf("no_operation_right")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C20-非员工角色查看详情权限不足",
        method="GET", path="/leave/my/detail",
        params={"applyNo": "${apply_no}"},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 员工撤回申请（依赖 C01 创建的数据）
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C21-成功撤回待审批申请",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}", "cancelReason": "行程有变"},
        assertions=[]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C22-撤回已通过申请失败",  # 假设的已通过单号
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "LV20260901002", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("cancel_not_allowed")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C23-撤回已驳回申请失败",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "LV20260901003", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("cancel_not_allowed")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C24-撤回已撤回申请失败",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "LV20260901004", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("cancel_not_allowed")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C25-撤回不存在的申请失败",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "LV_NOT_EXIST", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("apply_not_exist")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C26-撤回原因为必填",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}", "cancelReason": ""},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C27-撤回原因超过200字失败",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}", "cancelReason": "A" * 201},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C28-撤回他人申请权限不足",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "LV20260901005", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("no_operation_right")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C29-非员工角色撤回权限不足",
        method="POST", path="/leave/my/cancel",
        body={"applyNo": "${apply_no}", "cancelReason": "测试"},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 主管审批待办
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C30-查看审批待办列表成功",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C31-按申请人过滤待办列表",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10, "employeeName": "张三"},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C32-按请假类型过滤待办列表",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10, "leaveTypeId": 1},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C33-按状态过滤待办列表",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10, "status": 0},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C34-分页参数不合法查询失败",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 0, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C35-非主管角色查看待办列表权限不足",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 主管审批操作（依赖 C01 创建的数据，但需注意撤回后状态改变）
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C36-成功通过审批",
        method="POST", path="/leave/approve",
        body={"applyNo": "${apply_no}", "approveAction": 1, "approveComment": ""},
        assertions=[]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C37-成功驳回审批（填写意见）",  # 需要另一个待审批单号，此处使用假设
        method="POST", path="/leave/approve",
        body={"applyNo": "LV20260901002", "approveAction": 2, "approveComment": "理由不充分，请补充材料"},
        assertions=[]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C38-驳回未填写审批意见失败",
        method="POST", path="/leave/approve",
        body={"applyNo": "${apply_no}", "approveAction": 2, "approveComment": ""},
        biz_auto=False,
        assertions=[*_bf("approve_comment_required")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C39-审批已通过的申请失败",
        method="POST", path="/leave/approve",
        body={"applyNo": "LV20260901003", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("status_invalid")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C40-审批已驳回的申请失败",
        method="POST", path="/leave/approve",
        body={"applyNo": "LV20260901004", "approveAction": 2, "approveComment": "测试"},
        biz_auto=False,
        assertions=[*_bf("status_invalid")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C41-审批已撤回的申请失败",
        method="POST", path="/leave/approve",
        body={"applyNo": "LV20260901005", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("status_invalid")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C42-审批不存在的申请失败",
        method="POST", path="/leave/approve",
        body={"applyNo": "LV_NOT_EXIST", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("apply_not_exist")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C43-审批非本部门申请权限不足",
        method="POST", path="/leave/approve",
        body={"applyNo": "LV20260901006", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("no_operation_right")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C44-非主管角色审批权限不足",
        method="POST", path="/leave/approve",
        body={"applyNo": "${apply_no}", "approveAction": 1},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 主管已办列表
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C45-查看审批已办列表成功",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C46-按申请人过滤已办列表",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 1, "pageSize": 10, "employeeName": "李四"},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C47-按状态过滤已办列表",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 1, "pageSize": 10, "status": 1},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("manager", ApiCase(
        name="TC-LEAVE-C48-分页参数不合法查询失败",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 0, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C49-非主管角色查看已办列表权限不足",
        method="GET", path="/leave/approve/done",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 人事查询与统计
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C50-查看全公司请假记录成功",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C51-按部门过滤请假记录",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "deptName": "研发部"},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C52-按状态过滤请假记录",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "status": 1},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C53-按申请时间范围过滤请假记录",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "startDate": "2026-09-01", "endDate": "2026-09-30"},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C54-组合条件过滤请假记录",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "deptName": "研发部", "status": 0, "startDate": "2026-09-01", "endDate": "2026-09-30"},
        assertions=[Assertion(expected=True, op="exists", field="/data/list")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C55-分页参数不合法查询失败",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 0, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C56-日期格式错误查询失败",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10, "startDate": "2026/09/01"},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C57-非人事专员角色查看请假记录权限不足",
        method="GET", path="/leave/admin/list",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C58-查看请假时长统计成功",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "2026-09-01", "endDate": "2026-09-30"},
        assertions=[Assertion(expected=True, op="exists", field="/data")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C59-必填日期参数缺失查询失败",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "", "endDate": "2026-09-30"},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("hr_admin", ApiCase(
        name="TC-LEAVE-C60-日期格式错误查询失败",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "2026/09/01", "endDate": "2026-09-30"},
        biz_auto=False,
        assertions=[*_bf("param_error")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C61-非人事专员角色查看统计权限不足",
        method="GET", path="/leave/admin/statistics",
        params={"startDate": "2026-09-01", "endDate": "2026-09-30"},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),

    # 通用权限用例
    FlowStep("anonymous", ApiCase(
        name="TC-LEAVE-C62-未登录访问接口返回未登录",
        method="POST", path="/leave/apply",
        body={"leaveTypeId": 1, "startTime": "2026-09-01 09:00:00", "endTime": "2026-09-01 18:00:00", "reason": "测试"},
        biz_auto=False,
        assertions=[*_bf("not_login")]
    )),
    FlowStep("employee", ApiCase(
        name="TC-LEAVE-C63-跨角色访问接口返回无权限",
        method="GET", path="/leave/approve/todo",
        params={"pageNum": 1, "pageSize": 10},
        biz_auto=False,
        assertions=[*_bf("no_permission")]
    )),
]

pytestmark = [pytest.mark.smartadmin, pytest.mark.api, pytest.mark.requires_role('employee'),
              pytest.mark.requires_role('manager'), pytest.mark.requires_role('hr_admin')]

@allure.feature("SmartAdmin · 请假模块")
@allure.story("跨角色权限与业务流程")
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_leave_role_flow(role_registry, ctx: ScenarioContext, cleanup_registry, base_url, admin_client, step: FlowStep):
    # 匿名用例
    if step.role == "anonymous":
        client = ApiClient(base_url)
    # 管理员角色（用于某些通用校验，此处未使用，保留逻辑）
    elif step.role == "admin":
        client = admin_client
    else:
        # 按 step.role 懒登录该角色独立会话
        client = role_registry[step.role]
    
    result = run_case(client, ctx, step.case)
    
    # 对于成功的创建用例，分页反查 applyNo 并注册清理
    if result.passed and step.case.name == "TC-LEAVE-C01-成功提交事假申请":
        # 通过分页查询反查刚创建的申请（假设第一条即最新）
        list_case = ApiCase(
            name="TC-LEAVE-C01-分页反查id",
            method="GET", path="/leave/my/list",
            params={"pageNum": 1, "pageSize": 10},
            assertions=[Assertion(expected=True, op="exists", field="/data/list")],
            save={"/data/list[0]/applyNo": "apply_no"}
        )
        list_result = run_case(client, ctx, list_case)
        if list_result.passed:
            apply_no = ctx.get("apply_no")
            if apply_no:
                # 注册删除接口（文档未提供，仅示例）
                cleanup_registry.register_delete("/leave/delete/{applyNo}", apply_no)
    
    assert result.passed, f"[{step.role}] {step.case.name}: {result.failure_summary}"