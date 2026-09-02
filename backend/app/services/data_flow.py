"""接口文档数据链分析（2026-09-02 新增，源头治理）。

核心思想：接口与接口之间的本质关联 = **数据流**（A 接口的响应字段 → B 接口的入参字段）。
接口文档已收纳全模块字段，做「字段语义一致性」比对即可**确定性**地批量产出候选数据链，
不依赖 AI 从正文猜：
  - 候选 depends_on（接口级）：B 的入参能在 A 的响应中找到同名/同义字段 → A 是 B 的前置接口；
  - 候选 data_source（字段级）：入参字段 ← 响应字段路径（如 /data/list[0]/enterpriseId）。

启发式（纯函数，零成本）产出候选；可选 LLM 精修（去噪/补漏/补路径）。
候选经「接口文档卡片」人工确认后存 artifact.meta.data_flow，
auto_gen 生成用例时作为步骤顺序的主序（渲染器 save/${var} Kahn 兜底仍保留）。

典型识别结果（SmartAdmin 企业管理）：
  IF-01 分页查询企业(response.data.list[].enterpriseId)
    → IF-05 添加员工(request.body.enterpriseId)   depends_on=[IF-01]  ← 员工绑定企业
    → IF-13 分页查询企业员工(request.body.enterpriseId) ...（同级并列子功能）
"""
from __future__ import annotations

import re
from typing import Any

# 通用分页/信封字段——不是业务数据链，匹配时忽略
_IGNORE_FIELDS = {
    "pageNum", "pageSize", "total", "pages", "emptyFlag",
    "offset", "limit", "page", "size", "ok", "code", "msg", "data",
}

_DATAFLOW_MODE_CODES = 1  # 留用：LLM 精修模式标识


def _field_names_of(iface: dict, side: str) -> dict[str, str]:
    """收集接口单侧（request/response）的全部字段名 → 第一个出现的字段路径。

    side="request"：body + path_params + query_params。
    side="response"：success_fields（含 list 元素在 description 里列出的子字段，路径按
    /data/list[0]/xxx 归一）；忽略 envelope 与分页通用字段。
    返回 {field_name: expr}，expr 是形如 /data/list[0]/enterpriseId 的可读路径。
    """
    out: dict[str, str] = {}

    def _add(name: str, expr: str) -> None:
        if name and name not in _IGNORE_FIELDS:
            out.setdefault(name, expr)

    if side == "request":
        req = iface.get("request") or {}
        # 只收 body + path_params：查询筛选参数（query_params）是用户的输入条件，不是"上一个接口给的数据"
        # —— 拿它们做来源匹配会误报成数据链（如两个查询接口因同名字段互相依赖成环）。
        for grp, prefix in (("path_params", "path"), ("body", "body")):
            for f in req.get(grp) or []:
                n = (f or {}).get("name")
                if n:
                    _add(n, f"{prefix}.{n}")
    else:
        resp = iface.get("response") or {}
        for f in resp.get("success_fields") or []:
            n = (f or {}).get("name") or ""
            if not n:
                continue
            if n == "list":
                # list 元素字段常列在 description（如 "元素含 enterpriseId、enterpriseName、…"）
                desc = (f.get("description") or "")
                for sub in re.split(r"[、，,;；]\s*", desc):
                    sub = sub.strip()
                    if "元素含" in sub:
                        sub = sub.split("元素含", 1)[-1].strip()
                    if sub and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", sub):
                        _add(sub, "/data/list[0]/" + sub)
                _add("list", "/data/list")
            else:
                _add(n, f"/data/{n}")
    return out


def _is_id_field(name: str) -> bool:
    """是否为「ID 引用类」字段：xxxId / xxxID / xxx_id / id，及**列表型**（xxxIdList / xxxIds）。

    数据链的本质是「上一接口产出的引用，本接口消费」—— 只有 ID 类字段符合
    （enterpriseId/employeeId/…）。新建/编辑接口里用户录入的业务属性
    （enterpriseName/type/contact/…）不是数据链，绝不参与来源匹配，否则全是噪声。
    列表型 ID 字段（employeeIdList=员工 ID 数组）去掉复数/列表后缀后 base 仍是 ID 字段才认，
    避免 customerList→customer 这类业务属性误入。
    """
    if name.endswith("Id") or name.endswith("ID") or name.endswith("_id") or name == "id":
        return True
    return _id_list_base(name) is not None


def _id_list_base(name: str) -> str | None:
    """列表型 ID 字段 → 元素 ID 字段名；非列表型返回 None。

    employeeIdList / employeeIdLists / employeeIds → employeeId；idList → id。
    仅当去掉复数/列表后缀后的 base 本身是 ID 字段时返回（customerList → None，防业务属性误入）。
    """
    if not name:
        return None
    low = name.lower()
    # 后缀按「长优先」匹配：复数列表 → 列表 → 单复数 s
    # （"ids" 不单独列出：employeeIds 去尾部 s 得 employeeId 可正确回退到 ID 判定，
    #   而 "ids" 前缀剥离会把 employeeIds 错误切成 employee + ids）
    for suffix in ("idlists", "idlist", "list", "s"):
        if low.endswith(suffix):
            base = name[: -len(suffix)] if suffix != "s" else name[:-1]
            if base.endswith("Id") or base.endswith("ID") or base.endswith("_id") or base.lower() == "id":
                return base
    return None


