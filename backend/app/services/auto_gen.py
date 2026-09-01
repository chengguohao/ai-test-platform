"""自动化用例增量生成：approved 用例 + 接口文档 → pytest ApiCase 脚本。

遵循 pytest-bdd 规范（parametrize 展开/信封守卫/save-清理/TC 映射）；
增量保护：不覆盖含「手写维护」标记的文件；同模块二次迭代仅追加新 TC（由 skill 依据已有文件去重）。
"""
from __future__ import annotations

import difflib
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
from app.services.system_profile import SystemProfile, collect_system_profile


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


def _gen_code(inputs: dict, evidence: dict | None = None,
              log_hook=None, llm_config: dict | None = None,
              project_engine: dict | None = None, module: str = "") -> tuple[str, str]:
    """调用 LLM 生成「用例声明 JSON」→ 确定性渲染成 pytest 源码（方向 A）。

    LLM 只输出受 JSON Schema 约束的声明（run_json_skill 带 schema+业务规则校验与自动重试），
    不再写任何 Python 代码 —— op 白名单 / _bf / pytestmark / save / cleanup 全部由
    auto_gen_render 的固定模板生成，从架构上杜绝"AI 发明不支持的 op / 写错语法"。
    返回 (code, strategy_desc)：strategy_desc 取自声明里的 strategy 字段。
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
    return code, strategy


def _target_path(project_engine: dict, module: str) -> Path:
    # 生成目录 = 被测系统子目录（gen_dir 显式配置优先，未填按系统画像扫默认推断），
    # 该子目录 conftest 提供 api_client/ctx/cleanup_registry 等 fixture，其他目录会 fixture not found
    base = collect_system_profile(project_engine).api_base
    return base / module / f"test_{module}.py"


def generate(db: Session, run_id: int, project_engine: dict, project: str,
             llm_config: dict | None = None, fix_context: str = "") -> dict:
    """主入口：读 approved 用例集 + 接口文档 → 生成 → diff 预览 → 落盘。

    fix_context 非空表示「执行失败后的 AI 修复重生成」：把失败根因/pytest 日志作为上下文喂给 skill。
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
    # 全量覆盖：旧文件只用于「手写维护」检测 + diff 对比，不喂旧 TC 给 LLM 做增量去重
    target = _target_path(project_engine, module)
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
        code, strategy_desc = _gen_code(inputs, log_hook=_hook, llm_config=llm_config,
                                        project_engine=project_engine, module=module)
    except Exception as e:  # noqa: BLE001 失败也留完整日志
        _log(f"[结果] 失败：{e}")
        _register_log_artifact()
        task_progress.finish(pkey, error=str(e))
        raise
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
    desc_parts.append("- 资源 ID 是否通过分页反查 save，未写死。")

    return {
        "module": module,
        "target": str(target),
        "saved": True,
        "regenerated": bool(existing_code),
        "new_tc": new_tc,
        "old_tc": sorted(existing_tc_ids),
        "diff_preview": "\n".join(diff) if diff else "",
        "code": code,
        "desc": "\n".join(desc_parts),
        "model": model_label(llm_config),
    }
