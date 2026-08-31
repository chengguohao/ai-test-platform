"""SmartAdmin L3 验收：RBAC 跨角色企业流程（role_access_flow.feature）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/acceptance/smartadmin/test_sa_role_access.py`

通过 pytest_plugins（acceptance/smartadmin/conftest.py 已注册）加载步骤定义；
模块级 requires_role marker 保证未配置 reporter/auditor 账号时自动 SKIP。
"""
from __future__ import annotations

import allure
import pytest
from pytest_bdd import scenarios

pytestmark = [
    pytest.mark.smartadmin,
    pytest.mark.acceptance,
    pytest.mark.requires_role("reporter"),
    pytest.mark.requires_role("auditor"),
]

allure.dynamic.feature("SmartAdmin · RBAC 跨角色流程")
scenarios("features/role_access_flow.feature")