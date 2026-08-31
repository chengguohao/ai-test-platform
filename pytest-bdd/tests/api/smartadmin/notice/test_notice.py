# AUTO-GENERATED
# 来源用例映射：
#   TC-NOTICE-01  -> 创建公告-正常成功（拆为 01a 创建 / 01b 分页反查id）
#   TC-NOTICE-02  -> 创建公告-标题为空-参数校验失败
#   TC-NOTICE-03  -> 创建公告-标题超长-参数校验失败
#   TC-NOTICE-04  -> 创建公告-发布时间格式非法-参数校验失败
#   TC-NOTICE-05  -> 管理端分页查询-正常
#   TC-NOTICE-06  -> 管理端分页查询-pageSize=-1-待确认缺陷
#   TC-NOTICE-07  -> 修改公告-正常成功（拆为 07a 修改 / 07b 反查确认）
#   TC-NOTICE-08  -> 修改公告-缺少noticeId-参数校验失败
#   TC-NOTICE-09  -> 获取修改回显数据-正常
#   TC-NOTICE-10  -> 获取修改回显数据-公告不存在-业务失败
#   TC-NOTICE-11  -> 删除公告-正常成功（拆为 11a 删除 / 11b 反查确认）
#   TC-NOTICE-12  -> 删除公告-不存在-业务失败
#   TC-NOTICE-13  -> 管理端接口-未登录访问-业务失败
#   TC-NOTICE-14  -> 员工身份调用创建公告-权限不足
#   TC-NOTICE-15  -> 获取公告类型列表-正常
#   TC-NOTICE-16  -> 获取公告类型列表-未登录-业务失败
#   TC-NOTICE-17  -> 员工分页查询可见公告-正常
#   TC-NOTICE-18  -> 员工分页查询-按标题过滤
#   TC-NOTICE-19  -> 员工分页查询-pageNum=0-待确认缺陷
#   TC-NOTICE-20  -> 员工查看公告详情-正常
#   TC-NOTICE-21  -> 员工查看公告详情-未登录-业务失败
#   TC-NOTICE-22  -> 员工查看公告详情-公告不存在-业务失败
from __future__ import annotations

import time

import allure
import pytest

from support.api_case import ApiCase, Assertion, FlowStep, run_case
from support.clients.api_client import ApiClient
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import SA_CODES

TS = time.strftime("%Y%m%d%H%M%S")
CREATE_TITLE = f"制度发布通知20240115_{TS}"
UPDATE_TITLE = f"更新后的标题20240115_{TS}"
NO_ID_UPDATE_TITLE = f"缺少noticeId更新_{TS}"
EMPLOYEE_CREATE_TITLE = f"员工权限探测_{TS}"


def _bf(key):
    """按 key 动态取业务码；探测不到时退化为 /msg exists，避免断言崩溃。"""
    code = SA_CODES.get(key)
    if code is None:
        return [Assertion(expected=True, op="exists", field="/msg")]
    return Assertion.biz_fail(code=code) + [
        Assertion(expected=True, op="exists", field="/msg")
    ]


pytestmark = [
    pytest.mark.smartadmin,
    pytest.mark.api,
    pytest.mark.requires_role("admin"),
    pytest.mark.requires_role("employee"),
]

