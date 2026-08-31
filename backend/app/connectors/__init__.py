"""连接器包：自由接入自研平台（优先 MCP，可插拔）。

注册新连接器 = 在此 REGISTRY 里登记子类，即可在「连接器设置」页使用。
"""
from __future__ import annotations

from app.connectors.base import ArtifactPayload, Connector  # noqa: F401 重导出
from app.connectors.generic_http import GenericHttpConnector
from app.connectors.local_file import LocalFileConnector
from app.connectors.mcp_client import McpConnector
from app.connectors.paste import PasteConnector
from app.connectors.smtp_mail import SmtpMailConnector
from app.connectors.url_fetch import UrlFetchConnector

# 内置连接器注册表；自定义连接器（custom_example 等）在此追加即可
REGISTRY: dict[str, type[Connector]] = {
    cls.kind: cls for cls in (
        LocalFileConnector, PasteConnector, UrlFetchConnector,
        GenericHttpConnector, SmtpMailConnector, McpConnector,
    )
}


def get_connector(kind: str) -> Connector:
    if kind not in REGISTRY:
        raise ValueError(f"未注册的连接器类型: {kind}，可选: {sorted(REGISTRY)}")
    return REGISTRY[kind]()
