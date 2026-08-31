"""接入源：粘贴文本。"""
from __future__ import annotations

from app.connectors.base import ArtifactPayload, Connector


class PasteConnector(Connector):
    kind = "paste"

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        text = params.get("text", "")
        if not text.strip():
            raise ValueError("粘贴内容为空")
        return ArtifactPayload(text=text, text_name=params.get("name", "paste.txt"),
                               ref={"source": "paste"})
