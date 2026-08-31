"""自定义连接器示例：演示如何扩展接入任意自研平台。

实现 Connector 接口 → 在 connectors/__init__.py 的 REGISTRY 注册即可在管理界面可选。
（示例从任意 REST 平台拉"新增接口"清单，仅演示结构，可按需改造）
"""
from __future__ import annotations

from app.connectors.base import ArtifactPayload, Connector


class CustomExampleConnector(Connector):
    kind = "custom_example"

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        # 示例：把 params 里的关键信息原样返回，真实场景改为调用自研平台 API
        text = params.get("text", "（自定义连接器示例：请按需实现 fetch 逻辑）")
        return ArtifactPayload(text=text,
                               text_name=params.get("name", "custom.txt"),
                               ref={"source": self.kind})
