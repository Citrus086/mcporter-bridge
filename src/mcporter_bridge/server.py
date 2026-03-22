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

# 内置常见 MCP 描述（当用户没有配置时使用）
BUILTIN_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "exa": {"description": "AI 搜索引擎", "tags": ["搜索", "网页", "代码", "新闻"], "best_for": "搜索网页内容、代码、新闻"},
    "xiaohongshu": {"description": "小红书操作", "tags": ["小红书", "笔记", "社交媒体"], "best_for": "搜索/发布小红书笔记"},
    "douyin": {"description": "抖音操作", "tags": ["抖音", "视频", "短视频"], "best_for": "解析抖音视频、下载无水印视频"},
    "web-search-prime": {"description": "智谱网页搜索", "tags": ["搜索", "网页"], "best_for": "搜索中文网页内容"},
    "web-reader": {"description": "网页阅读器", "tags": ["网页", "阅读", "解析"], "best_for": "读取并解析网页内容"},
    "context7": {"description": "技术文档查询", "tags": ["文档", "代码", "API"], "best_for": "查询编程库的官方文档"},
    "zread": {"description": "GitHub 仓库阅读", "tags": ["GitHub", "代码", "仓库"], "best_for": "搜索/阅读 GitHub 仓库内容"},
    "zai-mcp-server": {"description": "Z.AI 多模态工具", "tags": ["图像", "视频", "分析"], "best_for": "图像分析、视频分析、OCR"},
    "bosszhipin": {"description": "Boss 直聘操作", "tags": ["招聘", "求职", "简历"], "best_for": "搜索职位、投递简历"},
    "notion": {"description": "Notion 笔记操作", "tags": ["笔记", "文档", "协作"], "best_for": "读写 Notion 页面"},
    "figma": {"description": "Figma 设计工具", "tags": ["设计", "UI", "原型"], "best_for": "读取 Figma 设计稿"},
    "github": {"description": "GitHub 官方 MCP (Docker 本地版)", "tags": ["GitHub", "代码", "仓库", "协作", "Issues", "PR"], "best_for": "代码搜索、仓库管理、Issues/PRs、文件操作 (响应快~2s)"},
    "linkedin-scraper": {"description": "LinkedIn 数据抓取", "tags": ["LinkedIn", "职场", "招聘", "人脉"], "best_for": "获取个人/公司资料、搜索职位和人才"},
    "wechat-article": {"description": "微信文章处理", "tags": ["微信", "公众号", "文章"], "best_for": "转换微信文章格式"},
}

# 名字猜测规则（用于未知 MCP）
NAME_HINTS: dict[str, str] = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "search": "搜索",
    "reader": "阅读器",
    "browser": "浏览器",
    "chrome": "Chrome 浏览器",
    "github": "GitHub",
    "git": "Git",
    "notion": "Notion 笔记",
    "figma": "Figma 设计",
    "slack": "Slack 通讯",
    "telegram": "Telegram",
    "feishu": "飞书",
    "wechat": "微信",
    "zhihu": "知乎",
    "weibo": "微博",
    "bilibili": "B站",
    "youtube": "YouTube",
    "twitter": "Twitter/X",
}

KNOWN_BINARIES = {
    "mcporter": [
        Path("/opt/homebrew/bin/mcporter"),
        Path("/usr/local/bin/mcporter"),
    ],
}
BINARY_ENV_VARS = {
    "mcporter": "MCPORTER_BRIDGE_MCPORTER_BIN",
}

app = FastMCP(APP_NAME)


def _get_mcporter_config_path() -> Path:
    """获取 mcporter 配置文件路径"""
    return Path.home() / ".mcporter" / "mcporter.json"


def _load_user_server_descriptions() -> dict[str, dict[str, Any]]:
    """从 mcporter.json 加载用户配置的服务器描述"""
    config_path = _get_mcporter_config_path()
    if not config_path.exists():
        return {}

    try:
        config = json.loads(config_path.read_text())
        servers = config.get("mcpServers", {})
        descriptions = {}
        for name, cfg in servers.items():
            if isinstance(cfg, dict) and ("description" in cfg or "tags" in cfg or "best_for" in cfg):
                descriptions[name] = {
                    "description": cfg.get("description", ""),
                    "tags": cfg.get("tags", []),
                    "best_for": cfg.get("best_for", ""),
                }
        return descriptions
    except Exception:
        return {}


def _infer_description_from_name(name: str) -> dict[str, Any]:
    """从服务器名称推断功能描述"""
    name_lower = name.lower()
    for keyword, hint in NAME_HINTS.items():
        if keyword in name_lower:
            return {
                "description": f"{hint}相关工具",
                "tags": [hint],
                "best_for": f"操作{hint}",
                "inferred": True,
            }
    return {
        "description": "未知服务",
        "tags": [],
        "best_for": "查看工具列表了解详情",
        "inferred": True,
    }


