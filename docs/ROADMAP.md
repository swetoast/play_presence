# Development roadmap

## Roadmap rules

- The approved design plus explicit 0.8 artwork revision is authoritative.
- `[x]` means Verified or explicitly Not applicable.
- Implemented means source exists but hardware verification may remain incomplete.
- Hardware-dependent items stay unchecked until device evidence is reviewed.
- Every project revision updates this file and `CHANGELOG.md`.

## Phase 0: Platform verification

- [x] P0-PLAT-001 Python-only two-stage probe interface
- [x] P0-PLAT-002 Root requirement for privileged preparation
- [x] P0-PLAT-003 `/opt` ordinary-reboot persistence
- [x] P0-PLAT-004 `/etc` ordinary-reboot persistence
- [x] P0-PLAT-005 Persistent custom systemd unit location
- [x] P0-PLAT-006 Enabled and active custom unit after reboot
- [x] P0-PLAT-007 Volatile `/run`
- [x] P0-PLAT-008 USB-online sysfs availability
- [x] P0-PLAT-009 USB-connected and disconnected values
- [x] P0-PLAT-010 Cheap non-blocking power reads
- [x] P0-PLAT-011 Python RSS/PSS measurement
- [x] P0-PLAT-012 Python plus Paho memory measurement
- [x] P0-PLAT-013 Paho network-thread lifecycle
- [x] P0-PLAT-014 Keepalive suitability under adaptive polling
- [x] P0-PLAT-015 Bounded atomic secret-safe JSON
- [x] P0-PLAT-016 Probe cleanup
- [x] P0-PLAT-017 Persistence claim limited to ordinary reboot

**Phase 0 gate: Verified from prior TF1 hardware work.**

## Phase 1: Process detector

- [x] P1-CONF-001 Strict configuration and secret-safe errors
- [x] P1-PROC-001 Direct numeric procfs enumeration
- [x] P1-PROC-002 Direct executable, command-line, and stat reading
- [x] P1-PROC-003 Procfs race tolerance
- [x] P1-PROC-004 Correct stat field-22 parsing
- [x] P1-DETECT-001 RetroArch detection and core normalization
- [x] P1-DETECT-002 Standard system `.dge` detection
- [x] P1-DETECT-003 XMAME path reconstruction
- [x] P1-DETECT-004 Permanent `mcuCtrl.dge` exclusion
- [x] P1-DETECT-005 Safe rejection of unknown layouts
- [x] P1-DETECT-006 Spaces, punctuation, Unicode, and non-UTF-8 preservation
- [x] P1-DETECT-007 Stable system aliases
- [x] P1-STATE-001 PID/start-ticks/path/executable session identity
- [x] P1-STATE-002 Deterministic candidate selection
- [x] P1-STATE-003 Immediate play and game-change transitions
- [x] P1-STATE-004 Confirmed playing-to-idle transition
- [x] P1-STATE-005 Restart recovery of current session
- [x] P1-STATE-006 Implausible-clock handling
- [x] P1-POWER-001 5/5/10/5 polling
- [x] P1-POWER-002 Internal-only power state

**Phase 1 gate: Verified.**

## Phase 2: MQTT presence

- [x] P2-MQTT-001 Protected password-file loading
- [x] P2-MQTT-002 Persistent Paho MQTT 1.5.1 client with QoS 1
- [x] P2-MQTT-003 Retained offline Last Will and online availability
- [x] P2-MQTT-004 Retained reduced state only on change
- [x] P2-MQTT-005 Bounded reconnect delay
- [x] P2-MQTT-006 Latest-state-only outage retention
- [x] P2-MQTT-007 Recovery publications after connection
- [x] P2-MQTT-008 Rate-limited errors

**Phase 2 gate: Verified.**

## Phase 3: Home Assistant discovery

