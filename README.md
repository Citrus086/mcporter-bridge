# mcporter-bridge

Expose your local [MCPorter](https://github.com/steipete/mcporter) registry as one stable MCP server for coding clients.

`mcporter-bridge` is a small FastMCP server that turns your existing `mcporter` setup into a single, reusable entry point for clients like Codex, Claude Code, Cline, and Cursor.

## Why

If you use multiple coding clients, your MCP setup usually fragments fast:

- Codex has one config format
- Claude Code has another
- Cline and Cursor add their own
- `mcporter` already knows your real server registry, auth state, and runtime

`mcporter-bridge` keeps `mcporter` as the source of truth and gives clients one stable MCP server instead of another pile of duplicated configs.

## What It Does

- Reads your local `mcporter` registry at runtime
- Lists configured MCP servers and their health
- Inspects a specific server and its tool schemas
- Calls any tool on any configured server through `mcporter`
- **Lazy loading**: Activate/deactivate heavy MCPs on demand to save context
- Optionally exposes local `agent-reach` diagnostics as helper tools

This is not a transport proxy and not an enterprise gateway. It is a local-first bridge for client integration.

## Tools

### Core Tools

| Tool | Description |
|------|-------------|
| `mcporter_list_servers` | 【MCP 全景】列出所有已加载(active)和可激活(available)的 MCP 服务器，包含类型区分(small/heavy) |
| `mcporter_help` | 探索 MCP 服务器的工具列表和参数格式，支持 `raw=true` 获取完整技术定义 |
| `mcporter_call_tool` | 调用指定 MCP 的某个工具 |

### Lazy Loading Tools (按需加载)

| Tool | Description |
|------|-------------|
| `mcporter_activate_mcp` | 激活一个大型 MCP（如 chrome-devtools, playwright） |
| `mcporter_deactivate_mcp` | 停用大型 MCP 释放上下文 |

### Utility Tools

| Tool | Description |
|------|-------------|
| `mcporter_status` | 检查 mcporter 状态（config doctor / version） |

All tools return structured output with:

- `ok`
- `timed_out`
- `command`
- `timeout_ms`
- `returncode`
- `stdout`
- `stderr`
- `parsed_json`

## Install

### pip

```bash
pip install mcporter-bridge
```

### pipx

```bash
pipx install mcporter-bridge
```

After installation, you get two commands:

- `mcporter-bridge` to run the MCP server
- `mcporter-bridge-config` to generate or install client snippets

### local development

```bash
git clone https://github.com/Citrus086/mcporter-bridge.git
cd mcporter-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Requirements

- `mcporter` installed and available on `PATH`
- at least one configured MCP server in your local `mcporter` registry

Optional:

## Quick Check

```bash
mcporter-bridge
```

In another shell:

```bash
mcporter list --stdio "python3 -m mcporter_bridge" --json
```

## Client Setup

Ready-made templates live in [examples/](examples/).

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.mcporter-bridge]
type = "stdio"
command = "python3"
args = ["-m", "mcporter_bridge"]
startup_timeout_ms = 30000
```

Or install it automatically:

```bash
mcporter-bridge-config install --client codex
```

Notes:

- OpenAI’s docs confirm that Codex reads MCP config from `~/.codex/config.toml` using the `mcp_servers.<name>` structure for MCP servers.
- The stdio form here is also verified locally with `codex mcp add --help`, which accepts `codex mcp add <name> -- <command...>` for stdio servers.

### Claude Code / Claude Desktop

Add this to your MCP config:

```json
{
  "mcpServers": {
    "mcporter-bridge": {
      "command": "python3",
      "args": ["-m", "mcporter_bridge"]
    }
  }
}
```

Automatic install using the default `~/.claude.json` path:

```bash
mcporter-bridge-config install --client claude
```

Notes:

- Anthropic’s Claude Code docs confirm that user-scoped MCP servers live in `~/.claude.json`.
- The same docs show project-scoped servers stored in `.mcp.json` at the project root.
- The documented JSON shape uses `mcpServers` with `command`, `args`, and `env` for stdio servers.

### Cline

Use the same stdio shape:

```json
{
  "mcpServers": {
    "mcporter-bridge": {
      "command": "python3",
      "args": ["-m", "mcporter_bridge"]
    }
  }
}
```

Generate snippets:

```bash
mcporter-bridge-config snippet --client cline
```

Write to an explicit config path:

```bash
mcporter-bridge-config install --client cline --config-path /path/to/mcp.json
```

Notes:

- Cline’s docs confirm that MCP settings are stored in `cline_mcp_settings.json`.
- For local stdio servers, the documented JSON shape uses `mcpServers` with `command`, `args`, `env`, `alwaysAllow`, and `disabled`.
- Cline’s docs use `type` for remote transport config such as `streamableHttp`, but not in the local stdio example, so the bridge does not emit `type` for Cline.

### Cursor

Cursor uses `mcp.json` with `mcpServers`, and for stdio servers the bridge emits `type: "stdio"` explicitly.

Global config example:

```json
{
  "mcpServers": {
    "mcporter-bridge": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "mcporter_bridge"]
    }
  }
}
```

Install into the default global path:

```bash
mcporter-bridge-config install --client cursor
```

Or write to an explicit config path:

```bash
mcporter-bridge-config install --client cursor --config-path /path/to/mcp.json
```

## Config Helper

Print a snippet:

```bash
mcporter-bridge-config snippet --client codex
```

Customize the launcher:

```bash
mcporter-bridge-config snippet \
  --client claude \
  --python-command /opt/homebrew/bin/python3.13 \
  --module-name mcporter_bridge
```

Install directly into a config file:

```bash
mcporter-bridge-config install --client codex
mcporter-bridge-config install --client claude
```

When an existing config file is updated, the helper writes a sibling backup with a `.bak` suffix first.

## Example Prompts

- "列出所有可用的 MCP 服务器"
- "查看 xiaohongshu 服务器的工具"
- "调用 xiaohongshu 的 check_login_status"
- "激活 playwright 浏览器工具"
- "查看 xiaohongshu 的原始工具定义（raw=true）"

## Lazy Loading (按需加载)

大型 MCP 如 `chrome-devtools` (29 tools) 或 `playwright` (22 tools) 会消耗大量上下文。默认保持未加载状态，需要时再激活。

### MCP 类型

- **small** - 小型 MCP，通常已加载，可直接使用
- **heavy** - 大型 MCP，默认未加载，需先激活

### Setup

1. 创建 heavy MCP 目录：
```bash
mkdir -p ~/.mcporter/heavy/available
```

2. 将大型 MCP 从 `mcporter.json` 移到单独文件：
```bash
# 示例：将 playwright 移到 heavy
echo '{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "description": "浏览器自动化",
      "tags": ["浏览器"]
    }
  }
}' > ~/.mcporter/heavy/available/playwright.json
```

3. 从主 `mcporter.json` 中移除该 MCP。

### Workflow

```
1. mcporter_list_servers()
   ↓ 返回 active（已加载）和 available（可激活）两个列表
   ↓ 需要的 MCP 在 available 中？
2. mcporter_activate_mcp(name="playwright")
   ↓
3. mcporter_list_servers()  # 确认已出现在 active 列表
   ↓
4. 使用 playwright 工具...
   ↓
5. mcporter_deactivate_mcp(name="playwright")  # 用完即释放
```

这让上游 LLM 能够**自我管理上下文**，按需加载/卸载大型 MCP。

## Server Descriptions (服务器描述)

`mcporter-bridge` 会为每个 MCP 服务器提供功能描述，帮助 LLM 了解每个服务是干什么的。

### 描述来源（优先级从高到低）

1. **用户配置** - 在 `~/.mcporter/mcporter.json` 中添加
2. **内置映射** - 常见 MCP 的预设描述
3. **名字推断** - 从服务器名称猜测功能

### 在 mcporter.json 中配置描述

```json
{
  "mcpServers": {
    "my-custom-mcp": {
      "command": "...",
      "args": [...],
      "description": "自定义 MCP 的功能描述",
      "tags": ["标签1", "标签2"],
      "best_for": "最适合的使用场景"
    }
  }
}
```

### 内置描述的常见 MCP

| 服务器名 | 描述 | 用途 |
|---------|------|------|
| exa | AI 搜索引擎 | 搜索网页内容、代码、新闻 |
| xiaohongshu | 小红书操作 | 搜索/发布小红书笔记 |
| douyin | 抖音操作 | 解析抖音视频、下载无水印视频 |
| web-search-prime | 智谱网页搜索 | 搜索中文网页内容 |
| web-reader | 网页阅读器 | 读取并解析网页内容 |
| context7 | 技术文档查询 | 查询编程库的官方文档 |
| zread | GitHub 仓库阅读 | 搜索/阅读 GitHub 仓库内容 |
| zai-mcp-server | Z.AI 多模态工具 | 图像分析、视频分析、OCR |
| bosszhipin | Boss 直聘操作 | 搜索职位、投递简历 |
| notion | Notion 笔记操作 | 读写 Notion 页面 |
| figma | Figma 设计工具 | 读取 Figma 设计稿 |
| github | GitHub 官方 MCP | 创建/更新文件、管理 Issues/PRs、搜索代码 |
| linkedin-scraper | LinkedIn 数据抓取 | 获取个人/公司资料、搜索职位和人才 |
| wechat-article | 微信文章处理 | 转换微信文章格式 |

### 名字推断规则

如果服务器不在内置列表中，会从名称推断：
- 包含 `search` → 搜索相关
- 包含 `browser` / `chrome` → 浏览器相关
- 包含 `github` / `git` → 代码仓库相关
- 包含 `xiaohongshu` → 小红书相关
- ...

## Environment Variables

- `MCPORTER_BRIDGE_MCPORTER_BIN`: override the `mcporter` binary path
- `MCPORTER_BRIDGE_MAX_OUTPUT_CHARS`: cap captured stdout/stderr length

## Roadmap

- higher-level convenience tools for common MCPs
- optional tool allowlists / denylists
- more client-specific path discovery
- richer auth and diagnostics helpers

## License

MIT
