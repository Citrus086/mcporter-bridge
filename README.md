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

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.mcporter-bridge]
type = "stdio"
command = "python3"
args = ["-m", "mcporter_bridge"]
startup_timeout_ms = 30000
```

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

### Cline / Cursor

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
- client config generators
- richer auth and diagnostics helpers

## License

MIT

