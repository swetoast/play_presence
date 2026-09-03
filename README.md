# Play Presence

Play Presence lets Home Assistant know which game is running on an Anbernic handheld. It detects games started through RetroArch or a native emulator, resolves a clean title, finds matching local artwork, and publishes the result over MQTT.

Play Presence is intended for Anbernic devices running Linux. 

Verified Models:

* RG40XX V

Current release: **0.7.0**.

## Highlights

- Detects RetroArch and native `.dge` emulator sessions
- Supports XMAME, OpenBOR, and TF1 RetroArch playlist launches
- Publishes the current game, system, emulator, core, start time, and artwork
- Uses existing `gamelist.xml` metadata and local artwork
- Cleans recognized technical metadata from fallback titles
- Restores the current state and artwork after reconnecting to MQTT
- Runs as a small systemd service with no inbound network interface
- Does not control emulators or write to ROM storage
- Preserves configuration and MQTT credentials during updates

## Requirements

- An Anbernic device running Linux
- An MQTT broker that the handheld can reach
- Root SSH access to the handheld
- Python 3.10 or later
- Paho MQTT 1.5.x or 1.6.x (the 1.x callback API; 2.x is not supported)
- `curl` or `wget`

Verified environment:

```text
Model: RG40XX V
Firmware: TF1 stock firmware
ROM root: /mnt/mmc/Roms
```

Other Linux-based Anbernic devices may work when their emulator processes and ROM layout are compatible, but those devices have not yet been verified.

## Installation

Connect to the handheld over SSH as root and run:

```sh
curl -fsSL https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

If `curl` is unavailable:

```sh
wget -qO- https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

The interactive installer asks for:

- MQTT host
- MQTT port
- MQTT username
- MQTT topic prefix
- MQTT password

The password is hidden while you type. The installer downloads the current source into `/tmp`, validates the project layout, installs and starts the service, removes temporary files, and prints the installed version and service status.

Run the same command again to update Play Presence.

### Installer trust model

The installer downloads the current `main` branch archive directly from GitHub over HTTPS and runs it as root. Its integrity therefore rests on the GitHub TLS connection and on the layout checks the installer performs before running anything (it aborts unless `deploy/install.py`, `pyproject.toml`, and `config/config.example.json` are present in the extracted tree). There is no separate signature or published-checksum verification. If you require stronger guarantees, clone the repository at a specific commit or tag over SSH, inspect it, and run `python3 deploy/install.py` directly instead of piping the bootstrap script to a shell.

## Uninstallation

To completely remove Play Presence, including its configuration and MQTT credentials, run:

```sh
curl -fsSL https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh -s -- uninstall
```

If `curl` is unavailable:

```sh
wget -qO- https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh -s -- uninstall
```

The uninstaller asks for confirmation before removing anything.


## Home Assistant

MQTT discovery creates these entities under one Play Presence device:

```text
sensor.play_presence_current_game
binary_sensor.play_presence_playing
sensor.play_presence_system
image.play_presence_current_game_artwork
```

The system sensor is optional. The retained state message remains focused on the game:

```json
{
  "state": "playing",
  "game": "Example Quest",
  "system": "Example Handheld",
  "system_id": "example",
  "emulator": "retroarch",
  "core": "example_core",
  "rom_file": "Example Quest (Region) (En).rom.zip",
  "started_at": "2026-09-02T05:12:00+02:00",
  "artwork_available": true,
  "artwork_content_type": "image/jpeg"
}
```

When no game is running, `state` changes to `idle`, the game fields become empty, and the previous artwork is cleared.

Software version, detection method, filesystem paths, battery information, performance data, and other diagnostics are not included in the normal game state.

## How detection works

Play Presence reads Linux process information directly from procfs and does not require RetroArch network control.

Supported launch paths include:

- Native TF1 game `.dge` processes
- XMAME with separate directory and filename arguments
- OpenBOR
- RetroArch with the ROM path in the command line
- TF1 RetroArch playlist launches that omit the ROM path

For contentless RetroArch launches, Play Presence performs bounded, read-only process-memory inspection. A game is accepted only when a mapped libretro core and a real ROM path appear together in a suitable memory region. This avoids treating old playlist or history entries as the active game.

Known helpers and non-game utilities, including `mcuCtrl.dge`, are ignored.

## How titles are chosen

