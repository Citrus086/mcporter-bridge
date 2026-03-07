from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tomlkit import document, dumps, parse, table


SUPPORTED_CLIENTS = ("codex", "claude", "cline", "cursor")


@dataclass(frozen=True)
class BridgeConfig:
    server_name: str = "mcporter-bridge"
    python_command: str = "python3"
    module_name: str = "mcporter_bridge"
    startup_timeout_ms: int = 30_000


def build_stdio_definition(config: BridgeConfig) -> dict[str, object]:
    return {
        "command": config.python_command,
        "args": ["-m", config.module_name],
    }


def default_config_path(client: str) -> Path | None:
    home = Path.home()
    if client == "codex":
        return home / ".codex" / "config.toml"
    if client == "claude":
        return home / ".claude.json"
    return None


def render_json_snippet(config: BridgeConfig) -> str:
    payload = {"mcpServers": {config.server_name: build_stdio_definition(config)}}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_codex_snippet(config: BridgeConfig) -> str:
    doc = document()
    servers = table()
    bridge = table()
    bridge["type"] = "stdio"
    bridge["command"] = config.python_command
    bridge["args"] = ["-m", config.module_name]
    bridge["startup_timeout_ms"] = config.startup_timeout_ms
    servers[config.server_name] = bridge
    doc["mcp_servers"] = servers
    return dumps(doc)


def render_client_snippet(client: str, config: BridgeConfig) -> str:
    if client == "codex":
        return render_codex_snippet(config)
    if client in {"claude", "cline", "cursor"}:
        return render_json_snippet(config)
    raise ValueError(f"Unsupported client: {client}")


def install_json_client(path: Path, config: BridgeConfig) -> Path | None:
    backup_path = None
    if path.exists():
        backup_path = path.with_name(f"{path.name}.bak")
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {}

    payload.setdefault("mcpServers", {})
    payload["mcpServers"][config.server_name] = build_stdio_definition(config)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return backup_path


def install_codex_client(path: Path, config: BridgeConfig) -> Path | None:
    backup_path = None
    if path.exists():
        original = path.read_text(encoding="utf-8")
        backup_path = path.with_name(f"{path.name}.bak")
        backup_path.write_text(original, encoding="utf-8")
        doc = parse(original)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = document()

    servers = doc.get("mcp_servers")
    if servers is None or not hasattr(servers, "append"):
        servers = table()
        doc["mcp_servers"] = servers

    bridge = table()
    bridge["type"] = "stdio"
    bridge["command"] = config.python_command
    bridge["args"] = ["-m", config.module_name]
    bridge["startup_timeout_ms"] = config.startup_timeout_ms
    servers[config.server_name] = bridge

    path.write_text(dumps(doc), encoding="utf-8")
    return backup_path


def install_client_config(client: str, path: Path, config: BridgeConfig) -> Path | None:
    if client == "codex":
        return install_codex_client(path, config)
    if client in {"claude", "cline", "cursor"}:
        return install_json_client(path, config)
    raise ValueError(f"Unsupported client: {client}")
