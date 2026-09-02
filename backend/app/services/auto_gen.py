"""自动化用例增量生成：approved 用例 + 接口文档 → pytest ApiCase 脚本。

遵循 pytest-bdd 规范（parametrize 展开/信封守卫/save-清理/TC 映射）；
增量保护：不覆盖含「手写维护」标记的文件；同模块二次迭代仅追加新 TC（由 skill 依据已有文件去重）。
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import task_progress
from app.services.ai_llm import model_label
from app.services.auto_gen_render import render_code
from app.services.skills import auto_gen as skill_auto
from app.services.skill_engine import run_json_skill
from app.services.system_profile import SystemProfile, collect_system_profile, resolve_target_file


def _patch_roles(code: str, available: list[str]) -> str:
    """确定性兜底：模块级 pytestmark 里 requires_role('X') 的 X 若未配置角色账号，
    则从 pytestmark 移除该项。

    原因：requires_role 是 collection 期校验——只要有一个未配置角色，整模块全部用例
    被 skip（63 条全跳过）。移除后：未配置角色的用例运行时 role_registry[X] 会单独
    pytest.skip（smartadmin fixture 已有该逻辑），已配置角色用例正常执行，不再全模块跳过。
    """
    if not available:
        return code
    for role in re.findall(r"requires_role\('([a-z_]+)'\)", code):
        if role in available:
            continue
        # 删除 pytestmark 列表里整行 requires_role 项（含行尾逗号），不留空行/尾逗号问题
        code = re.sub(rf"^\s*pytest\.mark\.requires_role\('{role}'\),?\s*\n?", "", code, flags=re.M)
    return code


# 断言引擎 support/api_case.py 支持的 op 白名单（白名单外一律非法，运行时会 raise ValueError）
_VALID_OPS = {"eq", "ne", "exists", "contains", "in", "gt", "gte", "lt", "lte", "regex"}


def _read_codes_keys(project_dir: Path, codes_mod: str, codes_var: str) -> set[str]:
    """从被测工程 support/fixtures/{codes_mod}.py 读取业务码常量字典的键集合。

    用 AST 解析（不 import 该模块，避免执行模块顶层代码的副作用，如依赖 pytest/.env）。
    支持两种定义形态：
      - 字面量字典：`SA_CODES: dict = {"key": None, ...}`
      - 基于其它 dict 的推导式：`SA_CODES = {k: None for keys in _PROBE_GROUPS.values() for k in keys}`
        （此时从被引用的 dict 字面量里收集键）
    """
    import ast

    mod = project_dir / "support" / "fixtures" / f"{codes_mod}.py"
    if not mod.is_file():
        return set()
    try:
        tree = ast.parse(mod.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()

    # 第一步：收集全部「顶层 dict 字面量」赋值（变量名 -> 键集合），兼容 Assign 与 AnnAssign
    dict_literals: dict[str, set[str]] = {}
    for n in tree.body:
        target = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            target = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            target = n.target.id
        if target and isinstance(n.value, ast.Dict):
            dict_literals[target] = {
                k.value for k in n.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}

    keys: set[str] = set()
    for n in tree.body:
        target = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            target = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            target = n.target.id
        if target != codes_var:
            continue
        # 字面量字典
        if isinstance(n.value, ast.Dict):
            for k in n.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
            return keys
        # 推导式：从被引用的 dict 变量收集键（如 `for keys in _PROBE_GROUPS.values()`）
        if isinstance(n.value, ast.DictComp):
            for gen in n.value.generators:
                it = gen.iter
                if isinstance(it, ast.Attribute) and isinstance(it.value, ast.Name) \
                        and it.value.id in dict_literals:
                    keys.update(dict_literals[it.value.id])
            return keys
    return keys


def _lint_code(code: str, codes_label: str, codes_keys: set[str]) -> tuple[list[str], list[str]]:
    """落盘前轻量校验（不重试、不自动修复）：语法编译 + 断言 op 白名单 + 反例业务码 key 对齐。

    返回 (errors, warnings)：
      - errors（语法错误）：文件完全不可运行，调用方应**拒绝落盘**并报错让用户重新生成；
      - warnings（op 非法 / 业务码 key 对不上）：文件能跑但存在必挂/白测风险，落盘但
        写日志 + 追加到「生成策略说明」核对清单，让测试人员看得见、优先处理。
    """
    errors: list[str] = []
    warnings: list[str] = []
    # 1) 语法编译：内置 compile 毫秒级，专门拦 keyword 重复 / 括号不匹配这类必炸错误
    try:
        compile(code, "<auto-gen>", "exec")
    except SyntaxError as e:  # noqa: BLE001
        errors.append(f"语法错误：{e.msg}（第 {e.lineno} 行）{e.text or ''}".strip())
    # 2) 断言操作符白名单：白名单外的 op（is_array/type/len 等）运行时会 raise ValueError
    for m in re.finditer(r"Assertion\s*\(([^)]*)\)", code):
        inner = m.group(1)
        om = re.search(r'\bop\s*=\s*"([a-z_]+)"', inner)
        if om and om.group(1) not in _VALID_OPS:
            line = code[:m.start()].count("\n") + 1
            warnings.append(
                f"不支持的断言操作符 op={om.group(1)!r}（第 {line} 行附近），运行时会 raise ValueError，"
                f"请改用白名单之一：{', '.join(sorted(_VALID_OPS))}")
    # 3) 反例业务码 key 对齐：_bf('key') 的 key 必须在业务码表字典键内，否则退化空壳反例=白测
    if codes_keys:
        for m in re.finditer(r'_bf\(["\']([a-z_]+)["\']\)', code):
            key = m.group(1)
            if key not in codes_keys:
                line = code[:m.start()].count("\n") + 1
                warnings.append(
                    f"反例业务码 key={key!r}（第 {line} 行）不在 {codes_label} 已探测键 "
                    f"{sorted(codes_keys)} 中，运行时 _bf 将降级为仅校验 /msg 存在（反例等于白测），"
                    f"请改用已探测的键或补充探测")
    return errors, warnings


def _tree_tc_ids(tree: dict) -> set[str]:
    """递归提取用例树里全部 TC-id（形如 TC-ENTERPRISE-01）。"""
    acc: set[str] = set()

    def _walk(node):
        if isinstance(node, dict):
            for k in ("tc_id", "id", "case_id"):
                v = node.get(k)
                if isinstance(v, str) and re.match(r"^TC-[A-Z0-9_]+-\d+$", v):
                    acc.add(v)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for x in node:
                _walk(x)

    _walk(tree)
    return acc


def _guard_alignment(obj: dict, module: str, tree_tcs: set[str],
                     min_ratio: float = 0.8) -> tuple[list[str], list[str]]:
    """渲染前守卫（防线2）：LLM 声明必须与输入对齐，防「幻觉编造别的模块 / 丢用例」。

    背景：2026-09-02 事故 —— LLM 无视输入的 53 条 enterprise 用例树，模仿 prompt 示例
    幻觉出 5 条 TC-OA_NOTICE 公告用例（module 自己声明 oa_notice，前缀校验自洽通过），
    全量覆盖把已有 49 条真实脚本毁掉。本守卫在渲染/落盘之前拦截这类输出。

    返回 (errors, warnings)：
      - errors 非空 → 拒绝落盘（module 不符 / 覆盖率 < min_ratio / 编造 tree 外 TC）；
      - warnings   → 覆盖率 ≥ min_ratio 但未全覆盖（落盘但写日志提醒核对）。
    """
    errs: list[str] = []
    warns: list[str] = []
    out_mod = obj.get("module", "")
    if out_mod != module:
        errs.append(f"module 不符：输出 {out_mod!r}，输入要求 {module!r}（疑似幻觉，禁止改动 module）")
    prefix = f"TC-{module.upper()}-"
    # 用例树编号集：TC-X-01 → "01"
    tree_nums = {t[len(prefix):] for t in tree_tcs if t.startswith(prefix)}
    # step 编号集：name "TC-X-C01-标题" → "01"（剥离 C/P 等字母前缀，兼容 C01/01 两种编号）
    step_nums: set[str] = set()
    for s in obj.get("steps", []):
        name = s.get("name", "")
        if not name.startswith(prefix):
            # 输出了非本模块前缀的 TC（如幻觉成别的模块编号）→ 记入错误
            m = re.match(r"^(TC-[A-Z0-9_]+)-", name)
            if m and m.group(1) != prefix.rstrip("-"):
                errs.append(f"step name {name!r} 的 TC 前缀不属于本模块（应为 {prefix}...，疑似幻觉编造）")
            continue
        seg = name[len(prefix):].split("-")[0]
        num = re.sub(r"^[A-Za-z]+", "", seg)
        if num:
            step_nums.add(num)
    if not tree_nums:
        return errs, warns   # 旧结构树无 TC-id 可比对：跳过覆盖校验
    covered = tree_nums & step_nums
    ratio = len(covered) / len(tree_nums)
    missing = sorted(tree_nums - step_nums, key=lambda x: (len(x), x))
    invented = sorted(step_nums - tree_nums)
    if invented:
        errs.append(f"输出含 {len(invented)} 个用例树中不存在的 TC 编号（疑似编造）：{', '.join(invented[:10])}"
                    + ("…" if len(invented) > 10 else ""))
    if ratio < min_ratio:
        errs.append(f"用例覆盖不全：输入用例树 {len(tree_nums)} 条，仅覆盖 {len(covered)} 条"
                    f"（覆盖率 {ratio:.0%} < {min_ratio:.0%}），缺失编号：{', '.join(missing[:20])}"
                    + ("…" if len(missing) > 20 else ""))
    elif missing:
        warns.append(f"用例覆盖不全（允许落盘，请核对）：输入 {len(tree_nums)} 条，覆盖 {len(covered)} 条"
                     f"（{ratio:.0%}），缺失编号：{', '.join(missing[:20])}")
    return errs, warns


def _body_schema_index(api_text: str) -> dict:
    """解析接口文档 JSON，建立 {method+path → {fields:{name→type}, required:set}} 索引。

    path 归一化：去尾部斜杠、统一小写，与声明 step 的 method/path 比较。
    非 JSON / 解析失败 / 无 body schema：返回空（body 对齐校验降级跳过，不误报）。
    """
    if not api_text:
        return {}
    try:
        doc = json.loads(api_text)
    except Exception:  # noqa: BLE001
        return {}
    idx: dict[str, dict] = {}
    for it in doc.get("interfaces") or []:
        req = it.get("request") or {}
        body = req.get("body") or []
        if not body:
            continue
        method = (it.get("method") or "get").lower()
        path = (it.get("path") or "").strip().rstrip("/").lower()
        fields: dict[str, str] = {}
        required: set[str] = set()
        for f in body:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            fields[f["name"]] = f.get("type") or ""
            if f.get("required"):
                required.add(f["name"])
        idx[f"{method} {path}"] = {"fields": fields, "required": required}
    return idx


_NUMERIC_TYPES = {"long", "int", "integer", "number", "decimal", "bigdecimal",
                  "big_decimal", "double", "float", "short", "byte", "money"}
_BOOL_TYPES = {"boolean", "bool"}
_STR_TYPES = {"string", "text", "char", "date", "time", "datetime", "date_time", "enum"}


def _body_value_mismatch(schema_type: str, val) -> bool:
    """判断声明 body 值类型是否与接口文档 schema 类型冲突。

    规则：
      - 字符串含 ${ 的引用值（如 '${enterprise_id}'）一律豁免：运行期类型由来源决定；
      - array<xxx>/array 期望 list；long/int/number/... 期望 int/float；boolean 期望 bool；
      - string/date/... 期望 str（数字可被服务端强转，放行；list/dict 判冲突）。
    返回 True=类型冲突（反序列化风险），False=对齐或无法判定。
    """
    t = (schema_type or "").lower().replace(" ", "")
    if not t:
        return False
    if isinstance(val, str) and "${" in val:
        return False
    if t.startswith("array<") or t in ("array", "list"):
        return not isinstance(val, list)
    if t in _NUMERIC_TYPES:
        return not isinstance(val, (int, float)) or isinstance(val, bool)
    if t in _BOOL_TYPES:
        return not isinstance(val, bool)
    if t in _STR_TYPES:
        return isinstance(val, (list, dict))
    return False


def _check_body_alignment(steps: list[dict], api_text: str) -> list[str]:
    """渲染前守卫（防线4）：LLM 声明 step 的 body 必须与接口文档 body schema 对齐。

    校验三项，全部**警告级**（不拦截落盘，追加到生成策略说明核对清单 + 日志）：
      ① body 字段名不在接口文档 schema → 疑似编造，接口可能忽略或 400；
      ② 接口文档 required 字段缺失 → 接口可能 400；
      ③ 值类型与 schema 冲突（long 收到字符串、array<long> 收到非列表等）→ 反序列化失败。
    声明了 body 但接口文档不可解析 / 找不到对应接口时跳过（降级不误报）。
    """
    if not steps:
        return []
    idx = _body_schema_index(api_text)
    if not idx:
        return []
    warns: list[str] = []
    for s in steps:
        body = s.get("body")
        if not isinstance(body, dict) or not body:
            continue
        method = (s.get("method") or "get").lower()
        path = (s.get("path") or "").strip().rstrip("/").lower()
        sch = idx.get(f"{method} {path}")
        if not sch:
            continue
        name = s.get("name") or "?"
        for fname, fval in body.items():
            stype = sch["fields"].get(fname)
            if stype is None:
                warns.append(f"step「{name}」body 字段 {fname!r} 不在接口文档 "
                             f"{method.upper()} {path} 的 body schema 中（疑似编造，接口可能忽略或 400）")
            elif _body_value_mismatch(stype, fval):
                warns.append(f"step「{name}」body 字段 {fname!r} 类型与接口文档 `{stype}` 不符"
                             f"（当前声明为 {type(fval).__name__}；long/数字/布尔字段请用 `${{var}}` 引用或对应类型值）")
        for rq in sorted(sch["required"] - set(body)):
            warns.append(f"step「{name}」body 缺少接口文档 required 字段 {rq!r}（接口可能 400，请补全）")
    return warns


# 创建类接口路径段特征词：命中即应带 cleanup（仅正例要求，反例不需要清理）
_CREATE_VERBS = ("create", "add", "register", "insert", "new", "save")
# 非账号角色（与渲染器 NON_ACCOUNT_ROLES 一致）：只允许单 step role，禁止模块级 pytestmark
_NON_ACCOUNT_ROLES = {"anonymous", "not_login", "notlogin", "unauth", "guest"}


def _check_decl_semantics(spec: dict) -> list[str]:
    """声明语义校验（渲染前警告级，配合渲染器兜底过滤，不拦截落盘）。

    ① 创建接口正例未声明 cleanup → 数据不清理（污染被测库），提示补 id_var/delete_path；
    ② 模块级 pytestmark_roles 含非账号角色（anonymous/not_login…）→ 渲染器已兜底过滤，
       提示 LLM 别把未登录混进模块级集合（未登录只出现在单 step 的 role）。
    与 _check_body_alignment 同防线层级：警告进日志 + 生成策略说明核对清单。
    """
    warns: list[str] = []
    for s in spec.get("steps") or []:
        path = s.get("path") or ""
        segs = [p for p in path.split("/") if p]
        is_create = any(seg in _CREATE_VERBS for seg in segs)
        if is_create and not s.get("cleanup") and not s.get("biz_fail"):
            warns.append(f"step「{s.get('name') or '?'}」是创建类正例但未声明 cleanup"
                         f"（{s.get('method')} {path}），执行后数据不清理，请补 id_var/delete_path")
    for r in spec.get("pytestmark_roles") or []:
        if r in _NON_ACCOUNT_ROLES:
            warns.append(f"模块级 pytestmark_roles 含非账号角色 {r!r}（已由渲染器自动过滤）；"
                         f"未登录（anonymous）应只声明在单个 step 的 role 里")
    return warns


def _gen_code(inputs: dict, evidence: dict | None = None,
              log_hook=None, llm_config: dict | None = None,
              project_engine: dict | None = None, module: str = "") -> tuple[str, str, dict]:
    """调用 LLM 生成「用例声明 JSON」→ 确定性渲染成 pytest 源码（方向 A）。

    LLM 只输出受 JSON Schema 约束的声明（run_json_skill 带 schema+业务规则校验与自动重试），
    不再写任何 Python 代码 —— op 白名单 / _bf / pytestmark / save / cleanup 全部由
    auto_gen_render 的固定模板生成，从架构上杜绝"AI 发明不支持的 op / 写错语法"。
    返回 (code, strategy_desc, obj)：obj 供调用方做渲染前对齐守卫（_guard_alignment）。
    """
    spec = skill_auto.SKILL
    profile = None
    if project_engine:
        from dataclasses import replace
        profile = collect_system_profile(project_engine, module)
        # 复制 spec（不 mutate 共享常量，避免并发交错污染 system_prompt）
        spec = replace(spec, system_prompt=skill_auto.build_system_prompt(profile))
    res = run_json_skill(spec, inputs, evidence=evidence, log_hook=log_hook,
                         llm_config=llm_config)
    obj = res["result"]
    strategy = obj.get("strategy", "")
    if profile is None:
        profile = SystemProfile()
    code = render_code(obj, profile)
    return code, strategy, obj


def _target_path(project_engine: dict, module: str, target_file: str = "") -> Path:
    """生成目标脚本路径：用户填了 target_file 用用户指定（resolve_target_file 统一规则），
    未填按默认 {api_base}/{module}/test_{module}.py。
    生成目录 = 被测系统子目录（gen_dir 显式配置优先，未填按系统画像扫默认推断），
    该子目录 conftest 提供 api_client/ctx/cleanup_registry 等 fixture，其他目录会 fixture not found。
    """
    resolved = resolve_target_file(project_engine, module, target_file)
    if resolved is not None:
        return resolved
    base = collect_system_profile(project_engine).api_base
    return base / module / f"test_{module}.py"


def _read_api_flow(db: Session, run_id: int, api_text: str) -> dict:
    """读取接口文档的已确认数据链（源头治理主序）。

    优先级：接口文档卡片人工确认的 stage.meta.data_flow → 候选 stage.meta.data_flow_candidates →
    现场自动启发式（不进库）。返回统一形态 {interfaces:[{id,name,path,role,depends_on,...}], order_recommended}。
    """
    stage = (db.query(models.StageState).filter(
        models.StageState.run_id == run_id, models.StageState.stage_type == "api_doc")
        .order_by(models.StageState.id.desc()).first())
    if stage:
        meta = stage.meta or {}
        for key in ("data_flow", "data_flow_candidates"):
            val = meta.get(key)
            if isinstance(val, dict) and val.get("interfaces"):
                return val
    if not api_text:
        return {}
    try:
        from app.services import data_flow as df_svc
        doc = json.loads(api_text)
        return df_svc.analyze_dataflow(doc)
    except Exception:  # noqa: BLE001 接口文档不可解析时降级为空数据链
        return {}


def generate(db: Session, run_id: int, project_engine: dict, project: str,
             llm_config: dict | None = None, fix_context: str = "",
             target_file: str = "") -> dict:
    """主入口：读 approved 用例集 + 接口文档 → 生成 → diff 预览 → 落盘。

    fix_context 非空表示「执行失败后的 AI 修复重生成」：把失败根因/pytest 日志作为上下文喂给 skill。
    target_file 为用户指定的目标脚本文件（留空=默认 test_{module}.py）；
    AI 修复重生成时应透传同一目标文件，避免修复写进默认文件造成双文件漂移。
    全程写 workspaces/{project}/{run_id}/logs/auto_gen.log（含每轮校验错误），成功失败都注册日志工件。
    """
    import time as _time
    started = _time.time()
    log_path = None
    from app import storage as _storage
    pkey = f"auto_gen:{run_id}"   # 前端轮询「思考过程」用
    task_progress.start(pkey)

    def _log(line: str):
        nonlocal log_path
        ts = _time.strftime("%Y-%m-%d %H:%M:%S")
        log_path = _storage.append_log(project, run_id, "auto_gen", f"[{ts}] {line}\n")
        task_progress.report(pkey, line)   # 同步喂给前端轮询

    def _register_log_artifact():
        if log_path:
            db.add(models.Artifact(run_id=run_id, stage_type="auto_gen", type="gen_log",
                                   name="自动化生成日志", file_path=str(log_path),
                                   source={"source": "gen_log", "module": module}))
            db.commit()

    cs = (db.query(models.CaseSet)
          .filter(models.CaseSet.run_id == run_id, models.CaseSet.status == "approved")
          .order_by(models.CaseSet.version.desc()).first())
    if not cs:
        task_progress.finish(pkey, error="尚无 approved 用例集")
        raise ValueError("尚无评审通过的用例集（approved），请先完成用例评审阶段")

    api_text = ""
    art = (db.query(models.Artifact).filter(
        models.Artifact.run_id == run_id, models.Artifact.type == "api_doc")
        .order_by(models.Artifact.version.desc()).first())
    if art and art.file_path:
        p = Path(art.file_path)
        if p.exists():
            api_text = p.read_text(encoding="utf-8", errors="ignore")

    tree = cs.content
    module = tree.get("module", "module")
    # 防线3：日志打印所选用例集关键信息（id/版本/类型/TC 数），排查「取错用例集/幻觉」类问题
    tree_tcs = _tree_tc_ids(tree)
    cs_ctype = (cs.gen_meta or {}).get("case_type") or tree.get("case_type") or "business"
    _log(f"[取数] 使用已批准用例集 #{cs.id} v{cs.version}（{cs_ctype}，module={module}，"
         f"用例 {len(tree_tcs)} 条）")
    # 全量覆盖：旧文件只用于「手写维护」检测 + diff 对比，不喂旧 TC 给 LLM 做增量去重
    target = _target_path(project_engine, module, target_file)
    existing_code = target.read_text(encoding="utf-8") if target.exists() else ""
    # 旧文件 TC-ID 全集（供 diff 展示用，含头部映射注释，仅参考）；existing_n 供日志计数真实用例数
    existing_tc_ids = set(re.findall(r"TC-[A-Z0-9_-]+", existing_code))
    existing_n = len(set(re.findall(r"\bFlowStep\(", existing_code)))
    if not existing_n:
        existing_n = len(set(re.findall(r"^def test_", existing_code, re.M)))

    profile = collect_system_profile(project_engine, module)
    # 业务码键清单：读被测工程业务码表字典的字面量键（供 LLM 的 biz_fail 对齐 + 落盘前校验）
    codes_keys: set[str] = set()
    if profile.codes_var and profile.codes_mod:
        pj = Path(project_engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
        codes_keys = _read_codes_keys(pj, profile.codes_mod, profile.codes_var)
    inputs = {
        "module": module,
        "case_tree": tree,
        # 量化覆盖目标（防线1）：LLM 必须覆盖这里列出的每一个 TC 编号，steps 数量 ≥ case_count
        "case_count": len(tree_tcs),
        "required_tc_ids": sorted(tree_tcs),
        "api_doc": api_text[:80000] if api_text else "",
        "api_doc_present": bool(api_text),
        # 全量重新生成：不传 existing_tc_ids / is_incremental，避免 LLM「只追加新 TC」导致覆盖为空转
        "regenerate": True,
        # 实际可用 fixture 清单（被测系统子目录 conftest 继承链扫描，防 LLM 臆造）
        "available_fixtures": profile.fixtures,
        # 已配置角色账号的角色键：约束 requires_role / step.role 只允许用这些
        "available_roles": profile.available_roles,
        # 业务码键清单：声明里 biz_fail 只能取这些值
        "codes_keys": sorted(codes_keys),
        # 接口文档数据链（源头治理，2026-09-02）：接口文档卡片人工确认的 depends_on/字段来源，
        # 作为 steps 顺序主序（api_flow）；确认过数据链的接口按 order_recommended 顺序声明步骤
        "api_flow": _read_api_flow(db, run_id, api_text),
    }
    if fix_context:
        inputs["fix_context"] = fix_context   # 执行失败后的修复重生成：根因+pytest 日志
    _log(f"===== 自动化生成开始（module={module}, 全量覆盖={bool(existing_code)}, "
         f"接口文档 {len(api_text)} 字符, 旧 TC {existing_n} 个, "
         f"被测系统={profile.system_name}, 使用 AI 模型：{model_label(llm_config)}, "
         f"可用 fixture {len(inputs['available_fixtures'])} 个, 业务码键 {len(codes_keys)} 个"
         + ("，携带执行失败修复上下文" if fix_context else "") + "）=====")

    def _hook(attempt: int, errs: list[str]) -> None:
        # json 型 skill：每轮输出都过 JSON Schema + 业务规则校验
        if errs:
            _log(f"[生成] 第 {attempt} 次输出未通过契约校验（JSON Schema/业务规则）：{errs}")
        else:
            _log(f"[生成] 第 {attempt} 次输出通过契约校验，开始确定性渲染 pytest 脚本")

    # 增量保护：含「手写维护」标记的文件永不覆盖
    if existing_code and "手写维护" in existing_code:
        _log("[结果] 失败：目标文件含「手写维护」标记，拒绝覆盖")
        _register_log_artifact()
        task_progress.finish(pkey, error="目标文件含「手写维护」标记")
        raise ValueError("目标文件含「手写维护」标记，拒绝覆盖。请在生成前先手动调整或另建模块目录。")

    try:
        code, strategy_desc, obj = _gen_code(inputs, log_hook=_hook, llm_config=llm_config,
                                             project_engine=project_engine, module=module)
    except Exception as e:  # noqa: BLE001 失败也留完整日志
        _log(f"[结果] 失败：{e}")
        _register_log_artifact()
        task_progress.finish(pkey, error=str(e))
        raise
    # 防线2：渲染前对齐守卫 —— LLM 声明必须与输入用例树对齐（module 一致 + TC 覆盖率），
    # 拦截「幻觉编造别的模块/丢用例」的输出（不达标拒绝落盘，不覆盖旧脚本）
    guard_errs, guard_warns = _guard_alignment(obj, module, tree_tcs)
    if guard_errs:
        _log("[守卫] LLM 输出与输入用例树不对齐，已拒绝落盘（未写入目标文件）：")
        for e in guard_errs:
            _log(f"  - {e}")
        _register_log_artifact()
        task_progress.finish(pkey, error="LLM 输出与输入用例树不对齐，已拒绝落盘：" + "；".join(guard_errs))
        raise ValueError("LLM 输出与输入用例树不对齐，已拒绝落盘（旧文件未被覆盖），请重新生成：\n"
                         + "\n".join(guard_errs))
    if guard_warns:
        for w in guard_warns:
            _log(f"[守卫] {w}")
        strategy_desc = (strategy_desc or "") + "\n\n**⚠ 覆盖警告**：\n- " + "\n- ".join(guard_warns)
    # 防线4：声明 body 与接口文档 schema 对齐（字段名/required/类型，警告级，不拦截落盘）
    body_warns = _check_body_alignment(obj.get("steps") or [], api_text)
    if body_warns:
        for w in body_warns:
            _log(f"[body 对齐] {w}")
        strategy_desc = (strategy_desc or "") + \
            f"\n\n**⚠ body 与接口文档对齐警告（{len(body_warns)} 处，请逐条核对）**：\n- " + "\n- ".join(body_warns)
    # 防线5：声明语义（创建类 cleanup / 模块级未登录角色；渲染器已兜底过滤，仅提示核对）
    sem_warns = _check_decl_semantics(obj)
    if sem_warns:
        for w in sem_warns:
            _log(f"[声明语义] {w}")
        strategy_desc = (strategy_desc or "") + \
            f"\n\n**⚠ 声明语义警告（{len(sem_warns)} 处，请核对）**：\n- " + "\n- ".join(sem_warns)
    # 确定性兜底：移除未配置角色的 requires_role，避免整模块全 skip
    if profile.available_roles:
        removed = len(re.findall(r"requires_role\('([a-z_]+)'\)", code)) - len(
            re.findall(r"requires_role\('([a-z_]+)'\)", _patch_roles(code, profile.available_roles)))
        code = _patch_roles(code, profile.available_roles)
        if removed:
            _log(f"[角色防护] 已移除 {removed} 个未配置角色的 requires_role 标记"
                 f"（当前可用角色：{', '.join(profile.available_roles)}）；"
                 f"对应角色用例运行时将单独跳过，不再整模块全 skip")

    # 落盘前轻量校验（不重试、不自动修复）：
    #   语法编译错误 → 拒绝落盘（文件完全不可运行），报错让用户重新生成；
    #   op 非法 / 反例业务码 key 对不上 → 落盘但显式警告（日志 + 策略说明核对清单）。
    lint_errors, lint_warnings = _lint_code(
        code,
        codes_label=(f"{profile.codes_var}（{profile.codes_mod}）" if profile.codes_var else ""),
        codes_keys=codes_keys)
    if lint_errors:
        _log("[校验失败] 生成代码存在语法错误，已拒绝落盘（未写入目标文件），请重新生成：")
        for e in lint_errors:
            _log(f"  - {e}")
        _register_log_artifact()
        task_progress.finish(pkey, error="生成代码存在语法错误，已拒绝落盘，请重新生成")
        raise ValueError("生成代码存在语法错误，已拒绝落盘，请重新生成：\n" + "\n".join(lint_errors))
    if lint_warnings:
        _log(f"[校验警告] 生成代码存在 {len(lint_warnings)} 处需人工核对的问题（已落盘）：")
        for w in lint_warnings:
            _log(f"  - {w}")

    diff = difflib.unified_diff(
        existing_code.splitlines(), code.splitlines(),
        fromfile="旧", tofile="新", lineterm="") if existing_code else None

    # 落盘（目标目录 + conftest 占位说明，实际 conftest 由部署侧提供/复用）
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")

    from app import storage
    ws_path = storage.save_text(project, run_id, f"test_{module}.py", code, subdir="auto")
    db.add(models.Artifact(run_id=run_id, stage_type="auto_gen", type="auto_file",
                           name=f"test_{module}.py", file_path=str(ws_path), version=1,
                           source={"source": "skill", "target": str(target)}))
    db.commit()

    # 统计实际生成的用例：优先按 ApiCase 的 name="TC-..." 提取（不含头部「来源用例映射」注释）
    new_tc = sorted(set(re.findall(r'name="TC-[A-Z0-9_-]+', code)))
    if not new_tc:
        # 结构未知时退回：FLOW_STEPS 数 / def test_ 数 / 全文件唯一 TC-ID
        n_flow = len(re.findall(r"\bFlowStep\(", code))
        n_def = len(re.findall(r"^def test_", code, re.M))
        n_cases = n_flow or n_def or len(set(re.findall(r"TC-[A-Z0-9_-]+", code)))
    else:
        n_cases = len(new_tc)
    _log(f"[结果] 成功：全量生成 {n_cases} 个用例（覆盖旧 {existing_n} 个）→ {target}，"
         f"耗时 {_time.time() - started:.1f}s")
    _register_log_artifact()
    task_progress.finish(pkey)

    desc_parts = ["## 生成策略说明"]
    if strategy_desc:
        desc_parts.append(strategy_desc)
    else:
        desc_parts.append("（LLM 未输出策略说明，请直接看生成代码）")
    if existing_code:
        desc_parts.append("\n本次为全量覆盖生成：基于最新需求与接口文档重新生成全部用例，已覆盖旧脚本。")
    if lint_warnings:
        desc_parts.append(f"\n----\n**⚠ 自动校验警告（{len(lint_warnings)} 处，请优先处理）**：")
        for w in lint_warnings:
            desc_parts.append(f"- {w}")
    desc_parts.append("\n----\n**请测试人员手工核对**，重点检查：")
    desc_parts.append("- 字段名是否与接口文档实际返回一致（如 name vs noticeTypeName）；")
    desc_parts.append("- 字段断言 op 是否优先 eq/ne（仅接口返回值无法精确预知时才允许 exists/contains/gt 等特殊 op）；")
    desc_parts.append("- 反例是否显式 biz_auto=False（默认 True 会自动追加 biz_ok 跟 biz_fail 冲突）；")
    desc_parts.append("- 多角色场景是否用了 FLOW_STEPS + role_registry（不要用 CASES + api_client）；")
    desc_parts.append("- 资源 ID 是否通过分页反查 save，未写死；")
    desc_parts.append("- 用例顺序已按「业务生命周期（增→查→改→删）+ ${var} 数据依赖」拓扑编排（渲染器兜底）：")
    desc_parts.append("  子实体（如员工）整体在父实体（如企业）增查改之后、父实体删除之前；"
                      "请重点核对 save→${xxx_id} 依赖链（员工用例是否确实引用了企业反查出的企业 id）。")

    # 归一化后的目标文件（相对 pytest 项目根的路径字符串）：供前端回显 / 执行报告透传
    rel_target = str(target)
    try:
        _pj = Path(project_engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
        rel_target = str(target.resolve().relative_to(_pj.resolve())).replace("\\", "/")
    except ValueError:
        pass

    return {
        "module": module,
        "target": str(target),
        "target_file": rel_target,
        "saved": True,
        "regenerated": bool(existing_code),
        "new_tc": new_tc,
        "old_tc": sorted(existing_tc_ids),
        "diff_preview": "\n".join(diff) if diff else "",
        "code": code,
        "desc": "\n".join(desc_parts),
        "model": model_label(llm_config),
    }
