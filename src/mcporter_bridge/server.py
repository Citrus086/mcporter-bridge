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


@app.tool(
    description="""列出可按需激活的大型 MCP。

这些 MCP 配置在 heavy/available 目录中，默认不加载以节省上下文。
使用 mcporter_activate_mcp 激活后才能使用。
"""
)
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


@app.tool(
    description="""激活一个大型 MCP。

大型 MCP 默认不加载以节省上下文。当你需要使用某个 MCP 但发现它不在
mcporter_list_servers 的结果中时，可以用此工具激活它。

激活后需要重新调用 mcporter_list_servers 才能看到新激活的服务器。

参数：
- name: MCP 名称，如 'chrome-devtools'、'playwright' 等

可用的大型 MCP 列表可通过 mcporter_list_heavy_mcps 获取。
"""
)
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


@app.tool(
    description="""停用一个大型 MCP（释放上下文）。

当你使用完某个大型 MCP 后，可以停用它以释放上下文空间。

参数：
- name: MCP 名称，如 'chrome-devtools'、'playwright' 等

注意：停用后该 MCP 的工具将不再可用，直到再次激活。
"""
)
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


@app.tool(description="""向 LLM 介绍 mcporter-bridge 的功能和使用方法。

当你（LLM）不确定如何使用 MCP 工具时，调用此工具获取引导。
这个桥接器连接了 mcporter 管理的所有 MCP 服务器，服务器列表是动态的，
请通过 mcporter_list_servers 自行发现当前可用的服务器。
""")
def mcporter_introduce() -> dict[str, Any]:
    return {
        "ok": True,
        "role": "mcporter-bridge：统一桥接 mcporter 管理的所有 MCP 服务器",
        "important_note": "服务器列表是动态的，不会在此硬编码。请按以下步骤自行发现：",
        "discovery_steps": [
            {
                "step": 1,
                "action": "mcporter_list_servers()",
                "purpose": "发现当前可用的所有 MCP 服务器及其健康状态",
            },
            {
                "step": 2,
                "action": "mcporter_help(server='xxx')",
                "purpose": "查看某服务器的所有工具列表（将 xxx 替换为实际服务器名）",
            },
            {
                "step": 3,
                "action": "mcporter_help(server='xxx', tool='yyy')",
                "purpose": "查看具体工具的参数格式",
            },
            {
                "step": 4,
                "action": "mcporter_call_tool(server_name='xxx', tool_name='yyy', arguments={...})",
                "purpose": "调用工具完成任务",
            },
        ],
        "usage_patterns": [
            {
                "scenario": "浏览器自动化",
                "hint": "查找 playwright 服务器，使用 browser_navigate/browser_click 等工具",
            },
            {
                "scenario": "网页搜索",
                "hint": "查找 web-search-prime 或 exa 服务器",
            },
            {
                "scenario": "文档查询",
                "hint": "查找 context7 服务器，用于查询编程库文档",
            },
            {
                "scenario": "GitHub 操作",
                "hint": "查找 github 服务器，用于仓库、Issue、PR 操作",
            },
            {
                "scenario": "社交媒体",
                "hint": "查找 xiaohongshu、douyin 等服务器",
            },
            {
                "scenario": "图像/视频分析",
                "hint": "查找 zai-mcp-server 服务器",
            },
        ],
        "available_helpers": [
            "mcporter_list_servers - 列出所有服务器",
            "mcporter_help - 查询工具使用方法（支持渐进式查询）",
            "mcporter_inspect_server - 查看服务器详细 schema",
            "mcporter_call_tool - 调用任意工具",
            "mcporter_config_doctor - 检查配置",
            "mcporter_list_heavy_mcps - 列出可按需激活的大型 MCP",
            "mcporter_activate_mcp - 激活一个大型 MCP",
            "mcporter_deactivate_mcp - 停用一个大型 MCP",
            "mcporter_introduce - 显示此介绍",
        ],
        "lazy_loading_note": "大型 MCP（如 chrome-devtools、playwright）默认不加载以节省上下文。"
        "如果需要的 MCP 不在 mcporter_list_servers 结果中，"
        "请先调用 mcporter_list_heavy_mcps 查看，然后用 mcporter_activate_mcp 激活。",
        "reminder": "服务器列表会随用户安装/配置而变化，始终先调用 mcporter_list_servers 获取最新状态",
    }

