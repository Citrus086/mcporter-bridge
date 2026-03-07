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
- Optionally exposes local `agent-reach` diagnostics as helper tools

This is not a transport proxy and not an enterprise gateway. It is a local-first bridge for client integration.

## Tools

- `mcporter_list_servers`
- `mcporter_get_server`
- `mcporter_inspect_server`
- `mcporter_call_tool`
- `mcporter_config_doctor`
- `mcporter_version`
- `agent_reach_doctor`
- `agent_reach_watch`
- `agent_reach_version`

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

- `agent-reach` installed if you want the `agent_reach_*` tools

## Quick Check

```bash
mcporter-bridge
```

In another shell:

```bash
mcporter list --stdio "python3 -m mcporter_bridge" --json
```

## Client Setup

Ready-made templates live in [examples/](/Users/mima0000/mcporter-bridge/examples).

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

- "List the MCP servers available through mcporter."
- "Inspect the xiaohongshu server and show its tools."
- "Call `check_login_status` on `xiaohongshu`."
- "Run Agent Reach doctor."

## Environment Variables

- `MCPORTER_BRIDGE_MCPORTER_BIN`: override the `mcporter` binary path
- `MCPORTER_BRIDGE_AGENT_REACH_BIN`: override the `agent-reach` binary path
- `MCPORTER_BRIDGE_MAX_OUTPUT_CHARS`: cap captured stdout/stderr length

## Roadmap

- higher-level convenience tools for common MCPs
- optional tool allowlists / denylists
- more client-specific path discovery
- richer auth and diagnostics helpers

## License

MIT
