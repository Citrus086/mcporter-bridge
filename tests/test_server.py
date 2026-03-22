import json
import subprocess

import mcporter_bridge.server as server


def test_mcporter_help_raw_mode_uses_targeted_lookup(monkeypatch):
    """测试 mcporter_help raw=true 能获取单个服务器的完整定义"""
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/mcporter" if name == "mcporter" else None)

    def fake_run(command, **kwargs):
        assert command[:4] == [
            "/opt/homebrew/bin/mcporter",
            "list",
            "xiaohongshu",
            "--json",
        ]
        return subprocess.CompletedProcess(command, 0, '{"name":"xiaohongshu","tools":[]}', "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)

    result = server.mcporter_help("xiaohongshu", raw=True)

    assert result["ok"] is True
    assert result["type"] == "raw_definition"
    assert result["data"] == {"name": "xiaohongshu", "tools": []}


def test_mcporter_call_tool_passes_json_arguments(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/mcporter" if name == "mcporter" else None)

    def fake_run(command, **kwargs):
        assert command[:4] == [
            "/opt/homebrew/bin/mcporter",
            "call",
            "xiaohongshu.check_login_status",
            "--output",
        ]
        assert command[4] == "json"
        assert command[5] == "--args"
        payload = json.loads(command[6])
        assert payload == {"force": True}
        return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)

    result = server.mcporter_call_tool(
        "xiaohongshu",
        "check_login_status",
        arguments={"force": True},
    )

    assert result["ok"] is True
    assert result["parsed_json"] == {"ok": True}


def test_timeout_is_reported_as_structured_result(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/mcporter" if name == "mcporter" else None)

    def fake_run(command, **kwargs):
        error = subprocess.TimeoutExpired(command, timeout=5, output="slow output")
        error.stderr = "still running"
        raise error

    monkeypatch.setattr(server.subprocess, "run", fake_run)

    result = server.mcporter_help("playwright", raw=True, timeout_ms=5000)

    assert result["ok"] is False
    assert result["timed_out"] is True
    assert result["stdout"] == "slow output"
    assert result["stderr"] == "still running"



