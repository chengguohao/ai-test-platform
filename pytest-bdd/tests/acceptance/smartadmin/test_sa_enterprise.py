"""SmartAdmin L3 验收 Gherkin 场景运行入口（企业 CRUD feature）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/acceptance/smartadmin/test_sa_enterprise.py`
"""
from __future__ import annotations

import allure
import pytest
from pytest_bdd import scenarios

# Explicitly import stepdefs module so pytest-bdd registers @given/@when/@then.
from tests.acceptance.smartadmin.steps import sa_common_steps  # noqa: F401

pytestmark = [pytest.mark.smartadmin, pytest.mark.acceptance]

allure.dynamic.feature("SmartAdmin · OA企业模块（L3 BDD 可评审场景大纲）")
scenarios("features/enterprise.feature")
