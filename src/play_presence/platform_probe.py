"""Safe, bounded Phase 0 hardware verification for TF1."""

from __future__ import annotations

import json
import os
import resource
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__

USB_ONLINE = Path("/sys/class/power_supply/axp2202-usb/online")
UNIT_NAME = "play-presence-probe.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
MARKER_NAME = ".play-presence-probe"
SCHEMA_VERSION = 1


class ProbeError(RuntimeError):
    """A concise fatal probe error."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _run(command: list[str], timeout: float = 20.0) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(127, "", type(exc).__name__)
    return CommandResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())


def _progress(message: str) -> None:
    text = message[:68]
    print(f"\rPhase 0: {text:<68}", end="", flush=True)


def _finish_progress(message: str) -> None:
    _progress(message)
    print()


def _require_root() -> None:
    if os.geteuid() != 0:
        raise ProbeError("run the platform probe as root")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError(f"cannot read probe state: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ProbeError("probe state has an invalid format")
    return value


def _read_boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip() or None
    except OSError:
        return None


def _memory_kib() -> dict[str, int | None]:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result: dict[str, int | None] = {"rss_kib": int(rss), "pss_kib": None}
    try:
        for line in Path("/proc/self/smaps_rollup").read_text(encoding="ascii").splitlines():
            if line.startswith("Pss:"):
                result["pss_kib"] = int(line.split()[1])
                break
    except (OSError, ValueError, IndexError):
        pass
    return result


def _timed_text_read(path: Path) -> dict[str, Any]:
    start_ns = time.monotonic_ns()
    try:
        value = path.read_text(encoding="ascii").strip()
        elapsed = time.monotonic_ns() - start_ns
        normalized = value if value in {"0", "1"} else None
        return {
            "available": True,
            "raw_value": value[:16],
            "normalized": normalized,
            "duration_us": round(elapsed / 1000, 3),
            "error": None,
        }
    except OSError as exc:
        elapsed = time.monotonic_ns() - start_ns
        return {
            "available": False,
            "raw_value": None,
            "normalized": None,
            "duration_us": round(elapsed / 1000, 3),
            "error": type(exc).__name__,
        }


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "writable": os.access(path, os.W_OK) if path.exists() else False,
    }


def _write_marker(directory: Path, token: str) -> Path:
    marker = directory / MARKER_NAME
    marker.write_text(token + "\n", encoding="ascii")
    with marker.open("r", encoding="ascii") as handle:
        os.fsync(handle.fileno())
    return marker


def _install_test_unit(token: str) -> dict[str, Any]:
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return {"attempted": False, "installed": False, "error": "systemctl-not-found"}
    unit = "\n".join(
        [
            "[Unit]",
            "Description=RG40XX Game Presence Phase 0 probe",
            "After=local-fs.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart=/usr/bin/printf {token}\\n",
            "RemainAfterExit=yes",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    try:
        UNIT_PATH.write_text(unit, encoding="ascii")
    except OSError as exc:
        return {"attempted": True, "installed": False, "error": type(exc).__name__}
    reload_result = _run([systemctl, "daemon-reload"])
    enable_result = _run([systemctl, "enable", UNIT_NAME])
    start_result = _run([systemctl, "start", UNIT_NAME])
    return {
        "attempted": True,
        "installed": all(r.returncode == 0 for r in (reload_result, enable_result, start_result)),
        "daemon_reload_rc": reload_result.returncode,
        "enable_rc": enable_result.returncode,
        "start_rc": start_result.returncode,
        "error": None,
    }


def _mqtt_measurement() -> dict[str, Any]:
    before = _memory_kib()
    try:
        import paho.mqtt.client as mqtt
    except (ImportError, OSError) as exc:
        return {"available": False, "error": type(exc).__name__, "before": before}
    imported = _memory_kib()
    client = mqtt.Client(client_id=f"play-presence-phase0-{os.getpid()}", clean_session=True)
    start = time.monotonic()
    client.loop_start()
    time.sleep(0.15)
    alive_during_test = bool(getattr(client, "_thread", None) and client._thread.is_alive())
    client.loop_stop()
    elapsed = time.monotonic() - start
    after = _memory_kib()
    return {
        "available": True,
        "error": None,
        "before": before,
        "after_import": imported,
        "after_loop": after,
        "network_thread_alive": alive_during_test,
        "loop_test_seconds": round(elapsed, 3),
    }



def _mqtt_broker_probe(host: str, port: int, username: str, password_file: str) -> dict[str, Any]:
    if not host:
        return {"configured": False, "connected": False, "error": "not-configured"}
    if not 1 <= port <= 65535:
        return {"configured": True, "connected": False, "error": "invalid-port", "host": host, "port": port}
    try:
        import paho.mqtt.client as mqtt
    except (ImportError, OSError) as exc:
        return {"configured": True, "connected": False, "error": type(exc).__name__, "host": host, "port": port}
    password = None
    if password_file:
        try:
            password = Path(password_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            return {"configured": True, "connected": False, "error": type(exc).__name__, "host": host, "port": port}
    connected = False
    disconnected = False
    connect_rc: int | None = None

    def on_connect(client: Any, userdata: Any, flags: Any, rc: int) -> None:
        nonlocal connected, connect_rc
        connect_rc = int(rc)
        connected = rc == 0

    def on_disconnect(client: Any, userdata: Any, rc: int) -> None:
        nonlocal disconnected
        disconnected = True

    client = mqtt.Client(client_id=f"play-presence-phase0-broker-{os.getpid()}", clean_session=True)
    if username:
        client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    started = time.monotonic()
    error = None
    try:
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        deadline = time.monotonic() + 12.0
        while not connected and connect_rc is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if connected:
            # Sleep longer than the longest planned idle interval while Paho owns keepalive.
            time.sleep(10.5)
        client.disconnect()
        stop_deadline = time.monotonic() + 2.0
        while not disconnected and time.monotonic() < stop_deadline:
            time.sleep(0.05)
    except (OSError, ValueError) as exc:
        error = type(exc).__name__
    finally:
        client.loop_stop()
    return {
        "configured": True,
        "host": host,
        "port": port,
        "username_configured": bool(username),
        "password_file_configured": bool(password_file),
        "connected": connected,
        "connect_rc": connect_rc,
        "clean_disconnect_observed": disconnected,
        "planned_interval_seconds": 10,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "error": error,
    }

def _prepare_record(
    token: str,
    use_systemd: bool,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str,
    mqtt_password_file: str,
) -> dict[str, Any]:
    paths = [Path("/opt"), Path("/etc"), Path("/etc/systemd/system"), Path("/run")]
    markers: dict[str, str] = {}
    statuses = {str(path): _path_status(path) for path in paths}
    for directory in (Path("/opt"), Path("/etc")):
        if directory.is_dir() and os.access(directory, os.W_OK):
            try:
                markers[str(directory)] = str(_write_marker(directory, token))
            except OSError:
                pass
    run_marker = None
    if Path("/run").is_dir() and os.access("/run", os.W_OK):
        try:
            run_marker = str(_write_marker(Path("/run"), token))
        except OSError:
            pass
    systemd = _install_test_unit(token) if use_systemd else {
        "attempted": False,
        "installed": False,
        "error": "disabled-by-option",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project_version": __version__,
        "stage": "prepared",
        "token": token,
        "prepared_at_unix": int(time.time()),
        "boot_id": _read_boot_id(),
        "paths": statuses,
        "persistent_markers": markers,
        "run_marker": run_marker,
        "systemd": systemd,
        "usb": _timed_text_read(USB_ONLINE),
        "python_memory": _memory_kib(),
        "paho": _mqtt_measurement(),
        "mqtt_broker": _mqtt_broker_probe(mqtt_host, mqtt_port, mqtt_username, mqtt_password_file),
        "python": sys.version.split()[0],
    }


def run_prepare(
    state_dir: str,
    use_systemd: bool = True,
    mqtt_host: str = "",
    mqtt_port: int = 1883,
    mqtt_username: str = "",
    mqtt_password_file: str = "",
) -> int:
    _require_root()
    state_path = Path(state_dir) / "state.json"
    if state_path.exists():
        raise ProbeError("existing probe state found; verify or remove it before preparing again")
    _progress("checking writable locations")
    token = secrets.token_hex(16)
    record = _prepare_record(token, use_systemd, mqtt_host, mqtt_port, mqtt_username, mqtt_password_file)
    _progress("saving pre-reboot state")
    _atomic_json(state_path, record)
    _finish_progress("prepared; reboot normally, then run probe verify")
    return 0


def _marker_matches(path_text: str | None, token: str) -> bool:
    if not path_text:
        return False
    try:
        return Path(path_text).read_text(encoding="ascii").strip() == token
    except OSError:
        return False


def _systemd_verify() -> dict[str, Any]:
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return {"available": False, "unit_exists": UNIT_PATH.exists(), "enabled": False, "active": False}
    enabled = _run([systemctl, "is-enabled", UNIT_NAME])
    active = _run([systemctl, "is-active", UNIT_NAME])
    return {
        "available": True,
        "unit_exists": UNIT_PATH.exists(),
        "enabled": enabled.returncode == 0,
        "active": active.returncode == 0,
        "enabled_rc": enabled.returncode,
        "active_rc": active.returncode,
    }


def _cleanup(state_dir: Path, prepared: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    systemctl = shutil.which("systemctl")
    if systemctl and UNIT_PATH.exists():
        for command in ([systemctl, "disable", "--now", UNIT_NAME],):
            result = _run(command)
            if result.returncode != 0:
                errors.append("systemd-disable")
        try:
            UNIT_PATH.unlink()
        except OSError:
            errors.append("systemd-unit-remove")
        _run([systemctl, "daemon-reload"])
    for path_text in list(prepared.get("persistent_markers", {}).values()) + [prepared.get("run_marker")]:
        if path_text:
            try:
                Path(path_text).unlink(missing_ok=True)
            except OSError:
                errors.append("marker-remove")
    try:
        shutil.rmtree(state_dir)
    except OSError:
        errors.append("state-remove")
    return sorted(set(errors))


def _phase0_outcome(prepared: dict[str, Any], verified: dict[str, Any]) -> str:
    broker = prepared.get("mqtt_broker", {})
    systemd_prepared = prepared.get("systemd", {})
    systemd_verified = verified.get("systemd", {})
    required = [
        verified["reboot_observed"],
        verified["opt_persistent"],
        verified["etc_persistent"],
        verified["run_volatile"],
        verified["usb"]["available"],
        verified["usb"]["normalized"] in {"0", "1"},
        bool(prepared.get("paho", {}).get("available")),
        bool(prepared.get("paho", {}).get("network_thread_alive")),
        bool(verified.get("paho", {}).get("network_thread_alive")),
        bool(broker.get("configured")),
        bool(broker.get("connected")),
        bool(broker.get("clean_disconnect_observed")),
        bool(systemd_prepared.get("attempted")),
        bool(systemd_prepared.get("installed")),
        bool(systemd_verified.get("unit_exists")),
        bool(systemd_verified.get("enabled")),
        bool(systemd_verified.get("active")),
    ]
    return "pass" if all(required) else "blocked"


def run_verify(state_dir: str, output: str, keep_artifacts: bool = False) -> int:
    _require_root()
    state_root = Path(state_dir)
    prepared = _load_json(state_root / "state.json")
    if prepared.get("stage") != "prepared" or prepared.get("schema_version") != SCHEMA_VERSION:
        raise ProbeError("probe state is not a compatible prepared record")
    token = prepared.get("token")
    if not isinstance(token, str) or not token:
        raise ProbeError("probe state is missing its verification token")

    _progress("checking post-reboot persistence")
    markers = prepared.get("persistent_markers", {})
    boot_before = prepared.get("boot_id")
    boot_now = _read_boot_id()
    verified: dict[str, Any] = {
        "verified_at_unix": int(time.time()),
        "boot_id": boot_now,
        "reboot_observed": bool(boot_before and boot_now and boot_before != boot_now),
        "opt_persistent": _marker_matches(markers.get("/opt"), token),
        "etc_persistent": _marker_matches(markers.get("/etc"), token),
        "run_volatile": not _marker_matches(prepared.get("run_marker"), token),
        "systemd": _systemd_verify(),
        "usb": _timed_text_read(USB_ONLINE),
        "python_memory": _memory_kib(),
        "paho": _mqtt_measurement(),
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "project_version": __version__,
        "result": "blocked",
        "prepared": prepared,
        "verified": verified,
        "claims": {
            "ordinary_reboot_persistence_only": True,
            "firmware_reflash_persistence_tested": False,
        },
        "cleanup_errors": [],
    }
    result["result"] = _phase0_outcome(prepared, verified)
    output_path = Path(output)
    _progress("writing bounded result")
    _atomic_json(output_path, result)
    if not keep_artifacts:
        result["cleanup_errors"] = _cleanup(state_root, prepared)
        _atomic_json(output_path, result)
    _finish_progress(f"{result['result']}; result: {output_path}")
    return 0 if result["result"] == "pass" else 3
