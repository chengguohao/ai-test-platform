"""连接器：通用 HTTP（轻量兜底，无 MCP Server 时拉任意 REST 自研平台）。

配置示例 cfg:
  { "url": "https://jira.example.com/rest/api/2/issue/{key}",
    "method": "GET",
    "headers": {"Authorization": "Bearer xxxxx"},
    "json_path": "fields.description" }   # 可选：从响应 JSON 取字段
"""
from __future__ import annotations

import json

import httpx

from app.connectors.base import ArtifactPayload, Connector


def _dig(node, path: str):
    if not path:
        return node
    cur = node
    for part in path.replace(".", "/").split("/"):
        part = part.strip()
        if not part:
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            return None
    return cur


class GenericHttpConnector(Connector):
    kind = "http"

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        url = (params.get("url") or cfg.get("url") or "").format(**params)
        method = (params.get("method") or cfg.get("method") or "GET").upper()
        headers = {**(cfg.get("headers") or {}), **(params.get("headers") or {})}
        body = params.get("json") or cfg.get("json")
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.request(method, url, headers=headers, json=body)
            resp.raise_for_status()
        text = resp.text
        json_path = cfg.get("json_path")
        if json_path:
            try:
                node = _dig(resp.json(), json_path)
                text = node if isinstance(node, str) else json.dumps(node, ensure_ascii=False)
            except Exception:
                pass
        return ArtifactPayload(text=text,
                               text_name=params.get("name", "http_content.txt"),
                               ref={"source": "http", "url": url})
