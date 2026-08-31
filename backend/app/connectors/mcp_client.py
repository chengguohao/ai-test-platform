"""连接器：MCP（对齐业界 agent，注册外部自研平台取实据）。

MCP Server 通过命令（stdio 传输）注册，AI 生成时调用其 tools 拉取真实数据。
MCP Python SDK 是纯 async 的：这里统一用 asyncio.run 包一层，供同步 FastAPI
路由（threadpool 执行）安全调用。未安装 mcp 或未配置 Server 时给出明确提示。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.connectors.base import ArtifactPayload, Connector


def _run_async(coro) -> Any:
    """在同步上下文里执行 async 协程（FastAPI sync 路由跑在 threadpool，安全）。"""
    return asyncio.run(coro)


async def _list_tools_async(cfg: dict) -> list[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command, args = _split_command(cfg)
    params = StdioServerParameters(command=command, args=args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [{"name": t.name, "description": t.description} for t in tools.tools]


async def _call_tool_async(cfg: dict, tool_name: str, args: dict) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command, cmd_args = _split_command(cfg)
    params = StdioServerParameters(command=command, args=cmd_args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            parts = []
            for item in result.content:
                text = getattr(item, "text", None)
                parts.append(str(text) if text is not None
                             else json.dumps(item, default=str, ensure_ascii=False))
            return "\n".join(parts) or str(result)


def _split_command(cfg: dict) -> tuple[str, list[str]]:
    command = cfg.get("command")
    if not command:
        raise ValueError("MCP 连接器未配置 command（如 npx / python 脚本）")
    parts = command.split()
    return parts[0], parts[1:]


class McpConnector(Connector):
    kind = "mcp"

    def validate_config(self, cfg: dict) -> list[str]:
        errs = []
        if not (cfg.get("command") or cfg.get("servers")):
            errs.append("缺少 MCP Server 命令（stdio）或 servers 列表")
        return errs

    def list_tools(self, cfg: dict) -> list[dict]:
        """列出 MCP Server 暴露的 tools（供前端选择与展示）。"""
        try:
            import mcp  # noqa: F401
        except ImportError:
            return [{"error": "mcp 未安装，请执行: pip install mcp"}]
        try:
            return _run_async(_list_tools_async(cfg))
        except Exception as e:  # noqa: BLE001
            return [{"error": f"连接 MCP Server 失败: {e}"}]

    def call_tool(self, cfg: dict, tool_name: str, args: dict) -> str:
        try:
            import mcp  # noqa: F401
        except ImportError as e:
            raise RuntimeError("mcp 未安装，请执行: pip install mcp") from e
        return _run_async(_call_tool_async(cfg, tool_name, args))

    def fetch(self, cfg: dict, params: dict) -> ArtifactPayload:
        tool = params.get("tool")
        if not tool:
            raise ValueError("缺少要调用的 MCP tool 名称")
        args = params.get("args") or {}
        text = self.call_tool(cfg, tool, args)
        name = params.get("name") or f"mcp_{tool}.txt"
        return ArtifactPayload(text=text, text_name=name,
                               ref={"source": "mcp", "tool": tool, "args": args})