def _get_server_capabilities(name: str, user_descriptions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """获取服务器的功能描述（用户配置 > 内置 > 名字推断）"""
    # 1. 用户配置优先
    if name in user_descriptions:
        result = user_descriptions[name].copy()
        result["source"] = "user_config"
        return result

    # 2. 内置描述
    if name in BUILTIN_DESCRIPTIONS:
        result = BUILTIN_DESCRIPTIONS[name].copy()
        result["source"] = "builtin"
        return result

    # 3. 名字推断
    result = _infer_description_from_name(name)
    result["source"] = "inferred"
    return result


# 定义哪些是大型 MCP（tool_count 超过此阈值或在此列表中）
HEAVY_MCP_NAMES = {"playwright", "chrome-devtools"}
HEAVY_MCP_THRESHOLD = 15


def _get_heavy_mcps() -> list[dict[str, Any]]:
    """获取可激活的大型 MCP 列表"""
    heavy_dir = Path.home() / ".mcporter" / "heavy" / "available"
    active_dir = Path.home() / ".mcporter" / "heavy" / "active"

    # 获取当前已激活的 heavy MCP 名称
    active_names = set()
    if active_dir.exists():
        for f in active_dir.iterdir():
            if f.is_symlink() or f.suffix == ".json":
                active_names.add(f.stem if f.suffix == ".json" else f.name)

    available = []
    if heavy_dir.exists():
        for f in heavy_dir.glob("*.json"):
            name = f.stem
            # 已激活的不在 available 里显示
            if name in active_names:
                continue

            # 读取配置获取描述信息
            try:
                config = json.loads(f.read_text())
                servers = config.get("mcpServers", {})
                server_count = len(servers)
                server_names = list(servers.keys())

                # 获取描述信息
                for srv_name, srv_cfg in servers.items():
                    if isinstance(srv_cfg, dict):
                        description = srv_cfg.get("description", "")
                        tags = srv_cfg.get("tags", [])
                        best_for = srv_cfg.get("best_for", "")
                        break
                else:
                    description = ""
                    tags = []
                    best_for = ""

            except Exception:
                server_count = 0
                server_names = []
                description = ""
                tags = []
                best_for = ""

            available.append({
                "name": name,
                "type": "heavy",
                "description": description,
                "tags": tags,
                "best_for": best_for,
                "server_count": server_count,
                "servers": server_names,
            })

    return available


def _is_heavy_mcp(name: str, tool_count: int) -> bool:
    """判断是否是大型 MCP"""
    return name in HEAVY_MCP_NAMES or tool_count > HEAVY_MCP_THRESHOLD


def _get_servers_with_capabilities(include_tools: bool = True) -> list[dict[str, Any]]:
    """获取所有服务器及其功能描述"""
    # 调用 mcporter list 获取服务器列表
    result = _run_binary_command("mcporter", ["list", "--json"], timeout_ms=DEFAULT_TIMEOUT_MS)

    if not result.get("ok") or not result.get("parsed_json"):
        return []

    servers_data = result["parsed_json"].get("servers", [])
    user_descriptions = _load_user_server_descriptions()

    servers = []
    for server_info in servers_data:
        name = server_info.get("name", "unknown")
        capabilities = _get_server_capabilities(name, user_descriptions)
        tools = server_info.get("tools", [])
        tool_count = len(tools)

        # 判断类型
        mcp_type = "heavy" if _is_heavy_mcp(name, tool_count) else "small"

        server_entry = {
            "name": name,
            "type": mcp_type,
            "status": server_info.get("status", "unknown"),
            "description": capabilities.get("description", ""),
            "tags": capabilities.get("tags", []),
            "best_for": capabilities.get("best_for", ""),
        }

        if include_tools:
            server_entry["tools"] = [t.get("name") for t in tools if t.get("name")]
            server_entry["tool_count"] = tool_count

        servers.append(server_entry)

    return servers


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


@app.tool(
    description="""【MCP 全景】列出所有已加载和可激活的 MCP 服务器。

返回分区：
- active: 当前已加载的 MCP（可直接调用）
- available: 未加载但可激活的大型 MCP

工具分类概览：
- 搜索类：智谱网页搜索、Exa AI 搜索
- 社交类：小红书、抖音平台操作
- 开发类：GitHub 仓库阅读(zread)、技术文档查询(context7)
- 职场类：Boss 直聘、LinkedIn 招聘求职
- 多模态：图像分析、视频分析、OCR
- 协作类：Notion、Figma 读写
- 网页阅读：解析网页内容

注：实际可用 MCP 以调用结果为准，本列表仅为示例

⚠️ 大型 MCP 占用大量上下文，请遵循：按需激活 → 用完即释放

使用流程：
1. 调用本工具查看 active.servers 找需要的 MCP
2. 大型 MCP 需先 mcporter_activate_mcp(name="xxx") 激活
3. 用 mcporter_call_tool 调用具体工具
4. 用完立即 mcporter_deactivate_mcp(name="xxx") 释放上下文"""
)
def mcporter_list_servers(
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    include_available: bool = True,
) -> dict[str, Any]:
    # 获取已加载的 MCP
    active_servers = _get_servers_with_capabilities(include_tools=True)

    # 分区统计
    small_active = [s for s in active_servers if s.get("type") == "small"]
    heavy_active = [s for s in active_servers if s.get("type") == "heavy"]

    ok_count = sum(1 for s in active_servers if s.get("status") == "ok")
    auth_count = sum(1 for s in active_servers if s.get("status") == "auth")
    offline_count = sum(1 for s in active_servers if s.get("status") in ("offline", "error"))

    result = {
        "ok": True,
        "active": {
            "total": len(active_servers),
            "small_count": len(small_active),
            "heavy_count": len(heavy_active),
            "status_summary": {
                "online": ok_count,
                "auth_required": auth_count,
                "offline": offline_count,
            },
            "servers": active_servers,
        },
    }

    # 添加可激活的大型 MCP
    if include_available:
        available = _get_heavy_mcps()
        result["available"] = {
            "total": len(available),
            "servers": available,
        }
        if available:
            result["_lazy_loading_hint"] = f"有 {len(available)} 个大型 MCP 可激活，使用 mcporter_activate_mcp(name='xxx') 激活需要的"

    result["_workflow"] = "1. 查看 active.servers 找需要的 MCP → 2. 如有需要激活 available 中的 → 3. mcporter_call_tool 执行"

    return result


USAGE_GUIDE = """## 使用流程
1. mcporter_list_servers() → 查看可用 MCP 及其类型(small/heavy)
2. mcporter_help(server="xxx") → 查看某 MCP 的工具列表
3. mcporter_help(server="xxx", tool="yyy") → 查看参数格式
4. mcporter_call_tool(server_name="xxx", tool_name="yyy", arguments={...}) → 调用

## 大型 MCP 管理
- 查看可激活：mcporter_list_servers().available
- 激活：mcporter_activate_mcp(name="xxx")
- 用完释放：mcporter_deactivate_mcp(name="xxx")

## 常见错误
- ❌ arguments: '{"key": "val"}' → 字符串
- ✅ arguments: {"key": "val"} → JSON 对象"""


@app.tool(
    description="""探索 MCP 服务器的工具和参数。

渐进式查询（推荐）：
- 无参数：返回使用指南
- server="xxx"：返回该服务器的工具列表（名称+描述）
- server="xxx", tool="yyy"：返回参数格式（类型/必填/默认值）

完整技术定义（需要原始 JSON）：
- server="xxx", raw=true：返回完整工具定义和健康状态

示例：
  mcporter_help(server="xiaohongshu")                     # 看工具有哪些
  mcporter_help(server="xiaohongshu", tool="search_feeds") # 看参数格式
  mcporter_help(server="xiaohongshu", raw=true)           # 看原始定义"""
)
def mcporter_help(
    server: str | None = None,
    tool: str | None = None,
    raw: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    """查询 mcporter 工具使用方法。"""
    # 如果没有参数，返回使用指南
    if server is None:
        return {
            "ok": True,
            "type": "usage_guide",
            "content": USAGE_GUIDE.strip(),
        }

    # 获取服务器完整信息（用于两种情况）
    result = _run_binary_command(
        "mcporter",
        ["list", server, "--json"],
        timeout_ms=timeout_ms,
    )

    if not result.get("ok") or not result.get("parsed_json"):
        return result

    # raw 模式：直接返回原始数据（替代原来的 inspect_server）
    if raw:
        return {
            "ok": True,
            "type": "raw_definition",
            "server": server,
            "data": result["parsed_json"],
        }

    tools = result["parsed_json"].get("tools", [])

    # 如果只有 server，返回工具列表（精简版）
    if tool is None:
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

    # 如果有 server 和 tool，查询该工具的详细参数
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


@app.tool(
    description="""检查 mcporter 状态和配置。

action 参数：
- "doctor"：验证配置文件（默认）
- "version"：显示 mcporter 版本

示例：
  mcporter_status()                    # 验证配置
  mcporter_status(action="version")    # 查看版本"""
)
def mcporter_status(
    action: Literal["doctor", "version"] = "doctor",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    if action == "version":
        return _run_binary_command("mcporter", ["--version"], timeout_ms=5_000)
    return _run_binary_command("mcporter", ["config", "doctor"], timeout_ms=timeout_ms)


@app.tool(
    description="""激活一个大型 MCP。激活后需重新调用 mcporter_list_servers 确认。

参数：name - 从 mcporter_list_servers().available 中获取的名称

示例：mcporter_activate_mcp(name="playwright")"""
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
            "message": f"已激活 {name}",
            "_next_step": "调用 mcporter_list_servers() 确认 MCP 已出现在 active 列表",
            "_reminder": "大型 MCP 使用完毕后请调用 mcporter_deactivate_mcp 释放上下文",
        }

    return {
        "ok": False,
        "name": name,
        "error": result.get("stderr") or result.get("stdout"),
        "hint": "检查名称是否正确，可用 mcporter_list_servers().available 查看可激活列表",
    }


@app.tool(
    description="""停用大型 MCP 释放上下文。

参数：name - 要停用的 MCP 名称

示例：mcporter_deactivate_mcp(name="playwright")"""
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
            "message": f"已停用 {name}，上下文已释放",
        }

    return {
        "ok": False,
        "name": name,
        "error": result.get("stderr") or result.get("stdout"),
    }

