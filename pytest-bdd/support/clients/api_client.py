import json as _json
import os
import time

import httpx


def _debug() -> bool:
    """控制台调试打印开关：默认开，设 API_DEBUG=0 关闭（大批量/回归用）。"""
    return os.getenv("API_DEBUG", "1") == "1"


METHOD_CN = {"GET": "查询", "POST": "创建", "PUT": "更新", "PATCH": "更新", "DELETE": "删除"}
STATUS_CN = {
    200: "成功",
    201: "创建成功",
    202: "已接受",
    204: "无内容",
    301: "永久重定向",
    302: "临时重定向",
    304: "未修改",
    400: "请求参数错误",
    401: "未登录/认证失败",
    403: "无访问权限",
    404: "资源不存在",
    405: "方法不允许",
    409: "资源冲突",
    415: "不支持的媒体类型",
    422: "参数校验失败",
    429: "请求过于频繁",
    500: "服务器内部错误",
    502: "网关错误",
    503: "服务不可用",
    504: "网关超时",
}


def _preview(val, limit=1200) -> str:
    if val is None:
        return "无"
    if isinstance(val, str):
        # 返回体/响应若是 JSON 字符串，先解析成对象，再以 ensure_ascii=False 输出中文
        try:
            val = _json.loads(val)
        except Exception:
            pass
    if isinstance(val, (dict, list)):
        try:
            val = _json.dumps(val, ensure_ascii=False)
        except TypeError:
            val = str(val)
    s = str(val)
    return s if len(s) <= limit else s[:limit] + "\n…(响应过长已截断)"


def _describe(method: str) -> str:
    """接口名只保留动作中文，具体含义由「请求说明」补充。"""
    return METHOD_CN.get(method.upper(), method)


def render_block(r: dict) -> str:
    """渲染单个接口块（不含断言）。"""
    line = "=" * 54
    out = [line, f"接口名称 : {r['name']}"]
    out += [
        f"请求方法 : {r['method']}",
        f"请求地址 : {r['url']}",
    ]
    if r["params"] not in (None, {}, []):
        out.append(f"查询参数 : {_preview(r['params'])}")
    out += [
        f"接口状态 : {STATUS_CN.get(r['status'], '未知')}  ({r['status']})   耗时 {r['elapsed']} 秒",
        f"body   : {_preview(r['json'])}",
        f"接口返回数据 ：{_preview(r["body"]) if r["body"] else "（无响应体）"}"
    ]
    return "\n".join(out)


def render_assertion(rec: dict) -> str | None:
    """渲染该接口对应的断言块；无断言时返回 None。

    优先渲染 record_assertions 写入的多条断言：第一行「断言数据」列出本次全部断言内容，
    第二行「断言结果」给出成功/失败；失败展开每条断言的预期值/实际值与失败原因。
    兼容旧的 expect（status-only）。
    """
    if rec.get("assertions"):
        block = rec["assertions"]
        items = block["items"]
        # 优先显示 run_case 组装的人类可读「断言数据」，缺失时回退 desc
        data = block.get("data") or "；".join(it.get("desc", "") for it in items) or "无"
        out = [f"断言数据 ：{data}", f"断言结果 ：{'成功' if block['ok'] else '失败'}"]
        if not block["ok"]:
            for it in items:
                if it.get("ok"):
                    continue
                out.append(f"\t断言预期值：{it['desc']}")
                out.append(f"\t实际返回值：{it['actual']}")
                out.append(f"\t断言失败原因：{it.get('reason')}")
        return "\n".join(out)
    exp = rec.get("expect")
    if not exp:
        return None
    ok = exp.get("ok", False)
    out = [f"断言数据 ：接口状态码 = {exp['expected']}", f"断言结果 ：{'成功' if ok else '失败'}"]
    out.append(f"\t断言预期值：接口状态码 = {exp['expected']}")
    out.append(f"\t实际返回值：接口状态码 = {exp['actual']}")
    if not ok:
        reason = exp.get("reason") or f"期望 {exp['expected']}, 实际 {exp['actual']}"
        out.append(f"\t断言失败原因：{reason}")
    return "\n".join(out)


