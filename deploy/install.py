#!/usr/bin/env python3
"""Safe installer for the Phase 0-approved TF1 system layout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = Path("/opt/rg40xx-game-presence")
CONFIG_DIR = Path("/etc/rg40xx-game-presence")
UNIT_PATH = Path("/etc/systemd/system/rg40xx-game-presence.service")


class InstallError(RuntimeError):
    pass


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "command failed"
        raise InstallError(f"{Path(command[0]).name}: {detail}")


def _systemctl_state(action: str, unit_name: str) -> bool:
    try:
        result = subprocess.run(["systemctl", action, unit_name], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _require_root() -> None:
    if os.geteuid() != 0:
        raise InstallError("run the installer as root")


def _source_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    required = [root / "src/rg40xx_game_presence", root / "config/config.example.json", root / "deploy/rg40xx-game-presence.service"]
    if not all(path.exists() for path in required):
        raise InstallError("installer source tree is incomplete")
    return root


def _secure(path: Path, mode: int) -> None:
    os.chmod(path, mode)
    try:
        os.chown(path, 0, 0)
    except PermissionError:
        # Unit tests run without real root even when the root gate is mocked.
        # A real installation has already passed _require_root and must not hide
        # an ownership failure.
        if os.geteuid() == 0:
            raise


def _validate_json(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid configuration source: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise InstallError("configuration source must contain a JSON object")


def install(config_source: Path | None, password_source: Path | None, enable: bool, start: bool) -> None:
    _require_root()
    root = _source_root()
    source_config = config_source or root / "config/config.example.json"
    _validate_json(source_config)
    password_path = CONFIG_DIR / "mqtt-password"
    password: str | None = None
    if password_source is not None:
        try:
            password = password_source.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise InstallError(f"cannot read password source: {type(exc).__name__}") from exc
        if not password:
            raise InstallError("password source is empty")
    elif not password_path.exists():
        raise InstallError("MQTT password is absent; supply --password-file on first install")

    APP_DIR.parent.mkdir(parents=True, exist_ok=True)
    app_existed = APP_DIR.exists()
    unit_existed = UNIT_PATH.exists()
    unit_was_enabled = unit_existed and _systemctl_state("is-enabled", UNIT_PATH.name)
    unit_was_active = unit_existed and _systemctl_state("is-active", UNIT_PATH.name)
    backup = APP_DIR.with_name(APP_DIR.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    try:
        with tempfile.TemporaryDirectory(prefix="rg40xx-game-presence-", dir=str(APP_DIR.parent)) as temporary:
            staged = Path(temporary) / APP_DIR.name
            (staged / "src").mkdir(parents=True)
            shutil.copytree(root / "src/rg40xx_game_presence", staged / "src/rg40xx_game_presence")
            shutil.copy2(root / "pyproject.toml", staged / "pyproject.toml")
            for directory in [staged, staged / "src", staged / "src/rg40xx_game_presence"]:
                _secure(directory, 0o755)
            for file_path in staged.rglob("*"):
                if file_path.is_file():
                    _secure(file_path, 0o644)
            if app_existed:
                APP_DIR.rename(backup)
            staged.rename(APP_DIR)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _secure(CONFIG_DIR, 0o700)
        installed_config = CONFIG_DIR / "config.json"
        if not installed_config.exists():
            shutil.copy2(source_config, installed_config)
        _secure(installed_config, 0o600)
        if password_source is not None and password is not None:
            temporary_password = CONFIG_DIR / ".mqtt-password.tmp"
            temporary_password.write_text(password + "\n", encoding="utf-8")
            _secure(temporary_password, 0o600)
            os.replace(temporary_password, password_path)
        _secure(password_path, 0o600)

        UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        unit_backup = UNIT_PATH.with_name(UNIT_PATH.name + ".previous")
        if unit_backup.exists():
            unit_backup.unlink()
        if UNIT_PATH.exists():
            shutil.copy2(UNIT_PATH, unit_backup)
        shutil.copy2(root / "deploy/rg40xx-game-presence.service", UNIT_PATH)
        _secure(UNIT_PATH, 0o644)
        _run(["/usr/bin/env", f"PYTHONPATH={APP_DIR / 'src'}", "/usr/bin/python3", "-m", "rg40xx_game_presence", "check-config", "--config", str(installed_config)])
        _run(["systemctl", "daemon-reload"])
        if enable:
            _run(["systemctl", "enable", UNIT_PATH.name])
        if start:
            _run(["systemctl", "restart", UNIT_PATH.name])
    except Exception:
        if start and not unit_was_active:
            try:
                _run(["systemctl", "stop", UNIT_PATH.name])
            except InstallError:
                pass
        if enable and not unit_was_enabled:
            try:
                _run(["systemctl", "disable", UNIT_PATH.name])
            except InstallError:
                pass
        if APP_DIR.exists():
            shutil.rmtree(APP_DIR)
        if backup.exists():
            backup.rename(APP_DIR)
        unit_backup = UNIT_PATH.with_name(UNIT_PATH.name + ".previous")
        unit_changed = UNIT_PATH.exists() or unit_backup.exists()
        if unit_backup.exists():
            shutil.copy2(unit_backup, UNIT_PATH)
            unit_backup.unlink()
        elif not unit_existed:
            UNIT_PATH.unlink(missing_ok=True)
        if unit_changed:
            try:
                _run(["systemctl", "daemon-reload"])
                if unit_was_enabled:
                    _run(["systemctl", "enable", UNIT_PATH.name])
                if unit_was_active:
                    _run(["systemctl", "restart", UNIT_PATH.name])
            except InstallError:
                pass
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)
        UNIT_PATH.with_name(UNIT_PATH.name + ".previous").unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--no-enable", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        install(args.config, args.password_file, not args.no_enable, not args.no_start)
    except InstallError as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 2
    print("RG40XX Game Presence installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