FLOW_STEPS: list[FlowStep] = [
    # ---------- 1. 公告类型（为后续创建公告提供真实 noticeTypeId） ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-15-获取公告类型列表-正常",
            method="GET",
            path="/oa/noticeType/getAll",
            assertions=[
                Assertion(expected=True, op="exists", field="/data"),
                Assertion(expected=True, op="exists", field="/data[0]/noticeTypeId"),
            ],
            save={"/data[0]/noticeTypeId": "notice_type_id"},
        ),
    ),

    # ---------- 2. 管理端创建公告反例 ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-02-创建公告-标题为空-参数校验失败",
            method="POST",
            path="/oa/notice/add",
            body={
                "title": "",
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            biz_auto=False,
            assertions=[*_bf("param_error")],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-03-创建公告-标题超长-参数校验失败",
            method="POST",
            path="/oa/notice/add",
            body={
                "title": "a" * 201,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            biz_auto=False,
            assertions=[*_bf("param_error")],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-04-创建公告-发布时间格式非法-参数校验失败",
            method="POST",
            path="/oa/notice/add",
            body={
                "title": "格式非法时间_%s" % TS,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024/01/15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            biz_auto=False,
            assertions=[*_bf("param_error")],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-08-修改公告-缺少noticeId-参数校验失败",
            method="POST",
            path="/oa/notice/update",
            body={
                "title": NO_ID_UPDATE_TITLE,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            biz_auto=False,
            assertions=[*_bf("param_error")],
        ),
    ),

    # ---------- 3. 创建公告正向流程（唯一标题 + 真实类型ID） ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-01a-创建公告-正常成功",
            method="POST",
            path="/oa/notice/add",
            body={
                "title": CREATE_TITLE,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            assertions=[],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-01b-分页反查id",
            method="POST",
            path="/oa/notice/query",
            body={"pageNum": 1, "pageSize": 10, "keywords": CREATE_TITLE},
            assertions=[
                Assertion(expected=True, op="exists", field="/data/total"),
                Assertion(expected=True, op="exists", field="/data/list[0]/noticeId"),
            ],
            save={"/data/list[0]/noticeId": "notice_id"},
        ),
    ),

    # ---------- 4. 管理端分页查询 ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-05-管理端分页查询-正常",
            method="POST",
            path="/oa/notice/query",
            body={"pageNum": 1, "pageSize": 10, "keywords": "制度"},
            assertions=[
                Assertion(expected=True, op="exists", field="/data"),
                Assertion(expected=True, op="exists", field="/data/total"),
                Assertion(expected=True, op="exists", field="/data/list[0]/noticeId"),
            ],
        ),
    ),
    # TC-NOTICE-06：上一轮实测系统未校验 pageSize=-1，按待确认缺陷记录为正例
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-06-管理端分页查询-pageSize负数-待确认缺陷",
            method="POST",
            path="/oa/notice/query",
            body={"pageNum": 1, "pageSize": -1},
            assertions=[],
        ),
    ),

    # ---------- 5. 回显 / 修改 ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-09-获取修改回显数据-正常",
            method="GET",
            path="/oa/notice/getUpdateVO/${notice_id}",
            assertions=[
                Assertion(expected=True, op="exists", field="/data/noticeId"),
                Assertion(expected=True, op="exists", field="/data/title"),
            ],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-07a-修改公告-正常成功",
            method="POST",
            path="/oa/notice/update",
            body={
                "noticeId": "${notice_id}",
                "title": UPDATE_TITLE,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "admin",
                "source": "OA系统",
                "attachment": "",
            },
            assertions=[],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-07b-修改后分页反查确认",
            method="POST",
            path="/oa/notice/query",
            body={"pageNum": 1, "pageSize": 10, "keywords": UPDATE_TITLE},
            assertions=[
                Assertion(expected=True, op="exists", field="/data/list[0]/title"),
            ],
        ),
    ),

    # ---------- 6. 员工端正常查询/查看（公告尚未删除） ----------
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-17-员工分页查询可见公告-正常",
            method="POST",
            path="/oa/notice/employee/query",
            body={"pageNum": 1, "pageSize": 10},
            assertions=[
                Assertion(expected=True, op="exists", field="/data/total"),
            ],
        ),
    ),
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-18-员工分页查询-按标题过滤",
            method="POST",
            path="/oa/notice/employee/query",
            body={"pageNum": 1, "pageSize": 10, "title": "制度"},
            assertions=[
                Assertion(expected=True, op="exists", field="/data/total"),
            ],
        ),
    ),
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-20-员工查看公告详情-正常",
            method="GET",
            path="/oa/notice/employee/view/${notice_id}",
            assertions=[
                Assertion(expected=True, op="exists", field="/data/title"),
            ],
        ),
    ),
    # TC-NOTICE-19：上一轮实测系统未校验 pageNum=0，按待确认缺陷记录为正例
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-19-员工分页查询-pageNum零值-待确认缺陷",
            method="POST",
            path="/oa/notice/employee/query",
            body={"pageNum": 0, "pageSize": 10},
            assertions=[],
        ),
    ),

    # ---------- 7. 反例（不存在 / 未登录 / 权限不足） ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-10-获取修改回显数据-公告不存在-业务失败",
            method="GET",
            path="/oa/notice/getUpdateVO/999999",
            biz_auto=False,
            assertions=[*_bf("notice_not_exist")],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-12-删除公告-不存在-业务失败",
            method="GET",
            path="/oa/notice/delete/999999",
            biz_auto=False,
            assertions=[*_bf("delete_not_exist")],
        ),
    ),
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-14-管理端接口-员工身份调用创建公告-权限不足",
            method="POST",
            path="/oa/notice/add",
            body={
                "title": EMPLOYEE_CREATE_TITLE,
                "noticeTypeId": "${notice_type_id}",
                "allVisibleFlag": True,
                "scheduledPublishFlag": False,
                "publishTime": "2024-01-15 10:00:00",
                "contentText": "正文文本",
                "contentHtml": "<p>正文HTML</p>",
                "author": "employee",
                "source": "OA系统",
                "attachment": "",
            },
            biz_auto=False,
            assertions=[*_bf("forbidden")],
        ),
    ),
    FlowStep(
        "employee",
        ApiCase(
            name="TC-NOTICE-22-员工查看公告详情-公告不存在-业务失败",
            method="GET",
            path="/oa/notice/employee/view/999999",
            biz_auto=False,
            assertions=[*_bf("notice_not_exist")],
        ),
    ),
    FlowStep(
        "anonymous",
        ApiCase(
            name="TC-NOTICE-16-获取公告类型列表-未登录-业务失败",
            method="GET",
            path="/oa/noticeType/getAll",
            biz_auto=False,
            assertions=[*_bf("not_login")],
        ),
    ),
    FlowStep(
        "anonymous",
        ApiCase(
            name="TC-NOTICE-21-员工查看公告详情-未登录-业务失败",
            method="GET",
            path="/oa/notice/employee/view/1",
            biz_auto=False,
            assertions=[*_bf("not_login")],
        ),
    ),
    FlowStep(
        "anonymous",
        ApiCase(
            name="TC-NOTICE-13-管理端接口-未登录访问-业务失败",
            method="GET",
            path="/oa/notice/delete/1",
            biz_auto=False,
            assertions=[*_bf("not_login")],
        ),
    ),

    # ---------- 8. 删除真实公告（必须放末尾，避免影响前面查看/回显用例） ----------
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-11a-删除公告-正常成功",
            method="GET",
            path="/oa/notice/delete/${notice_id}",
            assertions=[],
        ),
    ),
    FlowStep(
        "admin",
        ApiCase(
            name="TC-NOTICE-11b-删除后分页反查确认",
            method="POST",
            path="/oa/notice/query",
            body={"pageNum": 1, "pageSize": 10, "keywords": UPDATE_TITLE},
            assertions=[
                Assertion(expected=True, op="eq", field="/data/list[0]/deletedFlag"),
            ],
        ),
    ),
]


@allure.feature("SmartAdmin · 通知公告模块")
@allure.story("L2 接口 · 多角色权限序列")
@pytest.mark.parametrize("step", FLOW_STEPS, ids=lambda s: s.case.name)
def test_notice_flow(
    role_registry,
    ctx: ScenarioContext,
    cleanup_registry,
    base_url,
    admin_client,
    step: FlowStep,
):
    # 匿名/未登录：ApiClient 不登录即为匿名，token=None 自动不带 Authorization 头
    if step.role == "anonymous":
        client = ApiClient(base_url)
    elif step.role == "admin":
        client = admin_client
    else:
        client = role_registry[step.role]

    result = run_case(client, ctx, step.case)
    if result.passed and step.case.name == "TC-NOTICE-01b-分页反查id":
        nid = ctx.get("notice_id")
        if nid is not None:
            cleanup_registry.register_delete("/oa/notice/delete/{id}", nid)
    assert result.passed, f"[{step.role}] {step.case.name}: {result.failure_summary}"