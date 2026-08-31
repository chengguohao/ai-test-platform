import os
import re

import pytest

from support.clients import api_client as api_mod
from support.fixtures.smartadmin import SA_ROLE_CLIENTS


def _debug() -> bool:
    return os.getenv("API_DEBUG", "1") == "1"


def _pretty(name: str) -> str:
    """把 pytest 对中文参数化测试名的 \\u 转义还原成可读中文。"""
    if "\\u" in name:
        try:
            return name.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except Exception:
            return name
    return name


def _active_api_clients(item):
    """收集本次用例可能发起请求的客户端：api_client（默认 admin 会话）+
    多角色用例的角色会话池（role_registry 懒登录产生的各角色 ApiClient）。

    BDD 用例的 api_client 由步骤按需注入，不在 item.funcargs / fixturenames 中，
    需直接从 fixture 管理器按名取值（session 级，已缓存时直接复用）。
    SmartAdmin 场景下，该名字解析到的是 tests/api|acceptance/smartadmin 子目录
    conftest 里定义的登录会话版 api_client。
    """
    clients: list = []
    try:
        clients.append(item._request.getfixturevalue("api_client"))
    except BaseException:
        pass
    for cli in SA_ROLE_CLIENTS.values():
        clients.append(cli)
    return clients


@pytest.hookimpl(hookwrapper=True)
def pytest_collection_modifyitems(session, config, items):
    yield
    for item in items:
        item._nodeid = _unescape_node_id(item._nodeid)


def _unescape_node_id(s: str) -> str:
    """把 pytest 对参数化 id 转义的字符还原，便于收集清单与 PASSED 行可读。

    pytest 转义规则：中文等 BMP 字符转成 \\uXXXX（四位），latin-1 单字节字符
    （如中圆点 ·U+00B7）转成 \\xXX（两位），两者都需还原，否则左侧会出现 \\xb7。
    """
    return re.sub(
        r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))",
        lambda m: chr(int(m.group(1) or m.group(2), 16)),
        s,
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    yield
    clients = _active_api_clients(item)
    if clients:
        # 按客户端分别记录 setup 时已有历史长度，作为本用例请求数的基准
        item._api_base = {id(c): len(c.history) for c in clients}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" or not _debug():
        return
    clients = _active_api_clients(item)
    if not clients:
        return
    # 聚合所有活跃客户端在本用例内新增的请求记录（按客户端顺序拼接）
    base = getattr(item, "_api_base", {})
    recent = []
    for c in clients:
        start = base.get(id(c), 0)
        recent.extend(c.history[start:])
    if recent:
        blocks = []
        for rec in recent:
            blocks.append(api_mod.render_block(rec))
            block = api_mod.render_assertion(rec)
            if block:
                blocks.append(block)
        print("\n" + "\n".join(blocks))
    flag = "成功" if rep.passed else "失败"
    count = len(recent)
    tail = f"共 {count} 次接口调用" if count else "该用例未发起接口调用"
    print(f"[用例结论] {_pretty(item.name)} → {flag}  （{tail}）")


@pytest.hookimpl(hookwrapper=True)
def pytest_bdd_before_step(request, feature, scenario, step, step_func):
    """BDD 场景执行时，把每一步的 Gherkin 关键字+文本打印到运行日志/Test Output，
    便于按「单个场景节点」查看每一步执行情况（左侧面板粒度=场景，步骤细节看这里）。"""
    print(f"  [BDD 步骤] {step.keyword} {step.name}")
    yield