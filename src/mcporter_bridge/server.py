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


@app.tool(description="Call any tool on a configured mcporter server. Tool arguments are passed as a JSON object.")
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

