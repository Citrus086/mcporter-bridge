from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcporter_bridge.client_templates import (
    BridgeConfig,
    SUPPORTED_CLIENTS,
    default_config_path,
    install_client_config,
    render_client_snippet,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcporter-bridge-config",
        description="Generate or install client config snippets for mcporter-bridge.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("snippet", "install"):
        command = subparsers.add_parser(command_name)
        command.add_argument("--client", choices=SUPPORTED_CLIENTS, required=True)
        command.add_argument("--server-name", default="mcporter-bridge")
        command.add_argument("--python-command", default="python3")
        command.add_argument("--module-name", default="mcporter_bridge")
        command.add_argument("--startup-timeout-ms", type=int, default=30_000)
        if command_name == "install":
            command.add_argument("--config-path")

    return parser


def _bridge_config_from_args(args: argparse.Namespace) -> BridgeConfig:
    return BridgeConfig(
        server_name=args.server_name,
        python_command=args.python_command,
        module_name=args.module_name,
        startup_timeout_ms=args.startup_timeout_ms,
    )


def _resolve_install_path(client: str, provided_path: str | None) -> Path:
    if provided_path:
        return Path(provided_path).expanduser()

    default_path = default_config_path(client)
    if default_path is None:
        raise SystemExit(
            f"--config-path is required for {client}. "
            "This client has no single reliable default path across environments."
        )
    return default_path


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = _bridge_config_from_args(args)

    if args.command == "snippet":
        sys.stdout.write(render_client_snippet(args.client, config))
        return

    config_path = _resolve_install_path(args.client, args.config_path)
    backup_path = install_client_config(args.client, config_path, config)
    print(f"Updated {config_path}")
    if backup_path is not None:
        print(f"Backup written to {backup_path}")


if __name__ == "__main__":
    main()
