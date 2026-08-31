"""SmartAdmin L2 接口测试子目录专用 conftest（tests/api/smartadmin/）。

文件绝对路径: `computer://c:/AI-AGENT/test-ai-automated/pytest-bdd/tests/api/smartadmin/conftest.py`

通过 support.fixtures.smartadmin 模块里导出的 make_sa_fixture_functions()
拿到所有 SmartAdmin 专属的 session fixture，再按 pytest 约定暴露成本地 fixture
（`base_url` / `sa_client_registry` / `api_client` / `cleanup_registry` /
自动业务码探测的 autouse fixture）。这样 `tests/acceptance/smartadmin/conftest.py`
可以用同一套源码，两边不冲突、不重复维护。
"""
from __future__ import annotations

import pytest

from support.fixtures.context import ScenarioContext
from support.fixtures.smartadmin import (
    CleanupRegistry,  # noqa: F401 导出给外部 import
    close_role_clients,
    get_role_client,
    load_sa_roles,
    make_role_client_fixture,
    make_sa_fixture_functions,
    pytest_collection_modifyitems as _shared_skip_fn,
    SA_CODES,  # noqa: F401  导出给 test_enterprise_crud.py 访问（其实它也会从
               # support.fixtures.smartadmin 直读，这里 re-export 也没问题）
)


# ---- SA_PASSWORD 空时，smartadmin marker 的用例自动 SKIP ----
def pytest_collection_modifyitems(config, items):
    """先走共享逻辑（SA_PASSWORD 空就打 skip marker），如后续需要 L2 额外
    collection 级别处理，可在下方追加。"""
    _shared_skip_fn(config, items)


# ---- 拿到共享 fixture 函数，按约定导成 fixture 别名 ----
(_sa_base_url_fn, _sa_registry_fn, _sa_api_client_fn,
 _sa_cleanup_fn, _sa_probe_autouse_fn) = make_sa_fixture_functions()

base_url = pytest.fixture(scope="session")(_sa_base_url_fn)
sa_client_registry = pytest.fixture(scope="session")(_sa_registry_fn)
# 注意：fixture 名叫 api_client，它会在子目录层级覆盖 root conftest 的 api_client。
# 这样 L2 ApiCase 里的 api_client 引用始终拿到的是 SmartAdmin 的登录会话。
api_client = pytest.fixture(scope="session")(_sa_api_client_fn)
cleanup_registry = pytest.fixture(scope="session")(_sa_cleanup_fn)
_sa_probe = pytest.fixture(scope="session", autouse=True)(_sa_probe_autouse_fn)


@pytest.fixture(scope="module")
def ctx() -> ScenarioContext:
    """L2 接口参数化串行跑时，同一文件里的 创建→详情→修改→删除 要通过
    ${ent_id} 串值，因此需要 module 级 ScenarioContext（function 级会在每用例清空）。"""
    return ScenarioContext()


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
    """按 request.param 给的角色键取会话（供参数化/步骤按角色执行）。"""
    return get_role_client(request.param, base_url)


admin_client = pytest.fixture(scope="session")(make_role_client_fixture("admin"))
reporter_client = pytest.fixture(scope="session")(make_role_client_fixture("reporter"))
auditor_client = pytest.fixture(scope="session")(make_role_client_fixture("auditor"))
employee_client = pytest.fixture(scope="session")(make_role_client_fixture("employee"))
