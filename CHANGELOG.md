# Changelog

## Unreleased

### Performance
- Memoized resolved RetroArch content per live process so contentless playlist launches no longer re-scan bounded process memory on every poll; a running session now re-confirms only that its ROM still exists and reuses the cached core and ROM path until the process changes.
- Skipped the full `/proc` walk while a game keeps running: the detector re-confirms only the current session's own process (one `exe` link and `stat` read) and falls back to a full scan only when that process changes, since candidate selection already keeps the current session whenever its process is present. State transitions and the idle debounce are unchanged.
- Walked `/proc` with `os.scandir` and plain-string procfs paths instead of building a `Path` per entry, matched emulator `.dge` executables with string prefix checks instead of `Path.relative_to` exception flow, removed a dead per-process allocation and an unused compiled pattern, and cached the compiled ROM-path patterns per root set instead of recompiling them per scanned memory window.
- Made the MQTT poll-time retry skip work and JSON serialization entirely when nothing is pending, so idle and steady play no longer re-serialize the state on every poll.

### Fixed
- Updated the bootstrap installer regression test to match the current interactive `install.sh` (workspace path, `deploy/install.py` invocation, password handling) and added uninstall coverage; the suite no longer fails on a clean checkout.
- Marked `install.sh` executable in the repository.
- Derived the `probe verify` and `validate` default output filenames from the project version instead of hardcoded, drifting version strings.
- Aligned the default MQTT `client_id` to `play-presence` across the dataclass default, the loader fallback, and `config.example.json`, matching what the installer already writes.
- Corrected the installer success message branding to Play Presence.
- Captured the latest-state presence under the connection lock in the MQTT reconnect path instead of reading it unlocked.

### Documentation
- Corrected the supported Paho MQTT range to 1.5.x or 1.6.x (1.x callback API).
- Documented the installer trust model: integrity rests on GitHub TLS plus source-layout checks, with no separate signature or checksum, and noted the pinned-clone alternative.

## 0.6.9 - 2026-09-02

### Changed
- Renamed the Home Assistant device and discovery entities to Play Presence.
- Added the default entity IDs `sensor.play_presence_current_game`, `binary_sensor.play_presence_playing`, `sensor.play_presence_system`, and `image.play_presence_current_game_artwork`.
- Added retained discovery tombstones for the previous `rg40xxv_*` entities so Home Assistant can remove the old registrations during migration.
- Locked MQTT state serialization to the approved game-focused fields.
- Prevented internal diagnostic fields from being added to the normal MQTT state automatically.
- Updated and simplified the README with neutral examples, natural language, and a DRY structure.

### Validation
- Added regression coverage for the new Home Assistant device identity, entity IDs, legacy discovery cleanup, and exact MQTT state contract.
- Verified the complete automated test suite, source compilation, reported version, and release archive integrity.

## 0.6.8 - 2026-09-02

### Added
- Conservative cleanup for device ROM filename patterns, including stacked ROM and archive extensions, recognized trailing dump metadata, whitespace normalization, and trailing articles.
- Exact matching `gamelist.xml` `<image>` resolution and nested mirrored `images` fallback.
- Retained binary MQTT artwork publication and Home Assistant MQTT image discovery.
- Empty retained artwork on idle or missing artwork.
- Independent latest-state and latest-artwork retry after transient publication rejection.
- JPEG, PNG, and WebP signature verification.

### Security and performance
- Artwork must remain inside the active system directory.
- Symlinks, path escapes, unsupported types, signature mismatches, non-regular files, empty files, and oversized images are rejected.
- Default artwork size ceiling is 2 MiB.
- Artwork is read only after session identity changes and no media catalogue is retained.

### Compatibility
- Preserved verified 0.6.7 aliases, strict configuration validation, DGE detection, XMAME reconstruction, OpenBOR support, RetroArch command-line detection, and playlist-memory detection.
- Preserved public compatibility helpers and restored the complete phase regression modules.

### Packaging
- Clarified platform scope as Anbernic devices running Linux, with RG40XX V as the currently verified model.
- Added a root-only GitHub bootstrap installer with `curl` and `wget` support, temporary extraction, source validation, secure first-install MQTT password input, cleanup, version output, and service-status output.
- Completed the Play Presence rename for the package, command, installation paths, runtime path, and systemd unit.
- Added migration from previous installed paths and service names while preserving MQTT state and artwork topics.
- Excluded bytecode, pytest caches, and development filename inventories.
- Updated design, roadmap, validation, README, tests, and package version.

## 0.6.7 - 2026-09-01

### Added
- Bounded read-only RetroArch process-memory detection for TF1 playlist launches that omit the content path.
- Exact mapped libretro-core and existing ROM-path proximity validation.
- Successful-region caching per RetroArch process identity.
- Same-core live switch evidence for MAME 2010.

### Preserved
- Command-line RetroArch detection and all verified DGE paths.
- XMAME reconstruction, `mcuCtrl.dge` exclusion, metadata resolution, and MQTT state behavior.

## 0.6.6 - 2026-09-01

### Added
- Automatic Phase 5 assessment for continuity, growth-window usability, CPU, RSS limits, memory growth, process writes, ROM descriptors, and journal availability.
- Null results when evidence is unavailable or insufficient.

## 0.6.5 - 2026-09-01

### Added
- Bounded volatile fatal-error evidence under `/run/play-presence/last-failure.json`.
- Lifecycle phase labels and same-boot validation inclusion.
- Secret-safe failure records containing no messages, credentials, paths, arguments, or tracebacks.

## 0.6.4 - 2026-09-01

### Added
- Validation continuity, PID and restart evidence, valid-sample counts, completeness, and interruption reasons.
- Complete unknown-key rejection.
- MQTT recovery result checking.
- Installer restoration of previous systemd active and enabled state.

## 0.6.3 - 2026-09-01

### Fixed
- Replaced unsupported Paho 1.5.1 timed `wait_for_publish()` use with bounded `is_published()` polling.
- Restored clean SIGTERM handling.

## 0.6.2 - 2026-09-01

### Added
- Verified TF1 game-runtime `.dge` classification.
- OpenBOR exception.
- Friendly emulator names and generic future-runtime fallback.
- Expanded system aliases and utility or helper rejection.

## 0.6.1 - 2026-09-01

### Corrected
- Bounded MQTT shutdown and queueing.
- Strict configuration handling.
- Installer rollback, evidence continuity, timestamp formatting, and service hardening.

## 0.6.0 - 2026-09-01

### Added
- Production systemd unit and Python installer.
- Protected configuration and credentials.
- Staged deployment and rollback.
- Bounded Phase 5 validation and resource evidence.

## 0.5.0 - 2026-09-01

### Added
- Exact per-system `gamelist.xml` title resolution.
- Flat and nested lookup keys.
- Incremental XML parsing, bounded overrides, conservative fallback, and metadata regressions.

## 0.4.0 - 2026-09-01

### Added
- Home Assistant MQTT discovery for current game, playing, and optional system entities.
- Shared device identity and null-safe templates.

## 0.3.0 - 2026-09-01

### Added
- Persistent Paho MQTT transport, retained availability and state, latest-only outage state, reconnect recovery, rate limiting, and public-state boundary.

## 0.2.0 - 2026-09-01

### Added
- Strict configuration, direct procfs scanning, RetroArch and DGE normalization, stable sessions, adaptive polling, and state-machine tests.

## 0.1.0 - 2026-09-01

### Added
- Package entry point, Phase 0 platform probes, atomic bounded JSON output, cleanup, and initial roadmap.