- [x] P3-HA-001 Current-game sensor
- [x] P3-HA-002 Playing binary sensor
- [x] P3-HA-003 Optional system sensor
- [x] P3-HA-004 Shared device identity
- [x] P3-HA-005 Null-safe templates
- [x] P3-HA-006 Public-field boundary
- [x] P3-HA-007 Retained discovery recovery

**Phase 3 gate: Verified.**

## Phase 4: Metadata resolution

- [x] P4-META-001 Active system `gamelist.xml`
- [x] P4-META-002 Exact relative lookup key
- [x] P4-META-003 Incremental early-stop parser
- [x] P4-META-004 Matching path and title extraction
- [x] P4-META-005 Bounded manual overrides
- [x] P4-META-006 Conservative stacked-extension fallback
- [x] P4-META-007 Non-blocking metadata failure handling
- [x] P4-META-008 Session-change-only resolution
- [x] P4-META-009 Scraped and unscraped MAME handling
- [x] P4-META-010 No provider, DAT, hashing, or scraper duplication

**Phase 4 gate: Verified.**

## Phase 5: Service and performance validation

- [x] P5-SVC-001 Approved deployment layout implemented
- [x] P5-SVC-002 Protected configuration and password files implemented
- [ ] P5-SVC-003 Ordinary reboot: verified after bounded recovery; clean zero-restart evidence remains open
- [ ] P5-SVC-004 Wi-Fi and broker outage matrix: Wi-Fi outage and recovery confirmed; broker-outage observation still pending
- [x] P5-SVC-005 Supervision: graceful restart verified, and corrected unexpected-termination confirmed on device (0.7.0): force-kill of the main PID recovered to active with NRestarts +1
- [ ] P5-SVC-006 Permanent invalid configuration rate-limit: unit directives reviewed (static review complete); device rate-limit observation pending
- [x] P5-PERF-001 Idle CPU device evidence — confirmed on device (0.7.0): idle CPU 0.0416% over a 120 s window (within the 1.0% negligible limit), RSS 26.0 MiB (under the 30 MiB preferred limit), RSS/PSS growth zero
- [ ] P5-PERF-002 Stable gameplay CPU device evidence recorded for 0.6.7 but 0.6.8 artwork snapshot pending
- [x] P5-PERF-003 Preferred RSS and 40 MiB ceiling verified for 0.6.7 without artwork
- [ ] P5-PERF-004 Extended no-growth acceptance remains open; no additional one-hour run requested
- [x] P5-SEC-001 Persistent write: static review complete (no steady-state persistent writes; only the tmpfs `/run` failure record) and confirmed on device (0.7.0): `write_bytes` 0 with `write_bytes_growth` 0 over the window
- [x] P5-SEC-002 Journald bounds: static review complete (no per-poll logging; warnings rate-limited) and resolved on device (0.7.0): journald is `Storage=none`, so nothing is persisted and there is no journal growth to bound; the `last-failure.json` runtime record covers post-incident debugging
- [x] P5-SEC-003 No inbound interface or remote control
- [ ] P5-SEC-004 Full transition/outage matrix: Wi-Fi outage/recovery and detection-transition cells confirmed on device (0.7.0, in live Home Assistant use); broker-outage cell still pending

### Historical Phase 5 corrections

- [x] P5-CORR-011 through 016: `.dge` runtime normalization and alias expansion
- [x] P5-CORR-017 through 018: Paho 1.5.1 graceful-shutdown correction
- [x] P5-CORR-019 through 024: evidence, installer rollback, MQTT recovery, and strict configuration consolidation
- [x] P5-CORR-025 through 028: bounded volatile failure diagnostics
- [x] P5-CORR-029 through 033: automatic evidence assessment
- [x] P5-CORR-034 through 037: RetroArch playlist-content memory correction and successful-region cache

### Version 0.6.7 device evidence