Play Presence chooses the first available title source:

1. The matching `<name>` in the system's `gamelist.xml`
2. An optional manual title override
3. The ROM filename

When the ROM filename is used, Play Presence removes only recognized technical metadata. This includes stacked ROM and archive extensions, region and language tags, revision markers, beta or prototype labels, and known dump tags. Underscores and repeated whitespace are normalized, and a trailing article such as `, The`, `, A`, or `, An` is moved to the front.

Cleanup is deliberately conservative. Unknown parentheses, punctuation, hack names, special-edition labels, collection names, and separators remain part of the title. If Play Presence cannot confidently identify text as technical metadata, it leaves the text unchanged.

## How artwork is found

Play Presence first checks the `<image>` value for the exact matching game in `gamelist.xml`. If no usable image is defined, it checks the system's mirrored `images` directory, including nested ROM folders.

In other words, artwork follows the same relative folder layout as the ROM, but beneath the system's `images` directory. No commercial game names are needed to describe or configure this behavior.

Supported formats:

- JPEG
- PNG
- WebP

Before publishing an image, Play Presence verifies that the file:

- Is a regular file
- Is not a symlink
- Remains inside the active system directory
- Has a supported extension and matching image signature
- Is not empty
- Does not exceed the configured limit

The default artwork limit is 2 MiB.

Play Presence never downloads, converts, resizes, replaces, or writes artwork. A game without a valid image still publishes its game state and clears any previously retained artwork.

## MQTT

Default topics:

```text
rg40xxv/availability
rg40xxv/state
rg40xxv/artwork
```

The state topic contains JSON. The artwork topic contains raw image bytes without Base64 encoding or a JSON wrapper.

State and artwork use retained QoS 1 messages. During an outage, Play Presence keeps only the latest state and artwork rather than queuing a history of game changes.

## Configuration and service

Installed locations:

```text
Application: /opt/play-presence
Configuration: /etc/play-presence/config.json
MQTT password: /etc/play-presence/mqtt-password
Runtime data: /run/play-presence
Service: play-presence.service
```

Validate the configuration:

```sh
PYTHONPATH=/opt/play-presence/src \
python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

Manage the service:

```sh
systemctl status play-presence.service
systemctl restart play-presence.service
systemctl stop play-presence.service
journalctl -u play-presence.service -b
```

## Security and resource use

Play Presence is passive and intentionally bounded. It opens no listening port, accepts no inbound commands, does not control an emulator, keeps MQTT credentials outside command-line arguments, and mounts ROM storage read-only inside the systemd service.

The service keeps only the current state and artwork in memory. Artwork is limited to 2 MiB by default, and reconnect, retry, logging, validation, and process-memory operations are bounded.

Resource targets:

```text
Preferred RSS: 30 MiB or less
RSS ceiling: 40 MiB
Stable CPU: effectively 0.0 percent at reported precision
Routine process write growth: none
Long-run memory growth: none
```

## Troubleshooting

### The service does not start

```sh
systemctl status play-presence.service
PYTHONPATH=/opt/play-presence/src \
python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

### Home Assistant shows old artwork

Return to the launcher or start a game without artwork. Play Presence should publish an empty retained message to `rg40xxv/artwork`. If the old image remains, verify that the service is connected to MQTT and that Home Assistant received the update.

### A game has no artwork

Check the game's `<image>` value in `gamelist.xml` or the corresponding system `images` directory. The image must follow the expected ROM-relative layout and pass the file checks described above.

### A fallback title still contains extra text

Play Presence removes only recognized metadata. Leaving unfamiliar text in place is safer than removing part of a real title.

## Development and project records

Run the automated tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Check the version:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
python3 -m play_presence --version
```

Collect a bounded device snapshot:

```sh
PYTHONPATH=/opt/play-presence/src \
sudo -E python3 -m play_presence validate
```

Further project information:

- [`CHANGELOG.md`](CHANGELOG.md)
- [`docs/DESIGN.md`](docs/DESIGN.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/VALIDATION.md`](docs/VALIDATION.md)

## Contributing

Bug reports, feature requests, documentation corrections, and verified emulator observations are welcome through [GitHub Issues](https://github.com/swetoast/play_presence/issues).

Include the Play Presence version, Anbernic model, Linux firmware, emulator, and steps needed to reproduce the issue. Do not include MQTT passwords or other credentials.