def _build_dataflow(doc: dict) -> list[dict]:
    """启发式：按「ID 类入参字段 ← ID 类响应字段」同名匹配，产出接口级候选数据链。

    规则（2026-09-02 v2，针对"新建接口业务属性被误判为数据来源"的返工修正）：
      1) 只匹配 ID 类字段（*Id/*_id）：只有它才可能是"上个接口给的数据"；
      2) 一个入参字段最多保留 1 个首选来源（/data/list[0]/… 分页反查优先，其次声明序靠前的接口），
         不搞"多个候选让用户猜"；
      3) 响应侧也只收集 ID 类字段参与匹配（天然排除 enterpriseName 这类属性噪声）；
      4) depends_on = 该接口全部 field_sources 的来源接口并集。
    """
    ifaces = doc.get("interfaces") or []
    index = {i.get("id"): i for i in ifaces if i.get("id")}
    resp_fields: dict[str, dict[str, str]] = {}          # iface_id -> {field: expr}
    req_fields: dict[str, dict[str, str]] = {}
    for i in ifaces:
        iid = i.get("id")
        if not iid:
            continue
        resp_fields[iid] = {
            n: e for n, e in _field_names_of(i, "response").items() if _is_id_field(n)}
        req_fields[iid] = {
            n: e for n, e in _field_names_of(i, "request").items() if _is_id_field(n)}

    results: list[dict] = []
    for iid, iface in index.items():
        sources: list[dict] = []
        src_iface_ids: list[str] = []
        for fname, fexpr in req_fields.get(iid, {}).items():
            # 匹配键：列表型 ID 字段（employeeIdList）归一为其**元素 ID**（employeeId），
            # 以便与响应侧 list[].employeeId 命中；单个 ID 字段（enterpriseId）用原名匹配。
            is_list_field = _id_list_base(fname) is not None
            match_keys = {fname} | ({_id_list_base(fname)} if is_list_field else set())
            # 候选：其它接口响应里同名的 ID 字段；反查来源（/data/list[0]/…）优先
            hits = [(sid, expr) for sid, fields in resp_fields.items()
                    for name, expr in fields.items()
                    if name in match_keys and sid != iid]
            if not hits:
                continue
            hits.sort(key=lambda h: (0 if "/data/list[0]/" in h[1] else 1,
                                     list(resp_fields).index(h[0])))
            sid, expr = hits[0]   # 只保留首选来源，避免多候选让用户猜
            sources.append({
                "field": fname, "expr": fexpr,
                "source_interface": sid,
                "source_path": expr,
                # 列表型入参（如 employeeIdList）：来源实为 list 元素的 ID（list[].employeeId），
                # 测试人员可反查后取一个/多个元素 id 填充数组
                "list": is_list_field,
                "confidence": "high",
            })
            if sid not in src_iface_ids:
                src_iface_ids.append(sid)
        results.append({
            "id": iid,
            "name": iface.get("name"),
            "path": iface.get("path"),
            "role": iface.get("role"),
            "depends_on": list(iface.get("depends_on") or src_iface_ids),
            "field_sources": sources,
        })
    return results


def analyze_dataflow(doc: dict, preset: list[dict] | None = None) -> dict:
    """分析接口文档 → 候选数据链（含推荐执行顺序）。

    preset：已确认（或之前分析）的结果，直接透传不覆盖——用于重复分析时保留人工修正。
    返回结构可直接存 artifact.meta.data_flow，也供前端「接口文档卡片」展示确认。
    """
    doc = dict(doc or {})
    if preset:
        # 已有人工确认版本：保留确认结果，仅补全缺失接口的候选
        existing = {r["id"]: r for r in preset}
        fresh = {}
        base = {r["id"]: r for r in _build_dataflow(doc)}
        fresh = {iid: existing.get(iid, base.get(iid)) for iid in base}
        flow = [fresh[iid] for iid in base if iid in fresh]
    else:
        flow = _build_dataflow(doc)

    # 推荐执行顺序：按 depends_on 做 Kahn 拓扑（被依赖多的先出），有环时环内按原始 interfaces 顺序
    # （候选依赖可能成环——启发式误报，不能因此崩掉；人工确认环节会消环）
    index = {r["id"]: r for r in flow}
    seq = [r["id"] for r in flow]                       # 原始顺序（环内兜底）
    deps = {r["id"]: [d for d in (r.get("depends_on") or []) if d in index] for r in flow}
    ready = [iid for iid, ds in deps.items() if not ds]
    order: list[str] = []
    while ready:
        ready.sort(key=seq.index)
        iid = ready.pop(0)
        order.append(iid)
        for other, ds in list(deps.items()):
            if iid in ds:
                ds.remove(iid)
                if not ds and other not in order:
                    ready.append(other)
    order.extend(iid for iid in seq if iid not in order)   # 残余环按原始顺序追加

    # 尾序微调：删除类接口放最后、导出/导入类放倒数第二。
    # key 用「动作档位 + 原始序号」先算好再排序——绝不引用被排序的 order 本身，
    # 规避 CPython list.sort 就地归并时 key 回调对原列表的读取歧义。
    def _kind(iid: str) -> int:
        path = (index[iid].get("path") or "").lower()
        if any(w in path for w in ("delete", "remove")):
            return 2
        if any(w in path for w in ("export", "import")):
            return 1
        return 0

    order = [iid for iid, _ in sorted(
        ((iid, (_kind(iid), seq.index(iid))) for iid in order),
        key=lambda t: t[1])]
    for r in flow:
        r["order_hint"] = order.index(r["id"]) + 1 if r["id"] in order else 0

    return {
        "analyzed_at": True,
        "interfaces": flow,
        "order_recommended": order,
        "notes": [
            "候选由接口文档字段同名比对生成（确定性启发式），请在「接口文档卡片」人工确认",
            "depends_on=前置接口；field_sources=入参字段的数据来源路径",
            "人工确认后的数据链会成为用例生成步骤顺序的主序",
        ],
    }