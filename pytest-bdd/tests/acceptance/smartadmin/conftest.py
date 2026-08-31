"""SmartAdmin L3 验收测试子目录专用 conftest（tests/acceptance/smartadmin/）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/acceptance/smartadmin/conftest.py`

与 L2 共用 support.fixtures.smartadmin 的 fixture 实现，保证登录 / 清理 /
业务码探测是同一套源码；然后额外声明 function 级 `ctx`（每 BDD 场景独立上下文，
预埋 `ts_token` 时间戳给 Gherkin Examples `${ts_token}` 唯一化占位）。
"""
from __future__ import annotations

import time

import pytest
from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import (
    close_role_clients,
    get_role_client,
    load_sa_roles,
    make_role_client_fixture,
    make_sa_fixture_functions,
    pytest_collection_modifyitems as _shared_skip_fn,
)

# 关键：pytest-bdd 的步骤装饰器会把步骤注册为「fixture」（pytestbdd_stepdef_*），
# 但普通被 import 的 steps 模块不会被 pytest 的 fixture 收集器注册进 manager，
# 只有作为「插件」加载才会注册（否则运行时报 StepDefinitionNotFoundError）。
# 必须用完整 dotted path（pythonpath=["."] 已配置），相对路径 "steps.xxx" 会 ImportError。
pytest_plugins = ["tests.acceptance.smartadmin.steps.sa_common_steps"]


# ---- SA_PASSWORD 空时，smartadmin marker 的用例自动 SKIP ----
def pytest_collection_modifyitems(config, items):
    _shared_skip_fn(config, items)



# ---- 与 L2 共用的 SmartAdmin session fixture（别名 api_client / cleanup_registry 等）----
(_sa_base_url_fn, _sa_registry_fn, _sa_api_client_fn,
 _sa_cleanup_fn, _sa_probe_autouse_fn) = make_sa_fixture_functions()

base_url = pytest.fixture(scope="session")(_sa_base_url_fn)
sa_client_registry = pytest.fixture(scope="session")(_sa_registry_fn)
api_client = pytest.fixture(scope="session")(_sa_api_client_fn)
cleanup_registry = pytest.fixture(scope="session")(_sa_cleanup_fn)
_sa_probe = pytest.fixture(scope="session", autouse=True)(_sa_probe_autouse_fn)


@pytest.fixture
def ctx() -> ScenarioContext:
    """L3 验收场景：每个场景一个 ScenarioContext。"""
    c = ScenarioContext()
    c.set("ts_token", time.strftime("%m%d%H%M%S"))
    return c


# =========================================================================
# 多角色（RBAC）fixture：每角色独立 ApiClient / 独立 token，懒登录
# =========================================================================
@pytest.fixture(scope="session")
def role_accounts() -> dict:
    """解析后的角色账号表（{role_key: {loginName, password}}）。"""
    return load_sa_roles()


@pytest.fixture(scope="session")
def role_registry(base_url):
    """角色会话注册表：reg["reporter"] 按需得到该角色（懒登录）的 ApiClient。"""
    registry = type("RoleRegistry", (), {"__getitem__": staticmethod(lambda k: get_role_client(k, base_url))})()
    yield registry
    close_role_clients()


@pytest.fixture
def role_client(request, base_url):
    """按 request.param 给的角色键取会话（供步骤按角色执行）。"""
    return get_role_client(request.param, base_url)


admin_client = pytest.fixture(scope="session")(make_role_client_fixture("admin"))
reporter_client = pytest.fixture(scope="session")(make_role_client_fixture("reporter"))
auditor_client = pytest.fixture(scope="session")(make_role_client_fixture("auditor"))
