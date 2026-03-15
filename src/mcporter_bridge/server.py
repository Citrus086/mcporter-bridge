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
## 工作流程
1. `mcporter_list_servers()` → 查看可用服务器
2. `mcporter_help(server="xxx")` → 查看工具列表
3. `mcporter_help(server="xxx", tool="yyy")` → 查看参数格式
4. `mcporter_call_tool(server_name="xxx", tool_name="yyy", arguments={...})` → 调用

## 常见错误
- ❌ `arguments: '{"key": "val"}'` → 字符串
- ✅ `arguments: {"key": "val"}` → 对象
"""


@app.tool(
    description="""查询工具使用方法。

参数：
- 不传参数：返回使用指南
- 只传 server：返回该服务器的工具列表
- 传 server + tool：返回工具的参数格式

示例：`mcporter_help(server="xiaohongshu", tool="search_feeds")`
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
    description="""调用指定服务器的工具。

参数：
- server_name: 服务器名（如 xiaohongshu、douyin）
- tool_name: 工具名（如 search_feeds）
- arguments: JSON 对象，**不是字符串**

示例：`mcporter_call_tool(server_name="xiaohongshu", tool_name="search_feeds", arguments={"keyword": "GLM"})`

⚠️ 先用 mcporter_help 查询参数格式
"""
)
def mcporter_call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    output_format: Literal["json", "text", "markdown", "raw"] = "json",
) -> dict[str, Any]:
    # 兼容处理：某些 MCP 客户端会把嵌套的 arguments 对象序列化成字符串
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "error": f"arguments is a string but not valid JSON: {e}",
                "received_arguments": arguments[:200] if len(arguments) > 200 else arguments,
            }
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


@app.tool(description="列出可按需激活的大型 MCP（默认不加载以节省上下文）。")
def mcporter_list_heavy_mcps() -> dict[str, Any]:
    """列出可用但未激活的大型 MCP。"""
    heavy_dir = Path.home() / ".mcporter" / "heavy" / "available"
    active_dir = Path.home() / ".mcporter" / "heavy" / "active"

    available = []
    if heavy_dir.exists():
        for f in heavy_dir.glob("*.json"):
            name = f.stem
            # 读取配置获取描述信息
            try:
                config = json.loads(f.read_text())
                servers = config.get("mcpServers", {})
                server_count = len(servers)
                server_names = list(servers.keys())
            except Exception:
                server_count = 0
                server_names = []

            available.append({
                "name": name,
                "server_count": server_count,
                "servers": server_names,
            })

    active = []
    if active_dir.exists():
        for f in active_dir.iterdir():
            if f.is_symlink() or f.suffix == ".json":
                active.append(f.stem if f.suffix == ".json" else f.name)

    return {
        "ok": True,
        "available": available,
        "active": active,
        "hint": "使用 mcporter_activate_mcp('名称') 激活，使用 mcporter_deactivate_mcp('名称') 停用",
    }


@app.tool(description="激活一个大型 MCP。激活后用 mcporter_list_servers 确认。参数：name 如 'chrome-devtools'")
def mcporter_activate_mcp(name: str, timeout_ms: int = 10_000) -> dict[str, Any]:
    """激活一个大型 MCP。"""
    toggle_script = Path.home() / ".mcporter" / "mcp-toggle.sh"

    if not toggle_script.exists():
        return {
            "ok": False,
            "error": "mcp-toggle.sh 脚本不存在，请先配置按需加载系统",
            "hint": "运行以下命令创建：\nmkdir -p ~/.mcporter/heavy/available",
        }

    result = _run_command(
        [str(toggle_script), "activate", name],
        timeout_ms=timeout_ms,
    )

    if result.get("ok") and "已激活" in result.get("stdout", ""):
        return {
            "ok": True,
            "name": name,
            "message": f"已激活 {name}，请调用 mcporter_list_servers 查看更新后的服务器列表",
            "hint": "使用完毕后可调用 mcporter_deactivate_mcp 停用以释放上下文",
        }

    return {
        "ok": False,
        "name": name,
        "error": result.get("stderr") or result.get("stdout"),
        "hint": "检查名称是否正确，可用 mcporter_list_heavy_mcps 查看列表",
    }


@app.tool(description="停用一个大型 MCP（释放上下文）。参数：name 如 'chrome-devtools'")
def mcporter_deactivate_mcp(name: str, timeout_ms: int = 10_000) -> dict[str, Any]:
    """停用一个大型 MCP。"""
    toggle_script = Path.home() / ".mcporter" / "mcp-toggle.sh"

    if not toggle_script.exists():
        return {
            "ok": False,
            "error": "mcp-toggle.sh 脚本不存在",
        }

    result = _run_command(
        [str(toggle_script), "deactivate", name],
        timeout_ms=timeout_ms,
    )

    if result.get("ok") and "已停用" in result.get("stdout", ""):
        return {
            "ok": True,
            "name": name,
            "message": f"已停用 {name}",
        }

    return {
        "ok": False,
        "name": name,
        "error": result.get("stderr") or result.get("stdout"),
    }


@app.tool(description="获取 mcporter-bridge 的使用说明和工具列表。")
def mcporter_introduce() -> dict[str, Any]:
    return {
        "role": "mcporter-bridge：统一桥接 mcporter 管理的所有 MCP 服务器",
        "workflow": [
            "1. mcporter_list_servers() - 查看可用服务器",
            "2. mcporter_help(server='xxx') - 查看工具列表",
            "3. mcporter_call_tool(server_name='xxx', tool_name='yyy', arguments={...}) - 调用",
        ],
        "lazy_loading": "如果需要的 MCP 不在列表中，用 mcporter_list_heavy_mcps 查看可激活的大型 MCP",
        "tools": [
            "mcporter_list_servers / mcporter_help / mcporter_call_tool",
            "mcporter_list_heavy_mcps / mcporter_activate_mcp / mcporter_deactivate_mcp",
        ],
    }

