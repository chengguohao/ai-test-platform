"""大模型调用统一封装（OpenAI 兼容，如 DeepSeek）。

支持按请求覆盖配置：llm_config = {base_url, api_key, model, temperature}，
用于项目绑定 ai_model_configs 中的模型；未传/缺项回退全局 .env。
"""
from __future__ import annotations

import json
import re

from app.config import settings


def _client(llm_config: dict | None = None):
    from openai import OpenAI
    cfg = settings()
    c = llm_config or {}
    kwargs = {
        "api_key": c.get("api_key") or cfg.LLM_API_KEY or "EMPTY",
        "base_url": c.get("base_url") or cfg.LLM_BASE_URL,
        "timeout": cfg.LLM_TIMEOUT,
    }
    if cfg.LLM_PROXY:
        # 走 httpx 代理（OpenAI SDK 支持注入自定义 httpx.Client）
        import httpx
        kwargs["http_client"] = httpx.Client(
            proxy=cfg.LLM_PROXY, timeout=cfg.LLM_TIMEOUT)
    return OpenAI(**kwargs)


def model_label(llm_config: dict | None = None) -> str:
    """展示用的 AI 模型显示名，与 AI 配置页口径一致。

    - 项目绑定了 ai_model_configs：显示「别名（模型名）」，如 Deepseek（deepseek-v4-flash）；
    - 未绑定（回退全局 .env）：显示「模型名（全局默认）」，提醒用户与配置页模型不同时去项目里绑定。
    """
    c = llm_config or {}
    name, model = c.get("name"), c.get("model")
    if name and model:
        return name if name == model else f"{name}（{model}）"
    if name:
        return name
    if model:
        return model
    return f"{settings().LLM_MODEL}（全局默认）"


def chat(messages: list[dict], temperature: float | None = None,
         json_mode: bool = False, llm_config: dict | None = None,
         max_tokens: int | None = None) -> str:
    """普通对话。json_mode=True 时请求 JSON 输出。llm_config 覆盖全局配置。"""
    cfg = settings()
    c = llm_config or {}
    api_key = c.get("api_key") or cfg.LLM_API_KEY
    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY（在 .env 或 AI 配置页设置），无法调用大模型")
    kwargs = dict(
        model=c.get("model") or cfg.LLM_MODEL,
        messages=messages,
        temperature=(c.get("temperature") if c.get("temperature") is not None
                     else (cfg.LLM_TEMPERATURE if temperature is None else temperature)),
    )
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _client(llm_config).chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def chat_json(messages: list[dict], temperature: float | None = None,
              llm_config: dict | None = None) -> dict:
    """要求并解析 JSON 输出；失败抛 ValueError。"""
    text = chat(messages, temperature=temperature, json_mode=True, llm_config=llm_config)
    return _parse_json(text)


def chat_multimodal(text: str, images: list[dict], prompt: str = "",
                    llm_config: dict | None = None, max_tokens: int = 6000) -> str:
    """一次调用发「文本 + 多张图片」给多模态模型，返回文本。

    images: [{name, bytes, mime}]；图片转 base64 data URL content block。
    适用：需求文档整篇规范化（docx 全文 + 内嵌图片一起发，模型一次理解）。
    """
    import base64
    content: list = [{"type": "text", "text": text}]
    for img in images:
        b64 = base64.b64encode(img["bytes"]).decode("ascii")
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{img['mime']};base64,{b64}"}})
    messages = [{"role": "user", "content": content}]
    if prompt:
        messages.insert(0, {"role": "system", "content": prompt})
    return chat(messages, llm_config=llm_config, max_tokens=max_tokens)


def _parse_json(text: str) -> dict:
    """容错解析：去代码块围栏 → JSON 对象抽取。"""
    text = text.strip()
    if not text:
        # LLM 偶发返回空 content：明确报错，调用方（skill_engine）会按"LLM 输出异常"自动重试
        raise ValueError("LLM 返回为空，未得到 JSON 输出")
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"LLM 返回不是合法 JSON: {text[:400]}")
        obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("LLM 返回 JSON 不是对象")
    return obj
