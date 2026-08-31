"""接入源：URL 抓取（Swagger/OpenAPI、公开知识库页等）。"""
from __future__ import annotations

import httpx

from app.connectors.base import ArtifactPayload, Connector
from app.config import settings


class UrlFetchConnector(Connector):
    kind = "url_fetch"

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        url = params.get("url") or cfg.get("url")
        if not url:
            raise ValueError("缺少 URL")
        timeout = int(cfg.get("timeout", settings().LLM_TIMEOUT))
        proxy = cfg.get("proxy") or settings().LLM_PROXY or None
        with httpx.Client(timeout=timeout, proxy=proxy, follow_redirects=True) as client:
            resp = client.get(url, headers={"Accept": "application/json, text/plain, */*"})
            resp.raise_for_status()
        text = resp.text
        name = params.get("name") or url.rstrip("/").split("/")[-1] or "url_content.txt"
        if not name.lower().endswith((".json", ".yaml", ".yml", ".txt", ".md")):
            name = name + ".txt"
        return ArtifactPayload(text=text, text_name=name, ref={"source": "url_fetch", "url": url})
