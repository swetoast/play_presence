# Play Presence design

- Design version: 0.8
- Project implementation version: 0.6.8
- Status: Approved 0.7 baseline with explicit bounded artwork revision
- Target: Anbernic RG40XX V
- Firmware: TF1 stock firmware
- Integration: Home Assistant through MQTT
- External API: None

## Purpose

The daemon is a small, headless, read-only service that detects the game currently running through Linux procfs, resolves a display title from the active system `gamelist.xml`, and publishes a reduced retained state to MQTT. RetroArch and system-specific `.dge` emulators are equal first-class detection paths. `mcuCtrl.dge` is always ignored.

The daemon exposes no listening service, accepts no remote control, performs no runtime ROM hashing or scraping, retains no session history, writes nothing to ROM storage, and keeps CPU, memory, queues, caches, logs, and persistent writes bounded.

## Platform baseline

```text
Architecture: aarch64
OS: Ubuntu 22.04
Kernel: Linux 4.9.170
Python: 3.10.12
Memory: 973 MiB, no swap
ROM root: /mnt/mmc/Roms
Broker: 10.0.0.5:1883
Paho: 1.5.1
MQTT: 3.1.1
```

Phase 0 previously verified the persistent `/opt`, `/etc`, and systemd layout, volatile `/run`, power sysfs, Python/Paho environment, and ordinary-reboot installation viability. Claims remain limited to the tested TF1 installation and ordinary reboot.

## Detection contract

The detector uses Python filesystem APIs to inspect `/proc/<pid>/exe`, `/proc/<pid>/cmdline`, `/proc/<pid>/stat`, and bounded RetroArch memory regions. It never invokes shell process tools. Command lines are read as null-separated bytes with surrogate-safe decoding. Procfs disappearance races are normal and quiet.

Session identity is:

```text
PID + process start ticks + ROM path + emulator executable
```

Supported launch paths:

- verified game `.dge` runtimes under `/mnt/vendor/bin/game/`
- OpenBOR at `/mnt/vendor/deep/openBOR/OpenBOR.dge`
- XMAME split path arguments
- RetroArch command-line content
- contentless TF1 RetroArch playlist sessions where an exact mapped core and real ROM path occur in the same writable-private memory window

The detector preserves bounded fallback scanning and caches only the last successful memory region for the current RetroArch process identity.

## State transitions

- Idle to playing: immediate
- Game to game: immediate, no synthetic idle
- Playing to idle: two consecutive absent scans
- Replacement game cancels pending idle
- Daemon restart during play recovers the existing process identity
- Title and artwork resolution occur only after session identity change

## Adaptive polling

```text
Playing: 5 seconds
Idle on USB: 5 seconds
Idle on battery: 10 seconds
Unknown power: 5 seconds
```

Power state only chooses the next idle interval and is never published.

## Title contract

For a ROM under `<root>/<system-folder>/`, the daemon matches:

```text
./ + ROM path relative to the system folder
```

Resolution order:

1. Matching non-empty `gamelist.xml` `<name>`
2. Bounded daemon-owned manual override
3. Conservative filename fallback

Fallback cleanup repeatedly removes known archive and ROM extensions, removes only recognized trailing region/language/revision/dump metadata, normalizes underscores and whitespace, and moves a trailing `, The`, `, A`, or `, An` to the front. Unknown parentheses and collection punctuation remain title content.

## Artwork revision

After an exact active-ROM match, the daemon may read the same entry's `<image>` value. If no usable `<image>` exists, it checks the deterministic mirrored system `images/` location, preserving nested relative ROM directories.

Artwork rules:

- read-only
- session-change-only
- JPEG, PNG, or WebP
- signature and extension must agree
- regular files only
- symlinks rejected
- resolved parent must remain inside the active system directory
- default maximum size 2 MiB
- no download, conversion, resizing, cache catalogue, or manifest consumption

The daemon keeps only the latest current artwork bytes. Missing or invalid artwork is a normal no-artwork state.

## Public state

Playing state contains:

```json
{
  "state": "playing",
  "game": "GoldenEye 007",
  "system": "Nintendo 64",
  "system_id": "n64",
  "emulator": "retroarch",
  "core": "parallel_n64",
  "rom_file": "007 - GoldenEye (Europe).n64.zip",
  "started_at": "2026-08-31T19:44:00+02:00",
  "artwork_available": true,
  "artwork_content_type": "image/jpeg"
}
```

PID, start ticks, absolute paths, power values, intervals, credentials, and artwork bytes remain outside JSON.

## MQTT and Home Assistant

The daemon uses one persistent Paho MQTT 1.5.1 client, MQTT 3.1.1, QoS 1, retained availability, retained state, and retained binary artwork.

```text
rg40xxv/availability
rg40xxv/state
rg40xxv/artwork
```

Only the latest public state and artwork are retained in application memory. State and artwork have separate pending flags. A transient publication rejection is retried on a later detector poll. Reconnect republishes discovery, availability, latest state, and latest artwork. Idle or missing artwork publishes an empty retained artwork payload.

Home Assistant discovery adds an MQTT image entity while preserving the current-game sensor, playing binary sensor, optional system sensor, stable identifiers, and shared device identity.

## Security and storage

The service runs as root for procfs access. Credentials remain in a protected file and never appear in arguments, logs, state, discovery, or validation results. The service connects outward only. No ROM-derived value is executed. Normal operation adds no persistent runtime write and ROM storage remains read-only inside the systemd sandbox.

## Performance acceptance

```text
Stable CPU: effectively 0.0%
Preferred RSS: <= 30 MiB
RSS ceiling: 40 MiB
Long-run memory growth: none
Routine process write growth: none
```

The 2 MiB artwork ceiling is a bound, not proof of device acceptance. A short TF1 snapshot with representative artwork remains required. No additional one-hour run is required unless a later runtime change invalidates existing evidence.

## Approved phases

- Phase 0: Platform verification
- Phase 1: Process detector
- Phase 2: MQTT presence
- Phase 3: Home Assistant discovery
- Phase 4: Metadata resolution
- Phase 5: Service and performance validation

The 0.6.8 work is an explicit revision inside Phase 5, not a new phase.


## Distribution and naming

The visible project name is **Play Presence**. Compatibility-sensitive internal identifiers remain unchanged in version 0.6.8: Python package, command entry point, installation directories, systemd unit filename, MQTT topics, retained discovery identifiers, and Home Assistant unique IDs.

The repository bootstrap `install.sh` performs no direct installation logic. It requires root, downloads the configured GitHub branch into volatile `/tmp`, validates the expected project files, invokes the existing Python installer, and removes temporary files. Configuration preservation, credential handling, staged replacement, rollback, systemd enablement, and service startup remain owned by `deploy/install.py`.
