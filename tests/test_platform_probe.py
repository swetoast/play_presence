from __future__ import annotations

import json
from pathlib import Path

import pytest

from rg40xx_game_presence import platform_probe as probe


def test_timed_text_read_accepts_zero_and_one(tmp_path: Path) -> None:
    value = tmp_path / "online"
    value.write_text(" 1\n", encoding="ascii")
    result = probe._timed_text_read(value)
    assert result["available"] is True
    assert result["normalized"] == "1"
    assert result["duration_us"] >= 0


def test_timed_text_read_rejects_unexpected_value(tmp_path: Path) -> None:
    value = tmp_path / "online"
    value.write_text("charging\n", encoding="ascii")
    result = probe._timed_text_read(value)
    assert result["available"] is True
    assert result["normalized"] is None
    assert result["raw_value"] == "charging"


def test_timed_text_read_handles_missing_file(tmp_path: Path) -> None:
    result = probe._timed_text_read(tmp_path / "missing")
    assert result["available"] is False
    assert result["error"] == "FileNotFoundError"


def test_atomic_json_replaces_complete_document(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    probe._atomic_json(target, {"result": "pass", "secret": None})
    assert json.loads(target.read_text(encoding="utf-8")) == {"result": "pass", "secret": None}
    assert not target.with_name("result.json.tmp").exists()


def test_load_json_rejects_non_object(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("[]", encoding="utf-8")
    with pytest.raises(probe.ProbeError, match="invalid format"):
        probe._load_json(target)


def test_marker_match(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    marker.write_text("abc\n", encoding="ascii")
    assert probe._marker_matches(str(marker), "abc") is True
    assert probe._marker_matches(str(marker), "different") is False
    assert probe._marker_matches(None, "abc") is False


def test_phase0_blocks_without_systemd_and_broker() -> None:
    prepared = {
        "paho": {"available": True, "network_thread_alive": True},
        "mqtt_broker": {"configured": False},
        "systemd": {"attempted": False},
    }
    verified = {
        "reboot_observed": True,
        "opt_persistent": True,
        "etc_persistent": True,
        "run_volatile": True,
        "usb": {"available": True, "normalized": "0"},
        "systemd": {},
        "paho": {"network_thread_alive": True},
    }
    assert probe._phase0_outcome(prepared, verified) == "blocked"


def test_phase0_passes_only_with_full_gate_evidence() -> None:
    prepared = {
        "paho": {"available": True, "network_thread_alive": True},
        "mqtt_broker": {"configured": True, "connected": True, "clean_disconnect_observed": True},
        "systemd": {"attempted": True, "installed": True},
    }
    verified = {
        "reboot_observed": True,
        "opt_persistent": True,
        "etc_persistent": True,
        "run_volatile": True,
        "usb": {"available": True, "normalized": "1"},
        "paho": {"network_thread_alive": True},
        "systemd": {"unit_exists": True, "enabled": True, "active": True},
    }
    assert probe._phase0_outcome(prepared, verified) == "pass"


def test_phase0_blocks_when_reboot_not_observed() -> None:
    prepared = {
        "paho": {"available": True, "network_thread_alive": True},
        "mqtt_broker": {"configured": False},
        "systemd": {"attempted": False},
    }
    verified = {
        "reboot_observed": False,
        "opt_persistent": True,
        "etc_persistent": True,
        "run_volatile": True,
        "usb": {"available": True, "normalized": "1"},
        "systemd": {},
        "paho": {"network_thread_alive": True},
    }
    assert probe._phase0_outcome(prepared, verified) == "blocked"


def test_phase0_requires_active_enabled_systemd_when_attempted() -> None:
    prepared = {
        "paho": {"available": True, "network_thread_alive": True},
        "systemd": {"attempted": True},
    }
    verified = {
        "reboot_observed": True,
        "opt_persistent": True,
        "etc_persistent": True,
        "run_volatile": True,
        "usb": {"available": True, "normalized": "1"},
        "systemd": {"unit_exists": True, "enabled": True, "active": False},
    }
    assert probe._phase0_outcome(prepared, verified) == "blocked"


def test_prepare_refuses_to_overwrite_existing_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(probe, "_require_root", lambda: None)
    with pytest.raises(probe.ProbeError, match="existing probe state"):
        probe.run_prepare(str(state_dir), use_systemd=False)


def test_prepare_writes_bounded_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(probe, "_require_root", lambda: None)
    monkeypatch.setattr(probe, "_prepare_record", lambda token, use_systemd, mqtt_host, mqtt_port, mqtt_username, mqtt_password_file: {
        "schema_version": probe.SCHEMA_VERSION,
        "project_version": "0.1.0",
        "stage": "prepared",
        "token": token,
        "systemd": {"attempted": False},
    })
    assert probe.run_prepare(str(state_dir), use_systemd=False) == 0
    data = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert data["stage"] == "prepared"
    assert len(data["token"]) == 32
    assert (state_dir / "state.json").stat().st_size < 4096


def test_cli_version() -> None:
    from rg40xx_game_presence.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["probe", "verify", "--output", "/tmp/out.json"])
    assert args.command == "probe"
    assert args.stage == "verify"
    assert args.output == "/tmp/out.json"


def test_mqtt_broker_probe_is_optional() -> None:
    result = probe._mqtt_broker_probe("", 1883, "", "")
    assert result == {"configured": False, "connected": False, "error": "not-configured"}


def test_validate_cli_arguments() -> None:
    from rg40xx_game_presence.__main__ import build_parser

    args = build_parser().parse_args(["validate", "--duration", "3600", "--interval", "60", "--output", "/tmp/result.json"])
    assert args.command == "validate"
    assert args.duration == 3600
    assert args.interval == 60
    assert str(args.output) == "/tmp/result.json"
