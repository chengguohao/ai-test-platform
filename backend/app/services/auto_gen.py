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
from app.services import task_progress
from app.services.ai_llm import model_label
from app.services.skills import auto_gen as skill_auto
from app.services.skill_engine import run_code_skill
from app.services.system_profile import collect_system_profile

def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return m.group(1).strip() if m else text.strip()


def _extract_strategy(text: str) -> str:
    """提取 LLM 在代码块前输出的『生成策略说明』。

    skill 提示词要求 LLM 先写一段 markdown 说明（设计思路），再写代码块。
    取代码块之前的全部文本作为策略说明，去掉开头的 ## 生成策略说明 标题前缀。
    """
    m = re.search(r"```(?:python)?\s*", text)
    if not m:
        return ""
    head = text[:m.start()].strip()
    head = re.sub(r"\A#+\s*生成策略说明\s*\n?", "", head, flags=re.M)
    return head.strip()


_BF_HELPER = '''
def _bf(key):
    """动态业务失败断言：探测不到业务码时退化为「msg 存在」断言，避免导入期 None 崩溃。"""
    code = SA_CODES.get(key)
    if code is None:
        return [Assertion(expected=True, op="exists", field="/msg",
                          reason=f"业务码 {key} 未探测到，退化为仅校验失败信封")]
    return Assertion.biz_fail(code=code) + [Assertion(expected=True, op="exists", field="/msg")]

'''


def _patch_anonymous_client(code: str) -> str:
    """兜底 2：LLM 自创匿名 client 类 → 统一为 ApiClient(base_url)。

    触发条件：代码里出现「非 ApiClient 的 XxxClient(base_url)」引用（如 _AnonymousClient(base_url)），
    说明 LLM 自创了 client 类。run_case 依赖 client.record_assertions/mark_expect，
    自创类（如基于 requests.Session）缺这些方法会在运行时 AttributeError 崩溃。
    处理：
      1) 替换该引用为 ApiClient(base_url)；
      2) 删除被引用的自定义 client 类定义块（类体基于 requests 或类名以下划线开头才删，保守）；
      3) 补 from support.clients.api_client import ApiClient（若未导入）；
      4) 删类后 import requests 已无引用时一并删除。
    """
    m_ref = re.search(r'\b(?!ApiClient\b)(\w+Client)\(base_url\)', code)
    if not m_ref:
        return code
    cls_name = m_ref.group(1)
    # 1) 替换引用
    code = re.sub(r'\b(?!ApiClient\b)\w+Client\(base_url\)', 'ApiClient(base_url)', code)
    # 2) 删除被引用的自定义 client 类定义块（到下一个顶层代码为止）
    lines = code.splitlines(keepends=True)
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        head = ln.lstrip()
        if head.startswith(f"class {cls_name}:"):
            block, j = [ln], i + 1
            while j < n:
                l2 = lines[j]
                if l2.strip() and not l2.startswith((" ", "\t")):
                    break
                block.append(l2)
                j += 1
            block_text = "".join(block)
            # 保守：仅当类体基于 requests 或类名以下划线开头（自创特征）才删除
            if "requests" in block_text or cls_name.startswith("_"):
                i = j
                continue
            out.extend(block)
            i = j
            continue
        out.append(ln)
        i += 1
    code = "".join(out)
    # 3) 补 import ApiClient（插在最后一个 import 行之后）
    if "ApiClient(base_url)" in code and "from support.clients.api_client import ApiClient" not in code:
        m = list(re.finditer(r'^import |^from .+ import .+$', code, re.M))
        if m:
            pos = m[-1].end()
            code = code[:pos] + "\nfrom support.clients.api_client import ApiClient" + code[pos:]
        else:
            code = "from support.clients.api_client import ApiClient\n" + code
    # 4) 清理已无引用的孤立 import requests
    if "import requests" in code and "requests." not in code:
        code = re.sub(r'^import requests\s*\n', '', code, flags=re.M)
    return code


