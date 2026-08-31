"""接入源：本地上传（文件内容读出，供统一拉取流程使用）。

上传文件本身由 /api/artifacts/upload 落盘；这里提供"从已存工件读取文本"的便捷能力。
"""
from __future__ import annotations

from pathlib import Path

from app.connectors.base import ArtifactPayload, Connector


class LocalFileConnector(Connector):
    kind = "local"

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        path = Path(params.get("path") or cfg.get("path"))
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        return ArtifactPayload(text=path.read_text(encoding="utf-8", errors="ignore"),
                               text_name=path.name, ref={"source": "local", "path": str(path)})