- [x] Installed version, configuration, service, MQTT baseline, and source tests
- [x] Idle state
- [x] DGE game state
- [x] RetroArch state across Gambatte and Snes9x
- [x] Different-core RetroArch transition
- [x] RetroArch return to idle
- [x] Graceful service restart
- [x] Broker reconnection
- [x] Battery operation and USB `0 -> 1`
- [x] Snapshot RSS below preferred and release limits
- [x] No ROM descriptor in snapshots
- [x] Corrected supervision observation - confirmed on device (0.7.0): force-kill recovered to active, NRestarts +1
- [ ] Corrected broker-outage observation
- [x] True same-core RetroArch switch in the consolidated matrix - confirmed on device (0.7.0): SFC-to-SFC switch updates the game with no stale title, in live Home Assistant use
- [x] Manual Wi-Fi outage and recovery — confirmed on device: the daemon reconnected after the Wi-Fi outage cleared
- [x] Journald evidence - resolved on device (0.7.0): journald `Storage=none`, nothing persisted, no journal growth to bound

### Version 0.6.8 title and artwork revision

- [x] P5-CORR-038 Conservative fallback title cleanup for verified filename classes
- [x] P5-CORR-039 Exact gamelist image and nested mirrored `images/` fallback
- [x] P5-CORR-040 Bounded artwork reads and containment checks
- [x] P5-CORR-041 Retained binary artwork, idle clearing, and reconnect restoration
- [x] P5-CORR-042 Home Assistant MQTT image discovery
- [x] P5-CORR-043 DGE and RetroArch detection preserved
- [x] P5-CORR-044 Verified aliases and strict configuration invariants preserved
- [x] P5-CORR-045 Signature validation and no-follow file opening
- [x] P5-CORR-046 Default artwork ceiling reduced to 2 MiB
- [x] P5-CORR-047 Latest state and artwork retried independently
- [x] P5-CORR-048 Clean package without caches, bytecode, or development inventories
- [x] P5-CORR-049 Restored phase regression modules and compatibility helper contracts
- [x] P5-CORR-050 Add a simple validated GitHub bootstrap installer while preserving the existing safe Python installer
- [x] P5-CORR-051 Complete the Play Presence package, command, path, runtime, and service rename with migration from previous installation names
- [x] P5-HW-ART-001 Title and artwork on TF1 with a valid local image - confirmed on device (0.7.0): renders in Home Assistant in live use
- [x] P5-HW-ART-002 Verify missing artwork clears stale Home Assistant artwork — confirmed: no stale image retained; with the device powered off the image entity reports Unavailable via the offline Last Will
- [x] P5-HW-ART-003 Short RSS snapshot with artwork loaded - confirmed on device (0.7.0): RSS 26.7 MiB with an SFC game and gamelist artwork loaded, under the 30 MiB preferred limit

**Phase 5 implementation status: Complete. Hardware status: Pending remaining device evidence.**

### Version 0.7.0 efficiency and audit revision

- [x] P5-EFF-001 Memoize resolved RetroArch content per process to avoid repeated memory scans while playing
- [x] P5-EFF-002 Confirm the current session by its own process instead of a full `/proc` walk while a game runs
- [x] P5-EFF-003 Scan `/proc` with `os.scandir`, string procfs paths, and string `.dge` matching; cache compiled ROM-path patterns
- [x] P5-EFF-004 Skip MQTT state serialization on polls with nothing pending
- [x] P5-CORR-052 Repair the bootstrap installer regression suite and mark the script executable
- [x] P5-CORR-053 Derive probe and validation output filenames from the project version
- [x] P5-CORR-054 Align the default MQTT client identifier and correct installer branding
- [x] P5-CORR-055 Lock latest-state access in the MQTT reconnect path
- [x] P5-CORR-056 Correct the documented Paho range and document the installer trust model
- [x] P5-CORR-057 Add regression coverage for procfs scanning, liveness reuse, and content memoization

## Release gate

- [ ] Every applicable roadmap item Verified or justified Not applicable
- [x] Corrected complete source suite passes
- [x] Complete ZIP passes clean extraction and tests
- [ ] Remaining hardware acceptance completed
- [ ] Version 1.0.0 acceptance criteria completed
