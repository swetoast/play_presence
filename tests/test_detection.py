from __future__ import annotations

import os
from pathlib import Path

import pytest

from rg40xx_game_presence.config import DetectionConfig, PollConfig
from rg40xx_game_presence.detection import (
    PowerMode,
    ProcessRecord,
    SessionCandidate,
    decode_cmdline,
    inspect_process,
    next_interval,
    normalize_process,
    parse_start_ticks,
    read_power_mode,
    select_candidate,
)


def stat_line(comm: str, start_ticks: object = 123456) -> str:
    # fields 3 through 21, then field 22
    return f"99 ({comm}) " + " ".join(["S"] + ["0"] * 18 + [str(start_ticks)] + ["0"] * 4)


@pytest.mark.parametrize("comm", ["retroarch", "game process", "has ) char", "has )) many"])
def test_stat_field_22_with_difficult_comm(comm: str) -> None:
    assert parse_start_ticks(stat_line(comm)) == 123456


def test_stat_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_start_ticks("12 broken")
    with pytest.raises(ValueError):
        parse_start_ticks("12 (x) S 0")
    with pytest.raises(ValueError):
        parse_start_ticks(stat_line("x", "nope"))


def test_cmdline_is_null_split_and_surrogate_safe() -> None:
    result = decode_cmdline(b"./gba_emu.dge\0/mnt/mmc/Roms/GBA/Game Name.gba.zip\0bad\xffname\0")
    assert result[1].endswith("Game Name.gba.zip")
    assert "\udcff" in result[2]


def base_config() -> DetectionConfig:
    return DetectionConfig()


def test_retroarch_normalization() -> None:
    record = ProcessRecord(10, "/mnt/vendor/deep/retro/retroarch", (
        "/mnt/vendor/deep/retro/retroarch", "-c", "/.config/retroarch/retroarch_N64.cfg",
        "-L", "/mnt/vendor/deep/retro/cores/parallel_n64_libretro.so",
        "/mnt/mmc/Roms/N64/007 - GoldenEye (Europe).n64.zip",
    ), 100)
    item = normalize_process(record, base_config())
    assert item is not None
    assert item.emulator == "retroarch"
    assert item.core == "parallel_n64"
    assert item.system_id == "n64"
    assert item.rom_file == "007 - GoldenEye (Europe).n64.zip"


def test_contentless_retroarch_rejected() -> None:
    record = ProcessRecord(10, "/mnt/vendor/deep/retro/retroarch", (
        "/mnt/vendor/deep/retro/retroarch", "-L", "/x/core_libretro.so"
    ), 100)
    assert normalize_process(record, base_config()) is None


def test_standard_dge_and_helper_exclusion() -> None:
    record = ProcessRecord(11, "/mnt/vendor/bin/game/gba/gba_emu.dge", ("./gba_emu.dge", "/mnt/mmc/Roms/GBA/Test.gba.zip"), 101)
    item = normalize_process(record, base_config())
    assert item is not None and item.emulator == "Game Boy Advance Emulator" and item.system_id == "gba"
    helper = ProcessRecord(12, "/mnt/vendor/bin/mcuCtrl.dge", ("./mcuCtrl.dge", "/mnt/mmc/Roms/GBA/Test.gba.zip"), 102)
    assert normalize_process(helper, base_config()) is None


def test_xmame_reconstruction_and_subfolder() -> None:
    record = ProcessRecord(20, "/mnt/vendor/bin/game/xmame/xmame.dge", (
        "./xmame.dge", "/mnt/mmc/Roms/MAME/sub", "simpsons.zip"
    ), 200)
    item = normalize_process(record, base_config())
    assert item is not None
    assert item.rom_path == "/mnt/mmc/Roms/MAME/sub/simpsons.zip"
    assert item.system_id == "mame"


def test_unknown_dge_without_safe_path_rejected() -> None:
    record = ProcessRecord(20, "/tmp/unknown.dge", ("./unknown.dge", "game.zip"), 200)
    assert normalize_process(record, base_config()) is None


def candidate(pid: int, ticks: int, rom: str) -> SessionCandidate:
    return SessionCandidate(pid, ticks, "/tmp/gba.dge", rom, "/mnt/mmc/Roms", "GBA", "gba", "Game Boy Advance", "gba", None, Path(rom).name, None)


def test_candidate_selection_prefers_current_then_newest() -> None:
    old = candidate(1, 100, "/mnt/mmc/Roms/GBA/A.zip")
    new = candidate(2, 200, "/mnt/mmc/Roms/GBA/B.zip")
    assert select_candidate([new, old], old) == old
    assert select_candidate([old, new]) == new


def test_power_and_intervals(tmp_path: Path) -> None:
    power = tmp_path / "online"
    power.write_text("1\n", encoding="ascii")
    assert read_power_mode(power) is PowerMode.USB
    power.write_text("0", encoding="ascii")
    assert read_power_mode(power) is PowerMode.BATTERY
    power.write_text("bad", encoding="ascii")
    assert read_power_mode(power) is PowerMode.UNKNOWN
    config = DetectionConfig(power_online_path=power, poll=PollConfig(5, 6, 11, 7))
    assert next_interval(config, True, lambda _: (_ for _ in ()).throw(AssertionError())) == 5
    assert next_interval(config, False, lambda _: PowerMode.USB) == 6
    assert next_interval(config, False, lambda _: PowerMode.BATTERY) == 11
    assert next_interval(config, False, lambda _: PowerMode.UNKNOWN) == 7


