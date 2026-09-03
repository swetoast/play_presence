"""Direct procfs game-session detection for TF1."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable

from .config import DetectionConfig

_GAME_DGE_PREFIX = "/mnt/vendor/bin/game/"
_OPENBOR_DGE_PATH = "/mnt/vendor/deep/openBOR/OpenBOR.dge"
_EMULATOR_NAMES = {
    "fba4arm": "FinalBurn Alpha 4 ARM",
    "fbasdl": "FinalBurn Alpha SDL",
    "fbaverti": "FinalBurn Alpha Vertical",
    "fc_emu": "Nintendo Entertainment System Emulator",
    "gba_emu": "Game Boy Advance Emulator",
    "vbanext": "VBA Next",
    "gbcgb_emu": "Game Boy / Game Boy Color Emulator",
    "md_emu": "Mega Drive Emulator",
    "ngp": "Neo Geo Pocket Emulator",
    "sfc_emu": "Super Nintendo Emulator",
    "smsgg_emu": "Master System / Game Gear Emulator",
    "pce": "PC Engine Emulator",
    "swanemu": "WonderSwan Emulator",
    "xmame": "XMAME",
    "OpenBOR": "OpenBOR",
}
_EXCLUDED_SUFFIXES = {
    ".cfg", ".conf", ".so", ".sav", ".srm", ".state", ".rtc", ".m3u",
}
_RETROARCH_CHUNK = 1024 * 1024
_RETROARCH_OVERLAP = 4096
_RETROARCH_MAX_REGION = 128 * 1024 * 1024
_RETROARCH_SCAN_LIMIT = 384 * 1024 * 1024
_RETROARCH_REGION_CACHE: dict[tuple[int, int], tuple[int, int]] = {}
_RETROARCH_CONTENT_CACHE: dict[tuple[int, int], tuple[str | None, str]] = {}


class PowerMode(str, Enum):
    USB = "usb"
    BATTERY = "battery"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    executable: str
    argv: tuple[str, ...]
    start_ticks: int


@dataclass(frozen=True)
class SessionCandidate:
    pid: int
    process_start_ticks: int
    executable: str
    rom_path: str
    rom_root: str
    system_folder: str
    system_id: str
    system_name: str
    emulator: str
    core: str | None
    rom_file: str
    started_at: str | None

    @property
    def identity(self) -> tuple[int, int, str, str]:
        return self.pid, self.process_start_ticks, self.rom_path, self.executable


def parse_start_ticks(stat: bytes | str) -> int:
    line = os.fsdecode(stat) if isinstance(stat, bytes) else stat
    close = line.rfind(")")
    if close < 0:
        raise ValueError("stat record has no closing parenthesis")
    remainder = line[close + 1 :].split()
    # The remainder starts with field 3. Field 22 is remainder index 19.
    if len(remainder) <= 19:
        raise ValueError("stat record has no start-time field")
    try:
        value = int(remainder[19])
    except ValueError as exc:
        raise ValueError("stat start-time field is not numeric") from exc
    if value < 0:
        raise ValueError("stat start-time field is negative")
    return value


def decode_cmdline(data: bytes) -> tuple[str, ...]:
    if not data:
        return ()
    return tuple(os.fsdecode(part) for part in data.split(b"\0") if part)


def _under_root(path: str, roots: Iterable[Path]) -> tuple[Path, Path] | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        return None
    for root in roots:
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if relative.parts and ".." not in relative.parts:
            return root, relative
    return None


def _plausible_rom(path: str, roots: Iterable[Path]) -> tuple[Path, Path] | None:
    match = _under_root(path, roots)
    if match is None or path.startswith("-"):
        return None
    suffix = Path(path).suffix.lower()
    if suffix in _EXCLUDED_SUFFIXES or path.lower().endswith("_libretro.so"):
        return None
    return match



def _is_game_dge(executable: str) -> bool:
    if executable == _OPENBOR_DGE_PATH:
        return True
    return executable.startswith(_GAME_DGE_PREFIX) and executable.endswith(".dge")


def _humanize_emulator(identifier: str) -> str:
    known = _EMULATOR_NAMES.get(identifier)
    if known:
        return known
    words = identifier.replace("_", " ").replace("-", " ").split()
    return " ".join(word.upper() if word.casefold() in {"gba", "gb", "gbc", "sms", "pce"} else word.capitalize() for word in words) or identifier

def _core_id(path: str) -> str | None:
    name = Path(path).name
    suffix = "_libretro.so"
    return name[: -len(suffix)] if name.endswith(suffix) and len(name) > len(suffix) else None


def _derive_started_at(start_ticks: int, now: float | None = None) -> str | None:
    try:
        ticks_per_second = os.sysconf("SC_CLK_TCK")
        uptime = float(Path("/proc/uptime").read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError):
        return None
    wall_now = time.time() if now is None else now
    started = wall_now - uptime + (start_ticks / ticks_per_second)
    # Reject clocks before 2020, future starts, and impossible negative values.
    if started < 1_577_836_800 or started > wall_now + 5:
        return None
    return datetime.fromtimestamp(started).astimezone().isoformat(timespec="seconds")


def _system_identity(relative: Path, executable: str, argv: tuple[str, ...], config: DetectionConfig) -> tuple[str, str, str]:
    folder = relative.parts[0]
    if folder in config.aliases:
        system_id, name = config.aliases[folder]
        return folder, system_id, name
    folded = {key.casefold(): value for key, value in config.aliases.items()}
    if folder.casefold() in folded:
        system_id, name = folded[folder.casefold()]
        return folder, system_id, name
    exe_stem = Path(executable).name.removesuffix(".dge").lower()
    config_arg = next((Path(arg).stem for arg in argv if arg.lower().endswith(".cfg")), "")
    core_arg = next((_core_id(arg) for arg in argv if _core_id(arg)), None)
    hints = " ".join((folder, exe_stem, config_arg, core_arg or "")).casefold()
    for alias, (system_id, name) in config.aliases.items():
        if alias.casefold() in hints or system_id.casefold() in hints:
            return folder, system_id, name
    conservative_id = re.sub(r"[^a-z0-9]+", "_", folder.casefold()).strip("_") or "unknown"
    return folder, conservative_id, folder


def _retroarch_regions(pid: int, proc_root: Path) -> tuple[str | None, list[tuple[int, int]]]:
    """Return the mapped core and bounded writable-private regions to scan."""
    core_path: str | None = None
    regions: list[tuple[int, int]] = []
    try:
        lines = (proc_root / str(pid) / "maps").read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return None, regions
    for line in lines:
        parts = line.split(None, 5)
        if len(parts) < 2:
            continue
        address, permissions = parts[0], parts[1]
        mapped = parts[5] if len(parts) > 5 else ""
        if mapped.endswith("_libretro.so"):
            core_path = mapped
        if not permissions.startswith("rw") or "p" not in permissions:
            continue
        if mapped.startswith("/dev/") or mapped.startswith("/mnt/mmc/Roms/"):
            continue
        try:
            left, right = address.split("-", 1)
            start, end = int(left, 16), int(right, 16)
        except ValueError:
            continue
        if 0 < end - start <= _RETROARCH_MAX_REGION:
            regions.append((start, end))
    return core_path, regions


@lru_cache(maxsize=8)
def _rom_prefix_patterns(roots: tuple[Path, ...]) -> tuple[re.Pattern[bytes], ...]:
    patterns = []
    for root in roots:
        prefix = re.escape(os.fsencode(str(root).rstrip("/") + "/"))
        patterns.append(re.compile(prefix + rb"[ -~]{1,512}"))
    return tuple(patterns)


def _memory_rom_candidates(data: bytes, config: DetectionConfig) -> list[str]:
    """Extract complete existing ROM paths while rejecting patch/save derivatives."""
    results: list[str] = []
    for pattern in _rom_prefix_patterns(config.rom_roots):
        for match in pattern.finditer(data):
            text = os.fsdecode(match.group(0)).rstrip(" \t,;:)]}")
            candidate = text
            while candidate:
                if _plausible_rom(candidate, config.rom_roots) is not None and os.path.isfile(candidate):
                    if candidate not in results:
                        results.append(candidate)
                    break
                candidate = candidate[:-1]
    return results


def _retroarch_memory_content(record: ProcessRecord, config: DetectionConfig, proc_root: Path) -> tuple[str | None, str | None]:
    """Find live RetroArch content from bounded readable process memory.

    TF1 playlist launches omit content from cmdline and close the ROM descriptor.
    The active core and ROM path remain adjacent in writable private memory. A
    candidate is accepted only when the exact mapped core path occurs in the
    same bounded window, preventing history and playlist strings from winning.
    """
    core_path, regions = _retroarch_regions(record.pid, proc_root)
    if core_path is None or not regions:
        return None, None
    cache_key = (record.pid, record.start_ticks)
    cached_content = _RETROARCH_CONTENT_CACHE.get(cache_key)
    if cached_content is not None:
        cached_core, cached_rom = cached_content
        # A live RetroArch process keeps the same content for its lifetime, and
        # the session identity already treats rom_path as fixed per (pid,
        # start_ticks). Once the content is resolved, re-confirm only that the
        # ROM still exists and skip the bounded-but-costly full memory rescan on
        # every poll while the same process keeps running.
        if os.path.isfile(cached_rom):
            return cached_core, cached_rom
        _RETROARCH_CONTENT_CACHE.pop(cache_key, None)
    core_bytes = os.fsencode(core_path)
    cached_region = _RETROARCH_REGION_CACHE.get(cache_key)
    if cached_region in regions:
        regions = [cached_region] + [region for region in regions if region != cached_region]
    scores: dict[str, tuple[int, tuple[int, int]]] = {}
    scanned = 0
    try:
        memory = (proc_root / str(record.pid) / "mem").open("rb", buffering=0)
    except OSError:
        return _core_id(core_path), None
    with memory:
        for start, end in regions:
            position = start
            previous = b""
            while position < end and scanned < _RETROARCH_SCAN_LIMIT:
                amount = min(_RETROARCH_CHUNK, end - position, _RETROARCH_SCAN_LIMIT - scanned)
                try:
                    memory.seek(position)
                    chunk = memory.read(amount)
                except (OSError, ValueError):
                    break
                if not chunk:
                    break
                window = previous + chunk
                if core_bytes in window and any(os.fsencode(str(root).rstrip("/") + "/") in window for root in config.rom_roots):
                    for rom in _memory_rom_candidates(window, config):
                        score = 100
                        stem = os.fsencode(Path(rom).stem)
                        score += min(window.count(os.fsencode(rom)), 5) * 10
                        for suffix in (b".bps", b".cht", b".ips", b".ups", b".xdelta"):
                            if stem + suffix in window:
                                score += 3
                        previous_score = scores.get(rom)
                        if previous_score is None or score > previous_score[0]:
                            scores[rom] = (score, (start, end))
                previous = window[-_RETROARCH_OVERLAP:]
                position += len(chunk)
                scanned += len(chunk)
    if not scores:
        return _core_id(core_path), None
    best, (_, best_region) = sorted(scores.items(), key=lambda item: (-item[1][0], item[0]))[0]
    core_id = _core_id(core_path)
    _RETROARCH_REGION_CACHE.clear()
    _RETROARCH_REGION_CACHE[cache_key] = best_region
    _RETROARCH_CONTENT_CACHE.clear()
    _RETROARCH_CONTENT_CACHE[cache_key] = (core_id, best)
    return core_id, best


def normalize_process(record: ProcessRecord, config: DetectionConfig, proc_root: Path = Path("/proc")) -> SessionCandidate | None:
    exe_name = Path(record.executable).name
    if exe_name == "mcuCtrl.dge":
        return None
    rom: str | None = None
    core: str | None = None
    emulator: str
    if Path(record.executable) == config.retroarch_executable:
        emulator = "retroarch"
        for index, arg in enumerate(record.argv[:-1]):
            if arg == "-L":
                core = _core_id(record.argv[index + 1])
                break
        for arg in reversed(record.argv[1:]):
            if _plausible_rom(arg, config.rom_roots):
                rom = arg
                break
        if rom is None:
            memory_core, memory_rom = _retroarch_memory_content(record, config, proc_root)
            core = memory_core or core
            rom = memory_rom
    elif exe_name.endswith(".dge") and _is_game_dge(record.executable):
        emulator_id = exe_name[: -len(".dge")]
        emulator = _humanize_emulator(emulator_id)
        # XMAME's verified TF1 layout passes directory and filename separately.
        if emulator_id.casefold().startswith("xmame") and len(record.argv) >= 3:
            left, right = record.argv[1], record.argv[2]
            if Path(left).is_absolute() and not Path(right).is_absolute():
                joined = str(Path(left) / right)
                if _plausible_rom(joined, config.rom_roots):
                    rom = joined
        if rom is None:
            for arg in record.argv[1:]:
                if _plausible_rom(arg, config.rom_roots):
                    rom = arg
                    break
        if rom is None:
            for left, right in zip(record.argv[1:], record.argv[2:]):
                if Path(left).is_absolute() and not Path(right).is_absolute():
                    joined = str(Path(left) / right)
                    if _plausible_rom(joined, config.rom_roots):
                        rom = joined
                        break
    else:
        return None
    if rom is None:
        return None
    matched = _plausible_rom(rom, config.rom_roots)
    if matched is None:
        return None
    root, relative = matched
    folder, system_id, system_name = _system_identity(relative, record.executable, record.argv, config)
    return SessionCandidate(
        pid=record.pid,
        process_start_ticks=record.start_ticks,
        executable=record.executable,
        rom_path=rom,
        rom_root=str(root),
        system_folder=folder,
        system_id=system_id,
        system_name=system_name,
        emulator=emulator,
        core=core,
        rom_file=Path(rom).name,
        started_at=_derive_started_at(record.start_ticks),
    )


def inspect_process(
    pid: int,
    proc_root: Path = Path("/proc"),
    retroarch_executable: Path = Path("/mnt/vendor/deep/retro/retroarch"),
) -> ProcessRecord | None:
    base = f"{os.fspath(proc_root)}/{pid}"
    try:
        executable = os.fsdecode(os.readlink(base + "/exe"))
        if executable != os.fspath(retroarch_executable) and not _is_game_dge(executable):
            return None
        with open(base + "/cmdline", "rb") as handle:
            argv = decode_cmdline(handle.read())
        if not argv:
            return None
        with open(base + "/stat", "rb") as handle:
            start_ticks = parse_start_ticks(handle.read())
        return ProcessRecord(pid, executable, argv, start_ticks)
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError, ValueError):
        return None


def session_still_active(
    current: SessionCandidate,
    retroarch_executable: Path = Path("/mnt/vendor/deep/retro/retroarch"),
    proc_root: Path = Path("/proc"),
) -> bool:
    """Cheaply confirm the exact process instance behind a session is still alive.

    While a game keeps running, candidate selection already keeps the current
    session whenever its process is still present, so re-confirming just this one
    pid is behaviourally identical to a full ``/proc`` walk but far cheaper: it
    reads only this process's ``exe`` link and ``stat`` line. The executable and
    start-time together identify the process instance and guard against pid
    reuse. Any mismatch or missing file falls back to a full scan.
    """
    base = f"{os.fspath(proc_root)}/{current.pid}"
    try:
        if os.fsdecode(os.readlink(base + "/exe")) != current.executable:
            return False
        with open(base + "/stat", "rb") as handle:
            return parse_start_ticks(handle.read()) == current.process_start_ticks
    except (OSError, ValueError):
        return False


def scan_candidates(config: DetectionConfig, proc_root: Path = Path("/proc")) -> list[SessionCandidate]:
    candidates: list[SessionCandidate] = []
    try:
        scanner = os.scandir(os.fspath(proc_root))
    except OSError:
        return candidates
    with scanner:
        for entry in scanner:
            name = entry.name
            if not name.isdigit():
                continue
            record = inspect_process(int(name), proc_root, config.retroarch_executable)
            if record is None:
                continue
            candidate = normalize_process(record, config, proc_root)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def select_candidate(candidates: Iterable[SessionCandidate], current: SessionCandidate | None = None) -> SessionCandidate | None:
    items = list(candidates)
    if current is not None:
        for item in items:
            if item.identity == current.identity:
                return item
    if not items:
        return None
    # Newest process first; remaining keys make ties deterministic.
    return sorted(items, key=lambda item: (-item.process_start_ticks, item.pid, item.rom_path, item.executable))[0]


def read_power_mode(path: Path) -> PowerMode:
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return PowerMode.UNKNOWN
    if value == "1":
        return PowerMode.USB
    if value == "0":
        return PowerMode.BATTERY
    return PowerMode.UNKNOWN


def next_interval(config: DetectionConfig, playing: bool, power_reader: Callable[[Path], PowerMode] = read_power_mode) -> float:
    if playing:
        return config.poll.playing_seconds
    mode = power_reader(config.power_online_path)
    if mode is PowerMode.USB:
        return config.poll.idle_usb_seconds
    if mode is PowerMode.BATTERY:
        return config.poll.idle_battery_seconds
    return config.poll.unknown_power_seconds