def _auto_patch(code: str) -> str:
    """确定性兜底（纯文本、不重试）：无论 LLM 怎么写，都不会再产出崩溃代码。
    1) 自创匿名 client 类 → ApiClient(base_url)（run_case 依赖 record_assertions/mark_expect）；
    2) 导入期会崩的 Assertion.biz_fail(code=SA_CODES.get("X")) → *_bf("X") + 注入 _bf 辅助函数。"""
    code = _patch_anonymous_client(code)
    if 'Assertion.biz_fail(code=SA_CODES.get(' not in code:
        return code
    # 注入 _bf helper（若未定义）
    if "def _bf(" not in code:
        # 插在最后一个 import 行之后
        m = list(re.finditer(r'^import |^from .+ import .+$', code, re.M))
        if m:
            pos = m[-1].end()
            code = code[:pos] + "\n" + _BF_HELPER + code[pos:]
        else:
            code = _BF_HELPER + code
    # 替换：列表上下文里的 biz_fail(code=SA_CODES.get("X"))  → *_bf("X")
    code = re.sub(
        r'Assertion\.biz_fail\(code=SA_CODES\.get\("([a-z_]+)"\)\),',
        r'*_bf("\1"),', code)
    # 兜底：末尾无逗号的情况（如断言列表末元素）
    code = re.sub(
        r'Assertion\.biz_fail\(code=SA_CODES\.get\("([a-z_]+)"\)\)',
        r'*_bf("\1")', code)
    return code


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


def _gen_code(inputs: dict, evidence: dict | None = None,
              log_hook=None, llm_config: dict | None = None,
              project_engine: dict | None = None, module: str = "") -> tuple[str, str]:
    """一次性调用 LLM 生成代码 + 策略说明，不做 AST 校验/重试。

    设计取舍：测试人员是脚本最终负责人，AST 校验会拖慢首屏（每次失败重试 5+ 分钟），
    且无法覆盖字段名/业务码语义错误。改为：LLM 一次输出 → _auto_patch 确定性兜底 biz_fail
    写法 → 直接返回，让测试人员手工核对。
    log_hook(1, []) 兼容旧接口，仅记生成完成。
    返回 (code, strategy_desc)：strategy_desc 是 LLM 在代码块前写的『生成策略说明』。

    被测系统解耦：system prompt 按项目画像渲染（marker/业务码/角色/marker 清单/fixtures），
    换被测系统只改项目 gen_dir，不传染旧骨架。
    """
    spec = skill_auto.SKILL
    if project_engine:
        from dataclasses import replace
        profile = collect_system_profile(project_engine, module)
        # 复制 spec（不 mutate 共享常量，避免并发交错污染 system_prompt）
        spec = replace(spec, system_prompt=skill_auto.build_system_prompt(profile))
    raw = run_code_skill(spec, inputs, evidence=evidence, llm_config=llm_config)
    code = _extract_code(raw)
    code = _auto_patch(code)  # 确定性兜底：修掉导入期崩溃的 biz_fail 写法
    strategy = _extract_strategy(raw)
    if log_hook:
        try:
            log_hook(1, [])  # 一次性生成，errs 始终为空（兼容旧接口）
        except Exception:  # noqa: BLE001 日志不能影响主流程
            pass
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
    inputs = {
        "module": module,
        "case_tree": tree,
        "api_doc": api_text[:80000] if api_text else "",
        "api_doc_present": bool(api_text),
        # 全量重新生成：不传 existing_tc_ids / is_incremental，避免 LLM「只追加新 TC」导致覆盖为空转
        "regenerate": True,
        # 实际可用 fixture 清单（被测系统子目录 conftest 继承链扫描，防 LLM 臆造）
        "available_fixtures": profile.fixtures,
        # 已配置角色账号的角色键：约束 requires_role / FlowStep role 只允许用这些
        "available_roles": profile.available_roles,
    }
    if fix_context:
        inputs["fix_context"] = fix_context   # 执行失败后的修复重生成：根因+pytest 日志
    _log(f"===== 自动化生成开始（module={module}, 全量覆盖={bool(existing_code)}, "
         f"接口文档 {len(api_text)} 字符, 旧 TC {existing_n} 个, "
         f"被测系统={profile.system_name}, 使用 AI 模型：{model_label(llm_config)}, "
         f"可用 fixture {len(inputs['available_fixtures'])} 个"
         + ("，携带执行失败修复上下文" if fix_context else "") + "）=====")

    def _hook(attempt: int, errs: list[str]) -> None:
        # 兼容旧 _gen_code 接口：errs 始终为空（已去掉 AST 校验/重试）
        _log("[生成] LLM 输出已收到（无 AST 校验/重试，请测试人员手工核对生成代码）")

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
