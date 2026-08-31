"""连接器统一接口（fetch=拉取/导入，push=推送/通知）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArtifactPayload:
    """一次拉取的统一返回：原文/结构化/附件/来源引用。"""
    text: str = ""                       # 拉取到的文本（需求/接口/知识库内容）
    text_name: str = "content.txt"       # 文本落盘文件名
    files: list[Path] = field(default_factory=list)  # 附带文件（原样落盘）
    ref: dict = field(default_factory=dict)          # 来源引用（URL/tool/服务名，用于回溯）


class Connector(ABC):
    """所有接入方式的抽象基类。新增自研平台 = 实现本接口并注册（见 __init__.py）。"""

    kind: str = "base"

    @abstractmethod
    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        """拉取/导入外部平台数据 → 工件。cfg 为连接器配置，params 为本次调用参数。"""

    def push(self, cfg: dict, payload: dict) -> dict:
        """推送/通知（如评审邮件）。默认不支持，可覆写。"""
        raise NotImplementedError(f"连接器 {self.kind} 不支持 push")

    def validate_config(self, cfg: dict) -> list[str]:
        """配置校验，返回问题列表（空=通过）。"""
        return []
