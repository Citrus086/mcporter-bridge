import json

from tomlkit import parse

from mcporter_bridge.client_templates import (
    BridgeConfig,
    default_config_path,
    install_client_config,
    render_client_snippet,
)


def test_render_codex_snippet_contains_bridge_block():
    snippet = render_client_snippet("codex", BridgeConfig())
    doc = parse(snippet)

    assert doc["mcp_servers"]["mcporter-bridge"]["command"] == "python3"
    assert doc["mcp_servers"]["mcporter-bridge"]["args"] == ["-m", "mcporter_bridge"]


def test_install_json_client_merges_existing_servers(tmp_path):
    path = tmp_path / "claude.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {
                        "command": "npx",
                        "args": ["-y", "@upstash/context7-mcp"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    backup_path = install_client_config("claude", path, BridgeConfig())
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert backup_path == path.with_name("claude.json.bak")
    assert payload["mcpServers"]["context7"]["command"] == "npx"
    assert payload["mcpServers"]["mcporter-bridge"]["command"] == "python3"


def test_install_codex_client_updates_existing_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '\n'.join(
            [
                'model = "gpt-5.4"',
                "",
                '[projects."/tmp"]',
                'trust_level = "trusted"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    install_client_config("codex", path, BridgeConfig())
    doc = parse(path.read_text(encoding="utf-8"))

    assert doc["mcp_servers"]["mcporter-bridge"]["type"] == "stdio"
    assert doc["projects"]["/tmp"]["trust_level"] == "trusted"


def test_default_config_path_only_exists_for_supported_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert default_config_path("codex") == tmp_path / ".codex" / "config.toml"
    assert default_config_path("claude") == tmp_path / ".claude.json"
    assert default_config_path("cursor") is None
