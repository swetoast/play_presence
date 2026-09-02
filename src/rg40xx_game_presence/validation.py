"""Bounded Phase 5 service and performance evidence collection."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from . import __version__

SERVICE = "rg40xx-game-presence.service"
MAX_SAMPLES = 1440
RUNTIME_FAILURE = Path("/run/rg40xx-game-presence/last-failure.json")
MAX_RUNTIME_FAILURE_BYTES = 4096
PREFERRED_RSS_KIB = 30 * 1024
RSS_CEILING_KIB = 40 * 1024


class ValidationError(RuntimeError):
    pass

def record_runtime_failure(phase: str, error: BaseException) -> None:
    """Best-effort bounded volatile record for an unexpected daemon exit."""
    value = {
        "schema_version": 1,
        "project_version": __version__,
        "captured_at_unix": int(time.time()),
        "phase": phase[:64],
        "exception_type": type(error).__name__[:128],
    }
    try:
        RUNTIME_FAILURE.parent.mkdir(parents=True, exist_ok=True)
        temporary = RUNTIME_FAILURE.with_name(RUNTIME_FAILURE.name + ".tmp")
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        if len(payload.encode("utf-8")) > MAX_RUNTIME_FAILURE_BYTES:
            return
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, RUNTIME_FAILURE)
    except OSError:
        return


def read_runtime_failure() -> dict[str, Any] | None:
    try:
        if RUNTIME_FAILURE.stat().st_size > MAX_RUNTIME_FAILURE_BYTES:
            return {"available": False, "error": "oversized"}
        value = json.loads(RUNTIME_FAILURE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}
    if not isinstance(value, dict):
        return {"available": False, "error": "invalid"}
    allowed = {"schema_version", "project_version", "captured_at_unix", "phase", "exception_type"}
    return {"available": True, **{key: value.get(key) for key in allowed}}

def _require_root() -> None:
    if os.geteuid() != 0:
        raise ValidationError("run Phase 5 validation as root")

def _main_pid() -> int:
    try:
        return int(_service_property("MainPID") or "0")
    except ValueError:
        return 0


def _run(command: list[str], timeout: float = 15.0) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return result.returncode, result.stdout.strip()


def _service_property(name: str) -> str | None:
    rc, output = _run(["systemctl", "show", SERVICE, f"--property={name}", "--value"])
    return output if rc == 0 and output else None


def _integer_file(path: Path, key: str | None = None) -> int | None:
    try:
        text = path.read_text(encoding="ascii")
    except OSError:
        return None
    if key is None:
        try:
            return int(text.strip())
        except ValueError:
            return None
    for line in text.splitlines():
        if line.startswith(key + ":"):
            try:
                return int(line.split()[1])
            except (ValueError, IndexError):
                return None
    return None


def _sample(pid: int) -> dict[str, Any]:
    base = Path("/proc") / str(pid)
    try:
        stat_fields = (base / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
        cpu_ticks = int(stat_fields[11]) + int(stat_fields[12])
    except (OSError, ValueError, IndexError):
        cpu_ticks = None
    fds: list[str] = []
    try:
        for entry in list((base / "fd").iterdir())[:64]:
            try:
                target = os.readlink(entry)
            except OSError:
                continue
            if target.startswith("/mnt/mmc/Roms"):
                fds.append(target)
    except OSError:
        pass
    return {
        "monotonic_seconds": round(time.monotonic(), 3),
        "pid": pid,
        "cpu_ticks": cpu_ticks,
        "rss_kib": _integer_file(base / "status", "VmRSS"),
        "pss_kib": _integer_file(base / "smaps_rollup", "Pss"),
        "write_bytes": _integer_file(base / "io", "write_bytes"),
        "rom_fds": sorted(fds),
    }



def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    pids = [sample.get("pid") for sample in samples if sample.get("pid")]
    observed_pids = list(dict.fromkeys(pids))
    continuous = bool(samples) and len(observed_pids) == 1 and len(pids) == len(samples)
    interruption_reason: str | None = None
    if not samples:
        interruption_reason = "no-samples"
    elif len(pids) != len(samples):
        interruption_reason = "service-unavailable"
    elif len(observed_pids) > 1:
        interruption_reason = "process-restarted"
    metric_names = ("cpu_ticks", "rss_kib", "pss_kib", "write_bytes")
    valid_counts = {name: sum(sample.get(name) is not None for sample in samples) for name in metric_names}
    rss = [sample["rss_kib"] for sample in samples if sample.get("rss_kib") is not None]
    pss = [sample["pss_kib"] for sample in samples if sample.get("pss_kib") is not None]
    writes = [sample["write_bytes"] for sample in samples if sample.get("write_bytes") is not None]
    cpu_percent: float | None = None
    if continuous and len(samples) >= 2:
        first, last = samples[0], samples[-1]
        elapsed = last["monotonic_seconds"] - first["monotonic_seconds"]
        if elapsed > 0 and first.get("cpu_ticks") is not None and last.get("cpu_ticks") is not None:
            ticks = os.sysconf("SC_CLK_TCK")
            cpu_percent = round(((last["cpu_ticks"] - first["cpu_ticks"]) / ticks) / elapsed * 100, 4)
    final_complete = bool(samples) and all(samples[-1].get(key) is not None for key in ("pid", "cpu_ticks", "rss_kib", "write_bytes"))
    return {
        "measurement_continuous": continuous,
        "interruption_reason": interruption_reason,
        "observed_pids": observed_pids,
        "pid_change_count": max(0, len(observed_pids) - 1),
        "sample_count": len(samples),
        "valid_sample_counts": valid_counts,
        "final_sample_complete": final_complete,
        "cpu_percent_over_window": cpu_percent,
        "rss_max_kib": max(rss) if rss else None,
        "rss_growth_kib": rss[-1] - rss[0] if continuous and len(rss) == len(samples) and len(rss) >= 2 else None,
        "pss_max_kib": max(pss) if pss else None,
        "pss_growth_kib": pss[-1] - pss[0] if continuous and len(pss) == len(samples) and len(pss) >= 2 else None,
        "write_bytes_growth": writes[-1] - writes[0] if continuous and len(writes) == len(samples) and len(writes) >= 2 else None,
        "rom_file_descriptor_observed": any(sample.get("rom_fds") for sample in samples),
    }

def _assessment(summary: dict[str, Any], journal_available: bool) -> dict[str, bool | None]:
    continuous = summary.get("measurement_continuous") is True
    sample_count = int(summary.get("sample_count") or 0)
    growth_usable = continuous and sample_count >= 2 and summary.get("final_sample_complete") is True

    cpu = summary.get("cpu_percent_over_window")
    rss_max = summary.get("rss_max_kib")
    rss_growth = summary.get("rss_growth_kib")
    pss_growth = summary.get("pss_growth_kib")
    write_growth = summary.get("write_bytes_growth")

    return {
        "continuous_window": continuous,
        "growth_window_usable": growth_usable,
        "cpu_zero_at_reported_precision": cpu == 0.0 if cpu is not None else None,
        "rss_at_or_below_preferred_limit": rss_max <= PREFERRED_RSS_KIB if rss_max is not None else None,
        "rss_below_release_ceiling": rss_max < RSS_CEILING_KIB if rss_max is not None else None,
        "rss_growth_zero": rss_growth == 0 if rss_growth is not None else None,
        "pss_growth_zero": pss_growth == 0 if pss_growth is not None else None,
        "process_write_growth_zero": write_growth == 0 if write_growth is not None else None,
        "no_rom_descriptor_observed": not bool(summary.get("rom_file_descriptor_observed")),
        "journal_capture_available": journal_available,
    }

def collect(duration_seconds: int, interval_seconds: int) -> dict[str, Any]:
    _require_root()
    if duration_seconds < 0 or interval_seconds < 1:
        raise ValidationError("duration must be non-negative and interval must be positive")
    count = 1 if duration_seconds == 0 else min(MAX_SAMPLES, duration_seconds // interval_seconds + 1)
    pid = _main_pid()
    if pid <= 0:
        raise ValidationError("service has no running main process")
    restart_count_before = _service_property("NRestarts")
    samples: list[dict[str, Any]] = []
    for index in range(count):
        current_pid = _main_pid()
        samples.append(_sample(current_pid) if current_pid > 0 else {"monotonic_seconds": round(time.monotonic(), 3), "pid": None, "cpu_ticks": None, "rss_kib": None, "pss_kib": None, "write_bytes": None, "rom_fds": []})
        if index + 1 < count:
            time.sleep(interval_seconds)
    enabled_rc, enabled = _run(["systemctl", "is-enabled", SERVICE])
    active_rc, active = _run(["systemctl", "is-active", SERVICE])
    journal_rc, journal = _run(["journalctl", "-u", SERVICE, "--since", "boot", "--no-pager", "--output", "short-monotonic", "-n", "200"])
    summary = _summary(samples)
    return {
        "schema_version": 2,
        "project_version": __version__,
        "captured_at_unix": int(time.time()),
        "service": {
            "name": SERVICE,
            "enabled": enabled_rc == 0 and enabled == "enabled",
            "active": active_rc == 0 and active == "active",
            "initial_main_pid": pid,
            "final_main_pid": _main_pid(),
            "restart_count_before": restart_count_before,
            "restart_count_after": _service_property("NRestarts"),
            "unit_file": _service_property("FragmentPath"),
        },
        "samples": samples,
        "summary": summary,
        "assessment": _assessment(summary, journal_rc == 0),
        "last_runtime_failure": read_runtime_failure(),
        "journal": {
            "available": journal_rc == 0,
            "empty": journal_rc == 0 and not journal,
            "error": None if journal_rc == 0 else journal,
            "line_count": len(journal.splitlines()) if journal_rc == 0 else None,
            "tail": journal.splitlines()[-40:] if journal_rc == 0 else [],
        },
        "limits": {
            "maximum_samples": MAX_SAMPLES,
            "fd_targets_per_sample": 64,
            "journal_lines": 200,
            "preferred_rss_kib": PREFERRED_RSS_KIB,
            "rss_ceiling_kib": RSS_CEILING_KIB,
        },
    }


def write_result(result: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
