"""Async MCP client wrapper used by agents.

The default transport is an in-process MCP tool registry so local tests and
offline demos remain reliable. When `MCP_TRANSPORT=stdio` and the MCP SDK is
installed, the same wrapper calls the local MCP server over the MCP protocol.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from threading import Thread
from typing import Any

from backend.config import settings
from backend.errors import UpstreamFetchError
from backend.mcp.github_mock import PRData
from backend.mcp.models import MCPToolCallRecord
from backend.observability.logger import log_structured
from backend.observability.metrics import record_mcp_tool_call


class GitHubMCPClient:
    def __init__(self, *, transport: str | None = None) -> None:
        self.transport = (transport or settings.mcp_transport).strip().lower()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started_at = time.perf_counter()
        status = "completed"
        try:
            if self.transport == "stdio":
                result = await self._call_tool_stdio(tool_name, arguments)
            else:
                result = await self._call_tool_inprocess(tool_name, arguments)
            return result
        except Exception as exc:
            status = "error"
            if isinstance(exc, UpstreamFetchError):
                raise
            raise UpstreamFetchError(
                f"MCP tool '{tool_name}' failed: {exc}",
                status_code=502,
                code="mcp_tool_failed",
                details={"tool": tool_name, "transport": self.transport},
            ) from exc
        finally:
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            record_mcp_tool_call(tool_name, latency_ms, status=status, transport=self.transport)
            log_structured(
                "INFO" if status == "completed" else "ERROR",
                "mcp_tool_call",
                tool=tool_name,
                transport=self.transport,
                status=status,
                latency_ms=latency_ms,
            )

    async def _call_tool_inprocess(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from backend.mcp_server.github_tools import (
            get_pull_request_diff_impl,
            get_pull_request_impl,
        )

        if tool_name == "get_pull_request":
            return get_pull_request_impl(str(arguments.get("pr_url", "")))
        if tool_name == "get_pull_request_diff":
            return get_pull_request_diff_impl(str(arguments.get("pr_url", "")))
        raise ValueError(f"Unknown MCP tool: {tool_name}")

    async def _call_tool_stdio(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:  # pragma: no cover - requires optional SDK.
            raise RuntimeError("MCP SDK is not installed; use MCP_TRANSPORT=inprocess locally.") from exc

        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "backend.mcp_server.github_tools"],
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
                if isinstance(structured, dict):
                    return structured
                content = getattr(result, "content", [])
                if content:
                    text = getattr(content[0], "text", "")
                    if text:
                        return json.loads(text)
                raise RuntimeError(f"MCP tool '{tool_name}' returned no structured content")

    async def get_pr_data(self, pr_url: str) -> tuple[PRData, list[MCPToolCallRecord]]:
        records: list[MCPToolCallRecord] = []
        metadata_started = time.perf_counter()
        metadata = await self.call_tool("get_pull_request", {"pr_url": pr_url})
        records.append(
            MCPToolCallRecord(
                tool="get_pull_request",
                transport=self.transport,
                latency_ms=round((time.perf_counter() - metadata_started) * 1000, 2),
                status="completed",
            )
        )
        diff_started = time.perf_counter()
        diff_payload = await self.call_tool("get_pull_request_diff", {"pr_url": pr_url})
        records.append(
            MCPToolCallRecord(
                tool="get_pull_request_diff",
                transport=self.transport,
                latency_ms=round((time.perf_counter() - diff_started) * 1000, 2),
                status="completed",
            )
        )
        return (
            PRData(
                url=str(metadata.get("url", pr_url)),
                title=str(metadata.get("title", "")),
                author=str(metadata.get("author", "unknown")),
                base_branch=str(metadata.get("base_branch", "main")),
                head_branch=str(metadata.get("head_branch", "feature")),
                files_changed=[str(item) for item in metadata.get("files_changed", [])],
                language=str(metadata.get("language", "Unknown")),
                diff=str(diff_payload.get("diff", "")),
            ),
            records,
        )

    def get_pr_data_sync(self, pr_url: str) -> tuple[PRData, list[MCPToolCallRecord]]:
        return _run_async(self.get_pr_data(pr_url))


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive.
            error["value"] = exc

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return result["value"]


github_mcp_client = GitHubMCPClient()
