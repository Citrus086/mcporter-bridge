from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

APP_NAME = "mcporter-bridge"
DEFAULT_TIMEOUT_MS = 60_000
MAX_OUTPUT_CHARS = int(os.getenv("MCPORTER_BRIDGE_MAX_OUTPUT_CHARS", "40000"))
KNOWN_BINARIES = {
    "mcporter": [
        Path("/opt/homebrew/bin/mcporter"),
        Path("/usr/local/bin/mcporter"),
    ],
    "agent-reach": [
        Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/agent-reach"),
        Path("/opt/homebrew/bin/agent-reach"),
        Path("/usr/local/bin/agent-reach"),
    ],
}
BINARY_ENV_VARS = {
    "mcporter": "MCPORTER_BRIDGE_MCPORTER_BIN",
    "agent-reach": "MCPORTER_BRIDGE_AGENT_REACH_BIN",
}

app = FastMCP(APP_NAME)


def _resolve_binary(name: str) -> str:
    env_var = BINARY_ENV_VARS.get(name)
    if env_var:
        override = os.getenv(env_var)
        if override:
            return override

    path = shutil.which(name)
    if path:
        return path

    for candidate in KNOWN_BINARIES.get(name, []):
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(f"Required binary not found: {name}")


def _normalize_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    omitted = len(text) - MAX_OUTPUT_CHARS
    return f"{text[:MAX_OUTPUT_CHARS]}\n\n... truncated {omitted} characters ..."


def _maybe_parse_json(text: str) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _command_not_found_result(binary_name: str, command: list[str], timeout_ms: int) -> dict[str, Any]:
    return {
        "ok": False,
        "timed_out": False,
        "command": command,
        "timeout_ms": timeout_ms,
        "returncode": None,
        "stdout": "",
        "stderr": f"Required binary not found: {binary_name}",
        "parsed_json": None,
    }


def _run_command(command: list[str], *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_ms / 1000,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timed_out": True,
            "command": command,
            "timeout_ms": timeout_ms,
            "returncode": None,
            "stdout": _truncate(_normalize_text(exc.stdout)),
            "stderr": _truncate(_normalize_text(exc.stderr)),
            "parsed_json": None,
        }
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "timed_out": False,
            "command": command,
            "timeout_ms": timeout_ms,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "parsed_json": None,
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    parsed_json = _maybe_parse_json(stdout)
    return {
        "ok": completed.returncode == 0,
        "timed_out": False,
        "command": command,
        "timeout_ms": timeout_ms,
        "returncode": completed.returncode,
        "stdout": _truncate(stdout),
        "stderr": _truncate(stderr),
        "parsed_json": parsed_json,
    }


