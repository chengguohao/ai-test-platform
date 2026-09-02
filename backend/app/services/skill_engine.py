"""Skill 引擎：固定执行流程 + 固定输出（JSON Schema 校验通过才返回）。

用法：
    spec = get_skill("case_gen")
    result = run_json_skill(spec, inputs, evidence=evidence)   # 校验失败自动重试
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import jsonschema

from app.services import ai_llm


@dataclass
class SkillSpec:
    id: str
    name: str
    version: str
    system_prompt: str                      # 固定规则（反幻觉约束、覆盖清单等）
    user_template: str                      # 输入渲染模板，{inputs} 占位
    output_schema: dict | None = None       # JSON 输出契约（json 型 skill 必填）
    validator: Callable[[dict], list[str]] | None = None  # 额外规则校验（返回错误列表）
    max_retries: int = 2
    kind: str = "json"                      # json / code
    desc: str = ""                          # 面向测试人员的一句大白话用途


def build_messages(spec: SkillSpec, inputs: dict) -> list[dict]:
    payload = dict(inputs)
    user = spec.user_template.format(inputs=json.dumps(payload, ensure_ascii=False, indent=2))
    # 防回归：占位符若误写成 {{inputs}}（format 字面量转义），输入将永远不会注入，
    # LLM 只能看到模板骨架 → 必然幻觉（2026-09-02 auto_gen 声明式重构事故）。此处硬拦。
    if "{inputs}" in user:
        raise ValueError(f"Skill[{spec.id}] 的 user_template 占位符写成了 {{{{inputs}}}}（双花括号是 format "
                         "字面量转义，输入无法注入），请改为单花括号 {{inputs}}")
    return [{"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": user}]


def _validate(spec: SkillSpec, obj: dict) -> list[str]:
    errs: list[str] = []
    if spec.output_schema:
        try:
            jsonschema.validate(obj, spec.output_schema)
        except jsonschema.ValidationError as e:
            errs.append(f"输出不满足契约: {e.message}（位于 {list(e.relative_path)[-3:] or '根'}）")
    if spec.validator:
        errs += spec.validator(obj)
    return errs


def run_json_skill(spec: SkillSpec, inputs: dict, evidence: dict | None = None,
                   log_hook: Callable[[int, list[str]], None] | None = None,
                   llm_config: dict | None = None) -> dict:
    """执行 JSON 型 skill：组装消息（含 MCP/URL 实据）→ LLM → 校验 → 重试。

    log_hook(第几次尝试, 校验错误列表) 在每轮校验后触发，供调用方把过程写进日志文件。
    llm_config 覆盖全局模型配置（项目绑定的 AI 模型）。
    """
    if evidence:
        inputs = {**inputs, "evidence": evidence}
    messages = build_messages(spec, inputs)
    last_err = ""
    for attempt in range(1 + spec.max_retries):
        if last_err:
            messages = messages + [{"role": "user",
                                    "content": f"上次输出未通过校验：{last_err}\n请修正后仅输出合法 JSON。"}]
        try:
            obj = ai_llm.chat_json(messages, llm_config=llm_config)
        except Exception as e:  # noqa: BLE001 LLM 偶发空返回/网络异常 → 视作一次失败自动重试
            last_err = f"LLM 输出异常：{e}"
            if log_hook:
                try:
                    log_hook(attempt + 1, [last_err])
                except Exception:  # noqa: BLE001 日志不能影响主流程
                    pass
            continue
        errs = _validate(spec, obj)
        if log_hook:
            try:
                log_hook(attempt + 1, errs)
            except Exception:  # noqa: BLE001 日志不能影响主流程
                pass
        if not errs:
            return {"result": obj, "attempts": attempt + 1, "skill": spec.id, "skill_version": spec.version}
        last_err = "；".join(errs)
    raise ValueError(f"Skill[{spec.id}] 连续 {1 + spec.max_retries} 次未通过校验：{last_err}")


def run_code_skill(spec: SkillSpec, inputs: dict, evidence: dict | None = None,
                   llm_config: dict | None = None) -> str:
    """执行 code 型 skill（如自动化用例生成），返回代码文本。"""
    if evidence:
        inputs = {**inputs, "evidence": evidence}
    messages = build_messages(spec, inputs)
    return ai_llm.chat(messages, llm_config=llm_config)


def canonical(prefix: str, n: int, width: int = 2) -> str:
    return f"TC-{prefix}-{n:0{width}d}"
