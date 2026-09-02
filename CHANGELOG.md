# Changelog

## 0.6.9 - 2026-09-02

### Changed
- Locked MQTT state serialization to the approved game-focused field set.
- Prevented future internal dataclass fields from being published automatically.
- Added regression coverage that rejects version, detector, filesystem-path, source, battery, CPU, and memory fields from the normal MQTT state.
- Updated the README with the exact MQTT state contract in natural language.

## 0.6.8 - 2026-09-02

### Added
- Conservative cleanup for device ROM filename patterns, including stacked ROM/archive extensions, recognized trailing dump metadata, whitespace normalization, and trailing articles.
- Exact matching `gamelist.xml` `<image>` resolution and nested mirrored `images/` fallback.
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
- Preserved the public compatibility helpers and restored the complete phase regression modules.

### Packaging
- Clarified platform scope in the README: Anbernic devices running Linux, with RG40XX V as the currently verified model.
- Reworked README as a concise user-facing project introduction with highlights, one-line installation, usage, architecture, security, troubleshooting, documentation links, and contribution guidance. No emoji are used.
- Added a root-only GitHub bootstrap installer with curl/wget fallback, temporary extraction, source validation, secure first-install MQTT password prompt, cleanup, version output, and service-status output.
- Completed the Play Presence rename for the package, command, installation paths, runtime path, and systemd unit. Added migration from previous installed paths and service names while preserving MQTT topics and Home Assistant unique IDs.
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
- Validation continuity, PID/restart evidence, valid-sample counts, completeness, and interruption reasons.
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
- Expanded system aliases and utility/helper rejection.

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