def _run_binary_command(
    binary_name: str,
    args: list[str],
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    try:
        binary = _resolve_binary(binary_name)
    except FileNotFoundError:
        return _command_not_found_result(binary_name, [binary_name, *args], timeout_ms)
    return _run_command([binary, *args], timeout_ms=timeout_ms)


@app.tool(description="List all servers visible to the local mcporter registry, including health and optionally sources.")
def mcporter_list_servers(
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    include_sources: bool = False,
) -> dict[str, Any]:
    args = ["list", "--json"]
    if include_sources:
        args.append("--sources")
    return _run_binary_command("mcporter", args, timeout_ms=timeout_ms)


USAGE_GUIDE = """
# mcporter-bridge 使用指南

## 概述

mcporter-bridge 让你能访问 mcporter 管理的所有 MCP 服务器（如小红书、抖音等）。

## 推荐工作流程

1. **查看可用服务器** → `mcporter_list_servers`
2. **查询工具参数** → `mcporter_help(server="xiaohongshu")` 或 `mcporter_help(server="xiaohongshu", tool="search_feeds")`
3. **调用工具** → `mcporter_call_tool(server_name="xiaohongshu", tool_name="search_feeds", arguments={"keyword": "搜索内容"})`

## 工具列表

| 工具 | 用途 |
|------|------|
| `mcporter_list_servers` | 列出所有可用服务器 |
| `mcporter_help` | 查询工具使用方法和参数格式（本工具） |
| `mcporter_inspect_server` | 查看服务器的详细工具 schema |
| `mcporter_call_tool` | 调用指定服务器的工具 |
| `mcporter_get_server` | 获取服务器配置信息 |
| `mcporter_config_doctor` | 检查配置是否正确 |
| `mcporter_version` | 查看 mcporter 版本 |

## 常见错误

❌ arguments 传字符串：`arguments: '{"key": "value"}'`
✅ arguments 传对象：`arguments: {"key": "value"}`

❌ 参数名错误：`server_name` 写成 `server`
✅ 使用正确的参数名

## 示例：搜索小红书

```
1. mcporter_help(server="xiaohongshu")  # 查看可用工具
2. mcporter_help(server="xiaohongshu", tool="search_feeds")  # 查看参数格式
3. mcporter_call_tool(
     server_name="xiaohongshu",
     tool_name="search_feeds",
     arguments={"keyword": "GLM"}
   )
```
"""


@app.tool(
    description="""查询 mcporter 工具的使用方法和参数格式。

在调用 `mcporter_call_tool` 之前，建议先用本工具查询参数格式，避免参数错误。

参数说明：
- 不传参数：返回完整使用指南
- 只传 server：返回该服务器的所有工具列表
- 传 server + tool：返回该工具的详细参数说明

示例：
- `mcporter_help()` → 返回使用指南
- `mcporter_help(server="xiaohongshu")` → 列出小红书所有工具
- `mcporter_help(server="xiaohongshu", tool="search_feeds")` → 查看搜索工具的参数
"""
)
def mcporter_help(
    server: str | None = None,
    tool: str | None = None,
) -> dict[str, Any]:
    """查询 mcporter 工具使用方法。"""
    # 如果没有参数，返回使用指南
    if server is None:
        return {
            "ok": True,
            "type": "usage_guide",
            "content": USAGE_GUIDE.strip(),
        }

    # 如果只有 server，查询该服务器的工具列表
    if tool is None:
        result = _run_binary_command(
            "mcporter",
            ["list", server, "--json"],
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )
        if result.get("ok") and result.get("parsed_json"):
            tools = result["parsed_json"].get("tools", [])
            tool_list = []
            for t in tools:
                tool_list.append({
                    "name": t.get("name"),
                    "description": t.get("description", "")[:200],  # 截断描述
                })
            return {
                "ok": True,
                "type": "server_tools",
                "server": server,
                "tools": tool_list,
                "hint": f"使用 mcporter_help(server='{server}', tool='工具名') 查看具体工具的参数格式",
            }
        return result

    # 如果有 server 和 tool，查询该工具的详细参数
    result = _run_binary_command(
        "mcporter",
        ["list", server, "--json"],
        timeout_ms=DEFAULT_TIMEOUT_MS,
    )

    if not result.get("ok") or not result.get("parsed_json"):
        return result

    tools = result["parsed_json"].get("tools", [])
    target_tool = None
    for t in tools:
        if t.get("name") == tool:
            target_tool = t
            break

    if not target_tool:
        return {
            "ok": False,
            "error": f"Tool '{tool}' not found in server '{server}'",
            "available_tools": [t.get("name") for t in tools],
        }

    # 提取并格式化参数信息
    input_schema = target_tool.get("inputSchema", {})
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    params_info = []
    for param_name, param_info in properties.items():
        params_info.append({
            "name": param_name,
            "type": param_info.get("type", "unknown"),
            "required": param_name in required,
            "description": param_info.get("description", ""),
            "default": param_info.get("default"),
        })

    return {
        "ok": True,
        "type": "tool_schema",
        "server": server,
        "tool": tool,
        "description": target_tool.get("description", ""),
        "parameters": params_info,
        "required_params": required,
        "example_usage": {
            "server_name": server,
            "tool_name": tool,
            "arguments": {p["name"]: f"<{p['type']}>" for p in params_info if p["required"]},
        },
    }


@app.tool(description="Read one server definition from the local mcporter registry.")
def mcporter_get_server(
    server_name: str,
    timeout_ms: int = 10_000,
) -> dict[str, Any]:
    return _run_binary_command(
        "mcporter",
        ["config", "get", server_name, "--json"],
        timeout_ms=timeout_ms,
    )


@app.tool(description="Inspect one configured MCP server through mcporter and return its tool schemas plus runtime health.")
def mcporter_inspect_server(
    server_name: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    return _run_binary_command(
        "mcporter",
        ["list", server_name, "--json"],
        timeout_ms=timeout_ms,
    )


@app.tool(
    description="""Call any tool on a configured mcporter server.

## 使用流程（重要！）

1. **先查询可用服务器**：调用 `mcporter_list_servers` 查看所有服务器
2. **查询工具参数格式**：调用 `mcporter_help` 或 `mcporter_inspect_server` 获取参数 schema
3. **调用工具**：使用正确的参数格式调用本工具

## 参数格式说明

- `server_name`: 服务器名称，如 `xiaohongshu`、`douyin`
- `tool_name`: 工具名称，如 `search_feeds`、`get_feed_detail`
- `arguments`: JSON 对象格式的参数，**不是字符串**

## arguments 参数示例

正确格式（JSON 对象）：
```json
{"keyword": "GLM 乱码", "filters": {"sort_by": "最新"}}
```

错误格式（不要这样用）：
- `'{"keyword": "test"}'` ← 不要传字符串
- `"keyword=GLM"` ← 不要用 key=value 格式

## 完整调用示例

搜索小红书内容：
- server_name: "xiaohongshu"
- tool_name: "search_feeds"
- arguments: {"keyword": "搜索关键词"}

获取笔记详情：
- server_name: "xiaohongshu"
- tool_name: "get_feed_detail"
- arguments: {"feed_id": "xxx", "xsec_token": "yyy"}
"""
)
def mcporter_call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    output_format: Literal["json", "text", "markdown", "raw"] = "json",
) -> dict[str, Any]:
    args = ["call", f"{server_name}.{tool_name}", "--output", output_format]
    if arguments is not None:
        args.extend(["--args", json.dumps(arguments, ensure_ascii=False)])
    return _run_binary_command("mcporter", args, timeout_ms=timeout_ms)


@app.tool(description="Run `mcporter config doctor` and return the current config validation report.")
def mcporter_config_doctor(
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    return _run_binary_command("mcporter", ["config", "doctor"], timeout_ms=timeout_ms)


@app.tool(description="Return the local mcporter CLI version.")
def mcporter_version() -> dict[str, Any]:
    return _run_binary_command("mcporter", ["--version"], timeout_ms=5_000)


@app.tool(description="Run `agent-reach doctor` and return the local Agent Reach health report.")
def agent_reach_doctor(
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    return _run_binary_command("agent-reach", ["doctor"], timeout_ms=timeout_ms)


@app.tool(description="Run `agent-reach watch` for a quick health plus update check.")
def agent_reach_watch(
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    return _run_binary_command("agent-reach", ["watch"], timeout_ms=timeout_ms)


@app.tool(description="Return the local Agent Reach CLI version.")
def agent_reach_version() -> dict[str, Any]:
    return _run_binary_command("agent-reach", ["version"], timeout_ms=5_000)