def test_procfs_race_is_quiet(tmp_path: Path) -> None:
    assert inspect_process(999, tmp_path) is None


@pytest.mark.parametrize(("executable", "rom", "emulator", "system_id", "system_name"), [
    ("/mnt/vendor/bin/game/fbasdl/fbasdl.dge", "/mnt/mmc/Roms/FBNEO/aliens.zip", "FinalBurn Alpha SDL", "fbneo", "Arcade (NeoGeo)"),
    ("/mnt/vendor/bin/game/gbc/gbcgb_emu.dge", "/mnt/mmc/Roms/GBC/1942 (USA).gbc.zip", "Game Boy / Game Boy Color Emulator", "gbc", "Game Boy Color"),
    ("/mnt/vendor/bin/game/fc/fc_emu.dge", "/mnt/mmc/Roms/FC/game.zip", "Nintendo Entertainment System Emulator", "nes", "Nintendo Entertainment System"),
    ("/mnt/vendor/bin/game/md/md_emu.dge", "/mnt/mmc/Roms/MD/game.zip", "Mega Drive Emulator", "genesis", "Mega Drive"),
    ("/mnt/vendor/bin/game/temper/pce.dge", "/mnt/mmc/Roms/PCE/game.zip", "PC Engine Emulator", "pce", "PC Engine"),
])
def test_known_game_dge_normalization(executable, rom, emulator, system_id, system_name):
    record = ProcessRecord(50, executable, ("./" + Path(executable).name, rom), 500)
    item = normalize_process(record, base_config())
    assert item is not None
    assert (item.emulator, item.system_id, item.system_name) == (emulator, system_id, system_name)


def test_non_game_dge_utilities_are_rejected():
    for executable in (
        "/mnt/vendor/bin/charg.dge", "/mnt/vendor/bin/music/ap.dge",
        "/mnt/vendor/bin/video/vp.dge", "/mnt/vendor/bin/ndsCtrl.dge",
        "/mnt/vendor/bin/portsCtrl.dge",
    ):
        record = ProcessRecord(60, executable, (Path(executable).name, "/mnt/mmc/Roms/GBA/Test.zip"), 600)
        assert normalize_process(record, base_config()) is None


def test_future_game_dge_uses_humanized_fallback():
    executable = "/mnt/vendor/bin/game/future/new_core_emu.dge"
    record = ProcessRecord(70, executable, ("./new_core_emu.dge", "/mnt/mmc/Roms/GBA/Test.zip"), 700)
    item = normalize_process(record, base_config())
    assert item is not None and item.emulator == "New Core Emu"


def test_openbor_is_accepted_outside_game_root():
    executable = "/mnt/vendor/deep/openBOR/OpenBOR.dge"
    record = ProcessRecord(80, executable, ("./OpenBOR.dge", "/mnt/mmc/Roms/OPENBOR/Test.pak"), 800)
    item = normalize_process(record, base_config())
    assert item is not None
    assert item.emulator == "OpenBOR"
    assert item.system_id == "openbor"

def _write_sparse_memory(path: Path, offset: int, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.seek(offset)
        handle.write(payload)


def test_playlist_retroarch_memory_detection_prefers_live_same_core_cluster(tmp_path: Path) -> None:
    from rg40xx_game_presence import detection
    proc = tmp_path / "proc"
    base = proc / "10"
    base.mkdir(parents=True)
    rom_root = tmp_path / "Roms"
    system = rom_root / "MAME"
    system.mkdir(parents=True)
    stale = system / "avsp.zip"
    active = system / "ffight2b.zip"
    stale.write_bytes(b"stale")
    active.write_bytes(b"active")
    core = "/mnt/vendor/deep/retro/cores/mame2010_libretro.so"
    start = 0x1000
    payload = (
        core.encode() + b"\0" + str(active).encode() + b"\0" +
        str(active.with_suffix(".bps")).encode() + b"\0" +
        str(active.with_suffix(".cht")).encode() + b"\0"
    )
    _write_sparse_memory(base / "mem", start, payload)
    (base / "maps").write_text(
        f"{start:x}-{start + 0x4000:x} rw-p 00000000 00:00 0 [heap]\n"
        "7000-8000 r-xp 00000000 00:00 0 " + core + "\n",
        encoding="ascii",
    )
    config = DetectionConfig(rom_roots=(rom_root,))
    record = ProcessRecord(10, str(config.retroarch_executable), (str(config.retroarch_executable), "-c", "/.config/retroarch/retroarch.cfg"), 100)
    item = detection.normalize_process(record, config, proc)
    assert item is not None
    assert item.rom_path == str(active)
    assert item.core == "mame2010"
    assert item.emulator == "retroarch"


def test_playlist_retroarch_memory_detection_fails_closed_without_core_pair(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    base = proc / "10"
    base.mkdir(parents=True)
    rom_root = tmp_path / "Roms"
    system = rom_root / "MAME"
    system.mkdir(parents=True)
    stale = system / "avsp.zip"
    stale.write_bytes(b"stale")
    start = 0x1000
    _write_sparse_memory(base / "mem", start, str(stale).encode())
    (base / "maps").write_text(f"{start:x}-{start + 0x4000:x} rw-p 00000000 00:00 0 [heap]\n", encoding="ascii")
    config = DetectionConfig(rom_roots=(rom_root,))
    record = ProcessRecord(10, str(config.retroarch_executable), (str(config.retroarch_executable), "-c", "/.config/retroarch/retroarch.cfg"), 100)
    assert normalize_process(record, config, proc) is None
