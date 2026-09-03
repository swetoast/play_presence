from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("installer", ROOT / "deploy/install.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_service_unit_has_bounded_restart_and_verified_paths() -> None:
    unit = (ROOT / "deploy/play-presence.service").read_text(encoding="utf-8")
    assert "RestartSec=60" in unit
    assert "StartLimitBurst=3" in unit
    assert "ExecStartPre=/usr/bin/python3 -m play_presence check-config" in unit
    assert "ExecStart=/usr/bin/python3 -m play_presence run" in unit
    assert "RuntimeDirectory=play-presence" in unit
    assert "ReadOnlyPaths=/opt/play-presence /mnt/mmc/Roms" in unit
    assert "RuntimeDirectoryMode=0700" in unit
    assert "User=root" in unit


def test_installer_requires_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.os, "geteuid", lambda: 1000)
    with pytest.raises(installer.InstallError, match="root"):
        installer._require_root()


def test_installer_rejects_invalid_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(installer.InstallError, match="JSON object"):
        installer._validate_json(path)


def test_installer_preserves_existing_config_and_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "opt/app"
    config_dir = tmp_path / "etc/app"
    unit = tmp_path / "etc/systemd/system/app.service"
    source = ROOT
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text('{"existing":true}', encoding="utf-8")
    (config_dir / "mqtt-password").write_text("existing-secret\n", encoding="utf-8")
    monkeypatch.setattr(installer, "APP_DIR", app)
    monkeypatch.setattr(installer, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(installer, "UNIT_PATH", unit)
    monkeypatch.setattr(installer, "_source_root", lambda: source)
    monkeypatch.setattr(installer, "_require_root", lambda: None)
    commands = []
    monkeypatch.setattr(installer, "_run", lambda command: commands.append(command))
    installer.install(None, None, enable=False, start=False)
    assert (config_dir / "config.json").read_text(encoding="utf-8") == '{"existing":true}'
    assert (config_dir / "mqtt-password").read_text(encoding="utf-8") == "existing-secret\n"
    assert (app / "src/play_presence/__main__.py").exists()
    assert unit.exists()
    assert any("check-config" in command for command in commands)


def test_installer_rolls_back_application_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "opt/app"
    config_dir = tmp_path / "etc/app"
    unit = tmp_path / "etc/systemd/system/app.service"
    app.mkdir(parents=True)
    (app / "old.txt").write_text("old", encoding="utf-8")
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text('{}', encoding="utf-8")
    (config_dir / "mqtt-password").write_text("secret\n", encoding="utf-8")
    monkeypatch.setattr(installer, "APP_DIR", app)
    monkeypatch.setattr(installer, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(installer, "UNIT_PATH", unit)
    monkeypatch.setattr(installer, "_source_root", lambda: ROOT)
    monkeypatch.setattr(installer, "_require_root", lambda: None)
    monkeypatch.setattr(installer, "_run", lambda command: (_ for _ in ()).throw(installer.InstallError("failed")))
    with pytest.raises(installer.InstallError):
        installer.install(None, None, enable=False, start=False)
    assert (app / "old.txt").read_text(encoding="utf-8") == "old"


def test_service_disables_bytecode_and_limits_address_families() -> None:
    unit = (ROOT / "deploy/play-presence.service").read_text(encoding="utf-8")
    assert "PYTHONDONTWRITEBYTECODE=1" in unit
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in unit
    assert "ProtectSystem=full" in unit


def test_failed_update_restores_systemd_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "opt/app"; config_dir = tmp_path / "etc/app"; unit = tmp_path / "etc/systemd/system/app.service"
    app.mkdir(parents=True); (app / "old.txt").write_text("old", encoding="utf-8")
    config_dir.mkdir(parents=True); (config_dir / "config.json").write_text('{}', encoding="utf-8"); (config_dir / "mqtt-password").write_text("secret\n", encoding="utf-8")
    unit.parent.mkdir(parents=True); unit.write_text("old unit", encoding="utf-8")
    monkeypatch.setattr(installer, "APP_DIR", app); monkeypatch.setattr(installer, "CONFIG_DIR", config_dir); monkeypatch.setattr(installer, "UNIT_PATH", unit); monkeypatch.setattr(installer, "_source_root", lambda: ROOT); monkeypatch.setattr(installer, "_require_root", lambda: None); monkeypatch.setattr(installer, "_systemctl_state", lambda action, name: True)
    commands=[]; failed=False
    def run(command):
        nonlocal failed
        commands.append(command)
        if "check-config" in command and not failed:
            failed=True; raise installer.InstallError("failed")
    monkeypatch.setattr(installer, "_run", run)
    with pytest.raises(installer.InstallError): installer.install(None, None, enable=True, start=True)
    assert unit.read_text(encoding="utf-8") == "old unit"
    assert ["systemctl", "daemon-reload"] in commands
    assert ["systemctl", "enable", unit.name] in commands
    assert ["systemctl", "restart", unit.name] in commands


def test_service_unit_carries_full_hardening_and_rate_limit() -> None:
    """Guard the systemd unit so a future edit cannot silently drop hardening.

    These directives back the P5-SEC and P5-SVC roadmap items: no new
    privileges, a private /tmp, read-only system and home, read-only ROM
    storage, a tmpfs runtime directory, a bounded restart policy, and a
    restricted socket family set.
    """
    unit = (ROOT / "deploy/play-presence.service").read_text(encoding="utf-8")
    required = [
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectHome=true",
        "ProtectSystem=full",
        "ReadOnlyPaths=/opt/play-presence /mnt/mmc/Roms",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "UMask=0077",
        "RuntimeDirectory=play-presence",
        "RuntimeDirectoryMode=0700",
        "KillSignal=SIGTERM",
        "TimeoutStopSec=20",
        "Restart=on-failure",
        "RestartSec=60",
        "StartLimitIntervalSec=600",
        "StartLimitBurst=3",
        "User=root",
        "Group=root",
    ]
    missing = [directive for directive in required if directive not in unit]
    assert not missing, f"service unit is missing hardening directives: {missing}"
