# Play Presence

Play Presence shows what is currently running on an Anbernic RG40XX V in Home Assistant. It detects RetroArch and native TF1 emulator sessions, cleans game titles, finds local box art, and publishes the current game and artwork through MQTT.

## Highlights

- Detects RetroArch, native `.dge` emulators, XMAME, and OpenBOR
- Supports TF1 RetroArch playlist launches that omit the ROM from the command line
- Publishes the current game, system, emulator, core, and box art to Home Assistant
- Uses existing `gamelist.xml` metadata and local artwork
- Cleans common ROM filename noise when metadata is unavailable
- Clears stale artwork when a game has no image or the device returns to idle
- Runs as a small, headless systemd service
- Opens no inbound network service and never controls an emulator
- Writes nothing to ROM storage
- Preserves configuration and MQTT credentials during updates

## Overview

Play Presence is designed for the Anbernic RG40XX V running TF1 stock firmware. The daemon watches Linux process information to identify the active game without enabling RetroArch network control or exposing a web service.

When a game starts, Play Presence resolves the display title and local artwork, then publishes a compact retained state and raw image data to MQTT. Home Assistant discovery creates the related entities automatically.

The project is maintained at [swetoast/play_presence](https://github.com/swetoast/play_presence).

## Requirements

- Anbernic RG40XX V
- TF1 stock firmware
- Python 3.10 or later
- Paho MQTT 1.5.x
- Access to an MQTT broker
- Root access on the handheld for installation and procfs inspection
- `curl` or `wget` for the one-line installer

The verified ROM root is:

```text
/mnt/mmc/Roms
```

## Installation

Connect to the handheld over SSH as root and run:

```sh
curl -fsSL https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

If `curl` is unavailable:

```sh
wget -qO- https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

On the first installation, the script asks for the MQTT password through the terminal. Input is hidden while typing. The installer downloads into `/tmp`, validates the project layout, runs the protected Python installer, removes temporary files, prints the installed version, and shows the service status.

Updates use the same command. Existing configuration and MQTT credentials are preserved.

### Non-interactive first installation

To provide the password from an existing protected file:

```sh
curl -fL -o /tmp/play-presence-install.sh \
  https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh
chmod +x /tmp/play-presence-install.sh
/tmp/play-presence-install.sh --password-file /path/to/mqtt-password
```

## How it works

Play Presence follows this path:

```text
Running emulator
      |
      v
Read-only process detection
      |
      v
ROM, system, emulator, and core identification
      |
      v
Title and artwork resolution
      |
      v
Retained MQTT state and artwork
      |
      v
Home Assistant entities
```

### Game detection

Play Presence detects:

- Native TF1 game `.dge` processes
- XMAME split directory and filename arguments
- OpenBOR
- RetroArch games with content in the command line
- TF1 RetroArch playlist launches through bounded read-only process-memory inspection

`mcuCtrl.dge` and known TF1 utility processes are ignored.

### Title resolution

Titles are resolved in this order:

1. Exact matching `<name>` in the system `gamelist.xml`
2. Optional daemon-owned manual override
3. Conservative filename cleanup

The fallback removes stacked ROM and archive extensions, recognized trailing region and dump metadata, repeated whitespace, and common trailing articles. Unknown title text, hacks, and collection separators remain intact.

Example:

```text
Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba.zip
```

becomes:

```text
The Legend of Zelda - The Minish Cap
```

### Artwork resolution

Play Presence checks:

1. The matching `<image>` value in `gamelist.xml`
2. The mirrored `images/` location inside the active system folder

Nested ROM folders are mirrored beneath `images/`.

Supported formats:

- JPEG
- PNG
- WebP

The daemon verifies image signatures, rejects symlinks and path escapes, and accepts only regular files inside the active system directory. The default artwork limit is 2 MiB.

Play Presence does not download, resize, convert, replace, or otherwise modify artwork.

## Home Assistant

Play Presence publishes Home Assistant discovery for:

- Current game
- Playing status
- Optional system sensor
- Current game artwork

All entities share the same RG40XX V device identity.

The artwork entity receives raw image bytes over MQTT. Images are not Base64 encoded. When a game has no valid artwork, or the device returns to idle, Play Presence publishes an empty retained artwork payload so the previous image is not left behind.

## MQTT topics

Default topics:

```text
rg40xxv/availability
rg40xxv/state
rg40xxv/artwork
```

State and artwork use retained QoS 1 publication. Only the current state and current artwork are retained by the application. Obsolete game transitions are not queued during an outage.

## Configuration

Installed configuration:

```text
/etc/play-presence/config.json
```

Installed MQTT password:

```text
/etc/play-presence/mqtt-password
```

Example configuration is included at:

```text
config/config.example.json
```

Validate the installed configuration with:

```sh
PYTHONPATH=/opt/play-presence/src \
/usr/bin/python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

## Service management

Play Presence runs through the existing compatibility-safe service name:

```text
play-presence.service
```

Useful commands:

```sh
systemctl status play-presence.service
systemctl restart play-presence.service
systemctl stop play-presence.service
journalctl -u play-presence.service -b
```

Installed application files:

```text
/opt/play-presence/
```

Runtime failure evidence, when needed, is stored only in volatile storage:

```text
/run/play-presence/
```

## Security and resource limits

Play Presence:

- Opens no listening port
- Accepts no inbound commands
- Does not enable RetroArch network control
- Reads emulator and ROM information without controlling either
- Keeps MQTT credentials outside command-line arguments
- Mounts ROM storage read-only inside the systemd service
- Writes no routine state to ROM directories
- Keeps only the latest state and artwork in memory
- Limits artwork to 2 MiB by default
- Uses bounded reconnect, retry, journal, validation, and process-memory behavior

Project resource targets:

```text
Preferred RSS: 30 MiB or less
RSS ceiling: 40 MiB
Stable CPU: effectively 0.0 percent at reported precision
Routine process write growth: none
Long-run memory growth: none
```

## Validation

Run the automated suite from the project root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Compile the source and tests:

```sh
PYTHONDONTWRITEBYTECODE=1 \
python3 -m compileall -q src tests deploy/install.py
```

Check the source version:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
python3 -m play_presence --version
```

Collect a bounded device snapshot:

```sh
PYTHONPATH=/opt/play-presence/src \
sudo -E /usr/bin/python3 -m play_presence validate
```

Detailed project records are available in:

- [`docs/DESIGN.md`](docs/DESIGN.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/VALIDATION.md`](docs/VALIDATION.md)
- [`CHANGELOG.md`](CHANGELOG.md)

## Troubleshooting

### The service does not start

Check the service and configuration:

```sh
systemctl status play-presence.service
PYTHONPATH=/opt/play-presence/src \
python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

### Home Assistant shows the wrong or stale artwork

Confirm that the active game has a valid image referenced by `gamelist.xml` or stored under the system `images/` folder. Returning to idle or starting a game without artwork should clear the retained image.

### The game title still contains filename metadata

A matching `gamelist.xml` name takes priority. Without metadata, Play Presence applies conservative cleanup and intentionally preserves unfamiliar text rather than guessing a different title.

## Contributing and feedback

Bug reports, feature requests, documentation corrections, and tested emulator observations are welcome through [GitHub Issues](https://github.com/swetoast/play_presence/issues).

Please include the Play Presence version, TF1 environment details, relevant emulator, and reproducible observations. Never include MQTT passwords or other credentials.

## Project status

Version 0.6.8 includes automated coverage for detection, configuration, state transitions, MQTT recovery, Home Assistant discovery, title cleanup, artwork validation, installation, and bounded validation collection.

Remaining work is tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md), including targeted TF1 hardware evidence for artwork rendering, missing-artwork clearing, representative artwork memory usage, outage recovery, and remaining Phase 5 acceptance items.
