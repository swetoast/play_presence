# Validation record

## Project

- Version: 0.6.9
- Target: Anbernic RG40XX V
- Firmware: TF1 stock firmware
- Status: Phase 5 implementation complete; remaining hardware acceptance pending

## Phase 0 evidence

The accepted TF1 baseline includes writable persistent system locations, custom systemd startup viability, volatile `/run`, the `axp2202-usb/online` interface, and the installed Python/Paho environment. Claims remain limited to ordinary reboot persistence on the tested TF1 installation.

## Phase 1 automated validation

Coverage includes strict configuration, secret-safe errors, stat field 22, malformed procfs, null-separated command lines, non-UTF-8 bytes, RetroArch and DGE detection, XMAME, helper exclusion, safe unknown-layout rejection, stable candidate selection, procfs races, power parsing, polling intervals, immediate transitions, confirmed idle, pending-idle cancellation, timestamp refresh, and initial idle emission.

## Phase 2 automated validation

Coverage includes protected password loading, client identity, MQTT 3.1.1 setup, retained QoS 1 Last Will, retained availability, asynchronous connection, Paho loop startup, reconnect delay, no disconnected publication, latest-only outage state, discovery hooks, reconnect recovery, change-only publication, rejection handling, graceful Paho 1.5.1-compatible shutdown, public-state filtering, and error limiting.

## Phase 3 automated validation

Coverage includes current-game, playing, optional system, and current-artwork discovery; stable unique IDs; shared device identity; state, artwork, and availability topics; null-safe templates; public attributes; tombstones; custom discovery prefix; compact JSON; and reconnect discovery recovery.

## Phase 4 automated validation

Coverage includes exact flat and nested metadata keys, XML namespaces, incremental early-stop parsing, missing and malformed gamelists, title precedence, bounded overrides, stacked extensions, recognized trailing metadata, collection-title preservation, MAME behavior, session-change-only resolution, public-title propagation, and path-safe warnings.

## Phase 5 implementation validation

Coverage includes approved installed paths, root requirement, source JSON validation, first-install credential requirement, configuration and credential preservation, explicit credential replacement, staged deployment, application and systemd-state rollback, protected permissions, production unit constraints, bounded restart policy, runtime directory, read-only ROM path, disabled bytecode, bounded validation sampling, CPU/RSS/PSS/write summaries, atomic evidence, failure records, and all prior phase regressions.

## Hardware evidence through 0.6.7

### Installation and service

- Installer update succeeded and retained configuration and credentials.
- Service enablement succeeded.
- Graceful stop completed with success.
- Manual start returned active/running and restored MQTT.
- Ordinary reboot loaded and started the service; one bounded recovery occurred.
- Clean zero-restart boot remains open.

### Detection

- Live DGE sessions were observed for FBNEO, XMAME, GBA, SFC, and GB/GBC.
- Idle detection passed.
- RetroArch playlist detection passed with Gambatte and Snes9x.
- A different-core RetroArch transition passed.
- RetroArch return to idle passed.
- Live MAME 2010 memory probes identified `avsp.zip` and then `ffight2b.zip` beside the mapped core while stale history strings remained.
- Corrected consolidated same-core, DGE-to-RetroArch, and RetroArch-to-DGE matrix evidence remains open.

### MQTT and power

- Baseline MQTT connection passed.
- Broker reconnection passed.
- Broker-outage observation was inconclusive because the first SSH runner combined service and socket checks.
- Battery operation and USB-online transition `0 -> 1` passed.
- Wi-Fi outage/recovery remains the final manual network test.

### Resource evidence

- Idle and RetroArch snapshot RSS maximum: 27,128 KiB.
- Snapshot PSS values were below the release ceiling.
- No ROM descriptor was observed.
- The 0.6.7 gameplay run recorded a continuous window, zero process-write growth, no ROM descriptor, and RSS below 40 MiB.
- Journald capture was unavailable in the snapshots.
- No additional one-hour run is requested for 0.6.8.

## Version 0.6.8 automated validation

### Titles

Verified:

- repeated archive and ROM extension stripping
- recognized region, language, revision, beta, prototype, kiosk, and dump-tag cleanup
- underscore and whitespace normalization
- trailing article movement
- title-significant unknown parentheses preservation
- hacks and collection punctuation preservation
- compatibility of the public `metadata_location()` helper

### Artwork lookup

Verified:

- exact matching `gamelist.xml` `<image>`
- nested mirrored system `images/` fallback
- missing artwork returns no artwork without blocking presence
- JPEG signature
- PNG signature
- WebP signature
- extension/signature agreement
- unsupported or malformed image rejection
- empty and oversized file rejection
- symlink rejection
- active-system containment
- regular-file requirement
- default 2 MiB ceiling

### MQTT artwork

Verified:

- separate retained binary artwork topic
- Home Assistant MQTT image discovery
- shared device identity
- state attributes for artwork availability and content type
- empty retained payload on idle or missing artwork
- unchanged-state and unchanged-artwork suppression
- independent state and artwork pending flags
- retry after transient artwork publish rejection
- reconnect restoration of latest state and artwork
- latest-only behavior during outages
- Paho 1.5.1-compatible shutdown

### Regression restoration

The package includes and runs regression modules for:

- configuration
- daemon state machine
- deployment
- detection
- discovery
- metadata
- MQTT
- platform probe
- validation
- 0.6.8 artwork and title behavior

The compatibility audit restored the original two-value `metadata_location()` contract and retained all verified aliases.

## Packaging validation

The release process verifies:

- version reports `0.6.9`
- source and tests compile
- test suite passes from a clean extraction
- ZIP integrity passes
- no `__pycache__`
- no `.pyc` or `.pyo`
- no `.pytest_cache`
- no development ROM filename inventory
- required source, tests, deployment, configuration, documentation, and GitHub bootstrap files are present

## Remaining 0.6.8 device checks

- [ ] Install/update succeeds on TF1 and retains configuration and credentials
- [ ] Valid local artwork renders in Home Assistant
- [ ] Missing artwork clears the previous retained image
- [ ] Clean title appears for a representative fallback-only ROM
- [ ] One short resource snapshot with representative artwork remains below the 40 MiB ceiling
- [ ] Corrected supervision test
- [ ] Corrected broker-outage observation
- [ ] Manual Wi-Fi outage and recovery
- [ ] Journald evidence

No repeated one-hour validation is required for this revision unless the short artwork snapshot exposes continuing growth or a later runtime change invalidates prior evidence.


## GitHub bootstrap validation

Automated checks verify shell syntax, root refusal, dependency checks, temporary workspace cleanup, repository archive URL construction, required-file validation, argument forwarding to the Python installer, and preservation of compatibility-sensitive identifiers. Network download and first-install behavior remain device checks after the repository is populated.

## Version 0.6.9 MQTT contract validation

The MQTT serializer explicitly emits only the approved game-focused fields. Automated regression coverage verifies the exact field set and confirms that software version, detection method, relative path, metadata source, battery, CPU, and memory fields are absent from normal state messages.