class ApiClient:
    """封装 HTTP 调用，供 L2 接口测试与 L3 验收步骤复用。

    请求结果统一缓存到 history，不即时打印；用例结束时由 conftest
    钩子将「接口块 + 紧跟的断言块」一起输出。设 API_DEBUG=0 可关闭打印。

    SmartAdmin 扩展：
      - envelope(resp) -> dict | None 解析 SmartAdmin 的 {ok,code,msg,data,...} 统一信封；
      - page_query(path, page_num, page_size, keywords, **extra) 快捷方法（POST body 协议）；
      - set_relogin_hook(unauth_codes, hook) 支持 Sa-Token 过期时自动重新登录并原请求重发 1 次。
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=10.0)
        self.history: list[dict] = []
        # SmartAdmin 鉴权 token：登录响应 data.token，后续请求带 Authorization: Bearer <token>
        # （这套环境不走 cookie；前端 axios 也是从 localStorage 取 token 放 header）
        self.token: str | None = None
        # SmartAdmin 自动重登（会话过期时）
        self._unauth_codes: list[int] = []
        self._relogin_hook = None
        self._in_relogin = False

    # ------------------------------------------------------------------
    # SmartAdmin 扩展：信封解析 + 分页查询 + 重登钩子
    # ------------------------------------------------------------------
    @staticmethod
    def envelope(resp: httpx.Response) -> dict | None:
        """尝试解析 SmartAdmin 统一信封。非信封（非 JSON / 不含 ok 键）返回 None。

        守卫语义：只要返回 None，上层就认定"不是 SmartAdmin 协议"，
        不会自动注入 biz_ok / biz_fail 断言，确保非信封响应接口的 HTTP 状态码断言不被破坏。
        """
        try:
            body = resp.json()
        except Exception:
            return None
        if not isinstance(body, dict) or "ok" not in body:
            return None
        return body

    def page_query(
        self,
        path: str,
        page_num: int = 1,
        page_size: int = 10,
        keywords: str | None = None,
        name: str | None = None,
        **extra,
    ):
        """SmartAdmin 通用 POST body 分页查询快捷方法。

        body = {pageNum, pageSize, keywords?} + **extra；
        其余 kwargs（label/desc/...）透传 request()。
        """
        body = {"pageNum": page_num, "pageSize": page_size}
        if keywords is not None:
            body["keywords"] = keywords
        body.update(extra)
        return self.request("POST", path, json=body, name=name)

    def set_relogin_hook(self, unauth_codes: list[int], hook) -> None:
        """注册 Sa-Token 过期后自动重登 1 次的钩子。

        Args:
            unauth_codes: SmartAdmin 信封 code 值列表（例如未登录 / 会话过期）。
                传空列表即关闭自动重登。
            hook: callable()，无参数；实现里应拿 self._client 再重新走一遍
                登录协议（captcha + /login），成功后 cookie jar 已更新。
        """
        self._unauth_codes = list(unauth_codes or [])
        self._relogin_hook = hook

    # ------------------------------------------------------------------
    # 核心 request（带 1 次重登）
    # ------------------------------------------------------------------
    def request(self, method, path, params=None, json=None, label=None, desc=None, name=None, **kwargs):
        start = time.perf_counter()
        # 会话 token 注入：登录后所有请求自动带 Authorization: Bearer <token>（SmartAdmin 协议）
        headers = dict(kwargs.pop("headers", None) or {})
        if self.token and not any(k.lower() == "authorization" for k in headers):
            headers["Authorization"] = f"Bearer {self.token}"
        resp = self._client.request(method, path, params=params, json=json, headers=headers, **kwargs)
        # 信封守卫：如果命中未登录业务码，走自动重登 1 次（防止重入递归爆炸）
        env = ApiClient.envelope(resp)
        if (
            env is not None
            and self._relogin_hook is not None
            and env.get("code") in self._unauth_codes
            and not self._in_relogin
        ):
            print("[SA-Token 自动重登 1 次] code={code} path={path}".format(code=env.get("code"), path=path))
            self._in_relogin = True
            try:
                self._relogin_hook()
            finally:
                self._in_relogin = False
            # 重登后把原请求原样再发一次（务必用新 token 重建 Authorization 头，
            # 否则重发仍是未登录的裸请求，会再次命中 30007）
            start2 = time.perf_counter()
            retry_headers = dict(headers)
            if self.token:
                retry_headers["Authorization"] = f"Bearer {self.token}"
            resp = self._client.request(method, path, params=params, json=json,
                                        headers=retry_headers, **kwargs)
            elapsed = round(time.perf_counter() - start2, 3)
        else:
            elapsed = round(time.perf_counter() - start, 3)
        rec = {
            "method": method.upper(),
            "path": path,
            "name": name if name else _describe(method),
            "desc": desc,
            "url": self.base_url.rstrip("/") + path,
            "params": params,
            "json": json,
            "status": resp.status_code,
            "elapsed": elapsed,
            "body": resp.text,
            "expect": None,
        }
        self.history.append(rec)
        return resp

    def post(self, path, json=None, **kwargs):
        return self.request("POST", path, json=json, **kwargs)

    def get(self, path, params=None, **kwargs):
        return self.request("GET", path, params=params, **kwargs)

    def mark_expect(self, expected, actual: int, body: str = "", reason: str | None = None) -> None:
        """把一次断言结果挂到最近的接口记录上，供「接口块+断言块」一起渲染。

        expected 可为单个状态码，也可为状态码列表（表示实际需命中其一）。
        """
        if not self.history:
            return
        code = expected if isinstance(expected, (list, tuple)) else [expected]
        ok = actual in code
        display = "、".join(str(c) for c in code)
        self.history[-1]["expect"] = {
            "expected": display,
            "actual": actual,
            "body": body,
            "ok": ok,
            "reason": reason if reason is not None else (None if ok else f"期望状态码 {display} 之一，实际 {actual}"),
        }

    def record_assertions(self, case_name: str, items: list[dict], data: str = "") -> None:
        """把一组断言结果挂到最近的接口记录上，供「接口块+断言块」一起渲染。

        items 元素形如 {desc, expected, actual, ok, reason}；
        data 为人类可读的「断言数据」（如 {"code": 0, "msg": "操作成功"}），空则回退渲染 desc。
        """
        if not self.history:
            return
        self.history[-1]["assertions"] = {
            "case": case_name,
            "items": items,
            "data": data,
            "ok": all(i.get("ok") for i in items),
        }

    def close(self):
        self._client.close()