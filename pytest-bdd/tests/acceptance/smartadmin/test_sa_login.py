"""SmartAdmin L3 验收 Gherkin 场景运行入口（登录 feature）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/acceptance/smartadmin/test_sa_login.py`
"""
from __future__ import annotations

import allure
import pytest
from pytest_bdd import scenarios

# Explicitly import stepdefs module so pytest-bdd registers @given/@when/@then.
# Using Python 3.3+ implicit namespace packages + pythonpath=["."] (pyproject.toml).
from tests.acceptance.smartadmin.steps import sa_common_steps  # noqa: F401

pytestmark = [pytest.mark.smartadmin, pytest.mark.acceptance]

allure.dynamic.feature("SmartAdmin · 登录协议（L3 BDD 可评审）")
scenarios("features/login.feature")
