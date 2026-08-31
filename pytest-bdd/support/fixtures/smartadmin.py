"""SmartAdmin 项目公共 fixture / helper / 业务码常量。

被 `tests/api/smartadmin/conftest.py` 与 `tests/acceptance/smartadmin/conftest.py`
共同复用，避免同一份登录逻辑与清理注册逻辑在两个子目录 conftest 重复维护。

业务码（dup_enterprise/delete_not_exist/unauth）首次 session 启动时由
`_sa_probe_business_codes` autouse fixture 故意触发 3 种失败场景探测得到，
写入本模块全局字典 `SA_CODES`，L2/L3 所有 case 共享同一套值。
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
import httpx as _httpx

from support.clients.api_client import ApiClient


# SmartAdmin 前端登录密码加密（SM4，见前端 /src/lib/encrypt.js）。
# 登录页把 password 用 SM4-ECB(key=hex(SM4_KEY)) 加密 → hex(16B) → Base64 后提交，
# 后端 LoginService 先 SM4 解密再做 BCrypt 比对，因此明文 123456 会被判为"密码错误"。
SM4_KEY: str = "1024lab__1024lab"


def encrypt_sa_password(raw: str) -> str:
    """按 SmartAdmin 前端加密协议处理登录密码（与浏览器 F12 可见的 password 完全一致）。

    步骤：SM4-ECB(明文, key=hex('1024lab__1024lab')) → 密文 hex(16 字节) → base64。
    依赖 gmssl（已加入 requirements/base.txt）。
    """
    from gmssl import sm4

    key_hex = SM4_KEY.encode("utf-8").hex()
    cipher = sm4.CryptSM4()
    cipher.set_key(bytes.fromhex(key_hex), sm4.SM4_ENCRYPT)
    enc_hex = cipher.crypt_ecb(raw.encode("utf-8")).hex()
    return base64.b64encode(enc_hex.encode("utf-8")).decode("utf-8")


# SmartAdmin 登录信封：未登录 / Sa-Token 过期的信封 code 列表（自动重登触发条件）。
# 初始值空列表，表示先不开启自动重登；探测到 unauth code 后会被 fixture 回填。
SA_UNAUTHORIZED_CODES: list[int] = []

# 多角色（RBAC）测试支持：角色键 → 账号配置（.env SA_ROLES_JSON）
#   admin(管理员)    : 全部权限（增删改查/报送）
#   reporter(填报员) : 新增/修改所负责的数据、只读其余
#   auditor(审核员)  : 只读 + 审核阶段，不可修改数据
#   employee(员工)   : 员工端，仅可见/查看对全员可见的公告
SA_ROLE_KEYS: tuple[str, ...] = ("admin", "reporter", "auditor", "employee")
SA_ROLE_CN: dict[str, str] = {"admin": "管理员", "reporter": "填报员", "auditor": "审核员", "employee": "员工"}

# 角色会话池：role_key -> ApiClient（懒登录缓存，每角色独立 token）
SA_ROLE_CLIENTS: dict[str, ApiClient] = {}

# 探测得到的 SmartAdmin 业务失败信封 code 常量：
#   unauth             : 未登录 / token 失效 → 也是自动重登开关
#   dup_enterprise     : 创建企业重名失败
#   delete_not_exist   : 删除不存在的企业 id
#   forbidden          : 越权 / 无权限（低权限角色调用高权限操作）
SA_CODES: dict[str, int | None] = {
    "unauth": None,
    "dup_enterprise": None,
    "delete_not_exist": None,
    "forbidden": None,
}


# ---------------------------------------------------------------------------
# 清理注册表（SmartAdmin 删除接口是 GET /xxx/delete/{id}）
# ---------------------------------------------------------------------------
@dataclass
class CleanupRegistry:
    client: ApiClient | None = None
    items: list[tuple[str, Any]] = field(default_factory=list)

    def register_delete(self, path_template: str, id_value: object) -> None:
        if id_value is None:
            return
        self.items.append((path_template, id_value))

    def flush(self) -> None:
        if self.client is None or not self.items:
            return
        print(f"[SmartAdmin 清理] 准备删除 {len(self.items)} 条注册资源…")
        for path_template, id_value in list(self.items):
            path = path_template.format(id=id_value)
            try:
                resp = self.client.request("GET", path, name="清理注册删除", desc=f"清理 {path}")
                try:
                    body = resp.json()
                except Exception:
                    body = None
                ok = isinstance(body, dict) and body.get("ok") is True and body.get("code") == 0
                if not ok:
                    print(f"  [清理跳过] {path} 响应不是 biz_ok: {resp.text[:200]}")
                else:
                    print(f"  [清理完成] {path}")
            except Exception as e:
                print(f"  [清理异常] {path}: {e}")
        self.items.clear()


# ---------------------------------------------------------------------------
# 登录实现（dev 明文 captcha 自动解；支持按账号/角色参数化登录）
# ---------------------------------------------------------------------------
def sa_login(client: ApiClient, login_name: str | None = None, password: str | None = None,
             device: int | None = None, role_label: str | None = None) -> None:
    """用 client 的会话走一次 SmartAdmin 登录。

    成功后 token 写入 client.token，后续请求自动带 Authorization: Bearer <token>。
    login_name/password 缺省回退 .env 的 SA_LOGIN_NAME / SA_PASSWORD（默认 admin）。
    role_label 仅用于日志展示（如「角色=reporter」）。
    失败抛出 RuntimeError（含响应内容，便于排查密码 / 验证码 / dev 环境问题）。
    """
    base = client.base_url.rstrip("/")

    if login_name is None:
        login_name = os.getenv("SA_LOGIN_NAME", "admin").strip()
    if password is None:
        password = os.getenv("SA_PASSWORD", "").strip()
    if device is None:
        try:
            device = int(os.getenv("SA_LOGIN_DEVICE", "1").strip())
        except Exception:
            device = 1

    if not password:
        pytest.skip("账号密码为空，跳过 SmartAdmin 登录")
    # 关键：后端比对的是前端的加密形态（SM4），明文会永远报"密码错误"。
    password = encrypt_sa_password(password)

    raw: _httpx.Client = client._client  # noqa: SLF001 直接走原始 httpx，避免往 history 里塞

    # ---- 1. GET captcha ----
    cap_resp = raw.get(f"{base}/login/getCaptcha")
    if cap_resp.status_code != 200:
        raise RuntimeError(f"SmartAdmin /login/getCaptcha HTTP={cap_resp.status_code}: {cap_resp.text[:300]}")
    try:
        cap = cap_resp.json()
    except Exception as e:
        raise RuntimeError(f"SmartAdmin captcha 返回不是 JSON: {cap_resp.text[:300]}") from e
    data = cap.get("data") if isinstance(cap, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"SmartAdmin captcha data 缺失: {cap_resp.text[:400]}")
    captcha_uuid = data.get("captchaUuid")
    captcha_text = data.get("captchaText")
    if not captcha_uuid or not captcha_text:
        raise RuntimeError(
            "SmartAdmin captcha 返回未含 captchaUuid/captchaText（非 dev 环境？）"
            f"原始: {cap_resp.text[:400]}"
        )

    # ---- 2. POST /login 5 字段 ----
    login_body = {
        "loginName": login_name,
        "password": password,
        "captchaCode": captcha_text,
        "captchaUuid": captcha_uuid,
        "loginDevice": device,
    }
    login_resp = raw.post(f"{base}/login", json=login_body)
    if login_resp.status_code != 200:
        raise RuntimeError(f"SmartAdmin /login HTTP={login_resp.status_code}: {login_resp.text[:400]}")
    try:
        env_body = login_resp.json()
    except Exception as e:
        raise RuntimeError(f"SmartAdmin /login 返回不是 JSON: {login_resp.text[:400]}") from e
    ok = env_body.get("ok") if isinstance(env_body, dict) else None
    code = env_body.get("code") if isinstance(env_body, dict) else None
    if ok is not True or code != 0:
        raise RuntimeError(
            "SmartAdmin 登录失败（信封 biz_fail）。请检查 SA_LOGIN_NAME / SA_PASSWORD。"
            f"响应: {login_resp.text[:600]}"
        )
    # 关键：这套环境以 Authorization: Bearer <data.token> 鉴权（不走 cookie）。
    token = env_body.get("data") or {}
    client.token = token.get("token") if isinstance(token, dict) else None
    who = f"角色={role_label} " if role_label else ""
    print(f"[SmartAdmin 登录成功] {who}用户={login_name} base_url={base} token={client.token}")


# ---------------------------------------------------------------------------
# 多角色：账号解析 + 角色会话池（每角色独立 ApiClient / 独立 token）
# ---------------------------------------------------------------------------
def load_sa_roles() -> dict[str, dict]:
    """解析 .env 的 SA_ROLES_JSON 为 {role_key: {loginName, password, device?}}。

    未配置 SA_ROLES_JSON 时，回退为仅 admin（用 SA_LOGIN_NAME / SA_PASSWORD）。
    只保留 SA_ROLE_KEYS 中合法的键。
    """
    raw = (os.getenv("SA_ROLES_JSON") or "").strip()
    if raw:
        import json as _json

        try:
            parsed = _json.loads(raw)
            roles = {k: v for k, v in parsed.items() if k in SA_ROLE_KEYS and isinstance(v, dict)}
            if roles:
                return roles
        except Exception as e:
            print(f"[SmartAdmin 角色配置] SA_ROLES_JSON 解析失败，回退单 admin：{e}")
    return {
        "admin": {
            "loginName": os.getenv("SA_LOGIN_NAME", "admin").strip(),
            "password": os.getenv("SA_PASSWORD", "").strip(),
        }
    }


def has_sa_role(role_key: str) -> bool:
    """判断某角色账号是否已配置（供 collection 期对用例打 SKIP）。"""
    roles = load_sa_roles()
    return role_key in roles and bool(roles[role_key].get("password"))


def get_role_client(role_key: str, base_url: str | None = None) -> ApiClient:
    """按角色取（懒登录并缓存的）ApiClient。每个角色 = 独立登录 → 独立 token。

    角色真实账号配置在 .env 的 SA_ROLES_JSON；get 时密码缺失会触发 pytest.skip。
    """
    global SA_ROLE_CLIENTS
    if role_key in SA_ROLE_CLIENTS:
        return SA_ROLE_CLIENTS[role_key]

    if base_url is None:
        base_url = os.getenv("SA_BASE_URL", "http://127.0.0.1:1024").rstrip("/")
    roles = load_sa_roles()
    account = roles.get(role_key)
    if not account:
        pytest.skip(f"未配置角色 {role_key}（{SA_ROLE_CN.get(role_key, '')}）的账号，请检查 .env SA_ROLES_JSON")

    client = ApiClient(base_url)
    client.set_relogin_hook(SA_UNAUTHORIZED_CODES, lambda: sa_login(
        client, account.get("loginName"), account.get("password"), role_label=role_key))
    sa_login(client, account.get("loginName"), account.get("password"),
             device=account.get("device"), role_label=role_key)
    SA_ROLE_CLIENTS[role_key] = client
    return client


def close_role_clients() -> None:
    """session 结束统一关闭角色会话池。"""
    for client in SA_ROLE_CLIENTS.values():
        try:
            client.close()
        except Exception:
            pass
    SA_ROLE_CLIENTS.clear()


def make_role_client_fixture(role_key: str):
    """生成一个「按角色取会话」的 fixture 工厂函数（未装饰，交给 conftest 装饰）。

    用法：`admin_client = pytest.fixture(scope="session")(make_role_client_fixture("admin"))`
    角色账号缺失（.env 未配置）时，get_role_client 内部触发 pytest.skip。
    """
    def _role_client(base_url):
        client = get_role_client(role_key, base_url)
        yield client
        close_role_clients()
    return _role_client


# ---------------------------------------------------------------------------
# Fixture 工厂（两个子目录 conftest 调用 make_sa_fixtures() 拿到 fixture 函数后本地导出）
# ---------------------------------------------------------------------------
def make_sa_fixture_functions():
    """返回 (base_url_fn, sa_client_registry_fn, api_client_fn, cleanup_registry_fn,
    probe_autouse_fn)，供两个 smartadmin 子目录 conftest 直接赋值到同名 fixture。"""

    # IMPORTANT：此处只返回【未装饰的原生 Python 函数】，外层 conftest 统一用
    # pytest.fixture(scope="...")(fn) 只装饰一次，避免 "fixture applied more than once"。

    def sa_base_url() -> str:
        return os.getenv("SA_BASE_URL", "http://127.0.0.1:1024").rstrip("/")

    def sa_client_registry() -> CleanupRegistry:
        return CleanupRegistry()

    def sa_api_client(base_url, sa_client_registry: CleanupRegistry):
        client = ApiClient(base_url)
        sa_client_registry.client = client

        def _relogin():
            sa_login(client)

        client.set_relogin_hook(SA_UNAUTHORIZED_CODES, _relogin)

        pwd = os.getenv("SA_PASSWORD", "").strip()
        if pwd:
            sa_login(client)
        yield client
        sa_client_registry.flush()
        client.close()

    def sa_cleanup(sa_client_registry: CleanupRegistry) -> CleanupRegistry:
        return sa_client_registry

    def sa_probe_business_codes(api_client, cleanup_registry: CleanupRegistry):
        pwd = os.getenv("SA_PASSWORD", "").strip()
        if not pwd:
            yield
            return

        base = api_client.base_url.rstrip("/")
        ts = time.strftime("%Y%m%d%H%M%S")
        probe_name = f"_PROBE_DUP_{ts}"
        create_body = {
            "enterpriseName": probe_name,
            "contact": "探测用",
            "contactPhone": "13800000000",
            "disabledFlag": False,
            "unifiedSocialCreditCode": f"91{abs(hash(probe_name)) % 10**16:016d}",
        }

        raw = api_client._client  # noqa: SLF001 内部使用
        auth = {"Authorization": f"Bearer {api_client.token}"} if api_client.token else {}
        try:
            r1 = raw.post(f"{base}/oa/enterprise/create", json=create_body, headers=auth)
            env1 = r1.json() if r1.status_code == 200 else None
            created_id = None
            if isinstance(env1, dict) and env1.get("ok") and env1.get("code") == 0:
                created_id = (env1.get("data") or {}).get("id")
                cleanup_registry.register_delete("/oa/enterprise/delete/{id}", created_id)

            r2 = raw.post(f"{base}/oa/enterprise/create", json=create_body, headers=auth)
            env2 = r2.json() if r2.status_code == 200 else None
            if isinstance(env2, dict) and env2.get("ok") is False:
                SA_CODES["dup_enterprise"] = int(env2.get("code"))
        except Exception as e:
            print(f"[SmartAdmin 错误码探测] dup_enterprise 跳过：{e}")

        try:
            r3 = raw.get(f"{base}/oa/enterprise/delete/999999999", headers=auth)
            env3 = r3.json() if r3.status_code == 200 else None
            if isinstance(env3, dict) and env3.get("ok") is False:
                SA_CODES["delete_not_exist"] = int(env3.get("code"))
        except Exception as e:
            print(f"[SmartAdmin 错误码探测] delete_not_exist 跳过：{e}")

        # forbidden（越权/无权限）：admin 先建一个真实企业，再让低权限角色（auditor）对其调更新。
        # create 返回 data=null，需用「分页反查」拿到 enterpriseId 再越权操作。
        try:
            low_role = "auditor" if has_sa_role("auditor") else ("reporter" if has_sa_role("reporter") else None)
            fb_name = f"_PROBE_FB_{ts}"
            fb_body = {
                "enterpriseName": fb_name, "contact": "探测",
                "contactPhone": "13800000000", "disabledFlag": False,
                "unifiedSocialCreditCode": f"91{abs(hash(fb_name)) % 10**16:016d}",
            }
            r_c = raw.post(f"{base}/oa/enterprise/create", json=fb_body, headers=auth)
            r_q = raw.post(f"{base}/oa/enterprise/page/query",
                           json={"pageNum": 1, "pageSize": 10, "keywords": fb_name}, headers=auth)
            lst = ((r_q.json().get("data") or {}).get("list") or [])
            fb_id = lst[0].get("enterpriseId") if lst else None
            if low_role and fb_id:
                cleanup_registry.register_delete("/oa/enterprise/delete/{id}", fb_id)
                low = get_role_client(low_role, base)
                raw_low = low._client
                auth_low = {"Authorization": f"Bearer {low.token}"} if low.token else {}
                upd_body = {
                    "enterpriseName": f"{fb_name}_越权尝试", "contact": "探测",
                    "contactPhone": "13800000000", "disabledFlag": False,
                    "unifiedSocialCreditCode": f"91{abs(hash(fb_name)) % 10**16:016d}",
                    "enterpriseId": fb_id,
                }
                r5 = raw_low.post(f"{base}/oa/enterprise/update", json=upd_body, headers=auth_low)
                env5 = r5.json() if r5.status_code == 200 else None
                if isinstance(env5, dict) and env5.get("ok") is False:
                    SA_CODES["forbidden"] = int(env5.get("code"))
                else:
                    SA_CODES["forbidden"] = None
                    print("[SmartAdmin 错误码探测] 提示：低权限角色更新企业未被后端拦截（接口层未做权限控制）")
        except Exception as e:
            print(f"[SmartAdmin 错误码探测] forbidden 跳过：{e}")

        try:
            anon = _httpx.Client(base_url=base, timeout=10.0)
            r4 = anon.get(f"{base}/oa/enterprise/get/1")
            anon.close()
            env4 = r4.json() if r4.status_code == 200 else None
            if isinstance(env4, dict) and env4.get("ok") is False:
                SA_CODES["unauth"] = int(env4.get("code"))
            else:
                SA_CODES["unauth"] = None
        except Exception as e:
            print(f"[SmartAdmin 错误码探测] unauth 跳过：{e}")

        if SA_CODES["unauth"] is not None:
            global SA_UNAUTHORIZED_CODES
            SA_UNAUTHORIZED_CODES = [SA_CODES["unauth"]]
            api_client.set_relogin_hook(
                SA_UNAUTHORIZED_CODES,
                lambda: sa_login(api_client),
            )

        print(
            "[SmartAdmin 错误码探测结果] "
            f"dup_enterprise={SA_CODES['dup_enterprise']}, "
            f"delete_not_exist={SA_CODES['delete_not_exist']}, "
            f"forbidden={SA_CODES['forbidden']}, "
            f"unauth={SA_CODES['unauth']}；"
            f"自动重登 = {SA_UNAUTHORIZED_CODES != []}"
        )
        yield

    return (
        sa_base_url, sa_client_registry, sa_api_client, sa_cleanup,
        sa_probe_business_codes,
    )


# ---------------------------------------------------------------------------
# 跳过逻辑：
#   1) SA_PASSWORD 空 → 所有 smartadmin marker 用例 SKIP；
#   2) 带 role:<...> marker 的用例，若 .env 未配置对应角色账号 → 该用例 SKIP。
# 子目录 conftest.py 可直接 `from support.fixtures.smartadmin import pytest_collection_modifyitems`
# 也可在各自 conftest 里声明同名函数（后者优先），两个 conftest 都声明不冲突。
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(config, items):
    pwd = os.getenv("SA_PASSWORD", "").strip()
    if not pwd:
        skip_marker = pytest.mark.skip(reason="未配置 SA_PASSWORD，请在项目根 .env 里填写 admin 真实密码后再跑")
        for item in items:
            if any(m.name == "smartadmin" for m in item.iter_markers()):
                item.add_marker(skip_marker)
        return
    for item in items:
        for m in item.iter_markers("requires_role"):
            role_key = m.args[0] if m.args else None
            if role_key and not has_sa_role(str(role_key)):
                item.add_marker(
                    pytest.mark.skip(reason=f"未配置角色 {role_key} 账号，请检查 .env 的 SA_ROLES_JSON")
                )
                break
