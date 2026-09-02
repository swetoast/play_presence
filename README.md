# Play Presence

Play Presence lets Home Assistant know which game is currently running on an Anbernic handheld. It works quietly in the background, detects games started through RetroArch or a native emulator, cleans up messy ROM filenames, finds matching box art, and sends the result over MQTT.

The project is intended for Anbernic devices running Linux. The **RG40XX V running TF1 stock firmware is the currently verified model**.

Current release: **0.6.9**.

## Why use Play Presence?

If you already use Home Assistant, Play Presence gives your handheld a useful live status without adding a web server or enabling remote-control features on the device.

You can use it to:

- Show the game that is currently running
- Show the console or system being emulated
- Display local box art in Home Assistant
- Use the playing state in dashboards and automations
- Keep the last known state available through retained MQTT messages

Play Presence only observes the handheld. It does not start games, control emulators, modify ROMs, or expose an inbound network service.

## Highlights

- Detects RetroArch and native `.dge` emulator sessions
- Supports XMAME and OpenBOR
- Supports TF1 RetroArch playlist launches where the ROM is missing from the command line
- Uses existing `gamelist.xml` titles and artwork
- Cleans common region, revision, language, and dump tags from fallback titles
- Publishes raw JPEG, PNG, or WebP artwork through MQTT
- Clears the previous image when the current game has no artwork
- Automatically restores the current state and artwork after reconnecting to MQTT
- Runs as a small systemd service
- Preserves the existing configuration and MQTT password during updates

## Requirements

You need:

- An Anbernic device running Linux
- An MQTT broker that the handheld can reach
- Root access to the handheld through SSH
- Python 3.10 or later
- Paho MQTT 1.5.x
- `curl` or `wget` for the simple installer

Verified hardware and firmware:

```text
Model: RG40XX V
Firmware: TF1 stock firmware
ROM root: /mnt/mmc/Roms
```

Other Linux-based Anbernic devices may work if their emulator processes and ROM layout are compatible, but they have not yet been verified.

## Installation

Connect to the handheld over SSH as root and run:

```sh
curl -fsSL https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

If `curl` is not available, use:

```sh
wget -qO- https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh | sh
```

During the first installation, Play Presence asks for the MQTT password in the terminal. The password is hidden while you type it.

The installer then:

1. Downloads the current source into `/tmp`
2. Checks that the expected project files are present
3. Installs Play Presence under `/opt/play-presence`
4. Creates the protected configuration under `/etc/play-presence`
5. Enables and starts `play-presence.service`
6. Removes the temporary download
7. Prints the installed version and service status

Run the same command again to update Play Presence. Existing configuration and MQTT credentials are kept during updates.

### Non-interactive first installation

If the MQTT password is already stored in a protected file, download the installer and pass that file explicitly:

```sh
curl -fL -o /tmp/play-presence-install.sh \
  https://raw.githubusercontent.com/swetoast/play_presence/main/install.sh
chmod +x /tmp/play-presence-install.sh
/tmp/play-presence-install.sh --password-file /path/to/mqtt-password
```

## What appears in Home Assistant?

Play Presence uses MQTT discovery to create these entities:

- **Current game**: the cleaned or metadata-provided game title
- **Playing**: whether a game is currently running
- **System**: an optional sensor for the emulated platform
- **Current game artwork**: the matching local box art

All entities are grouped under the same device in Home Assistant.

## MQTT state data

The retained state message stays focused on the game that is currently running. A playing state looks like this:

```json
{
  "state": "playing",
  "game": "The Legend of Zelda - The Minish Cap",
  "system": "Game Boy Advance",
  "system_id": "gba",
  "emulator": "retroarch",
  "core": "gambatte",
  "rom_file": "Legend of Zelda, The - The Minish Cap (Europe).gba.zip",
  "started_at": "2026-09-02T05:12:00+02:00",
  "artwork_available": true,
  "artwork_content_type": "image/jpeg"
}
```

When no game is running, `state` changes to `idle`, the game fields become empty, and the previous artwork is cleared. Play Presence does not add software-version, detector, filesystem-path, battery, performance, or other diagnostic fields to the normal game state.

## How game detection works

Play Presence reads Linux process information directly from procfs. It does not use shell process tools and does not require RetroArch network control.

The detector supports:

- Native TF1 game `.dge` processes
- XMAME games whose directory and filename are passed separately
- OpenBOR
- RetroArch games whose ROM path is present in the command line
- TF1 RetroArch playlist launches that omit the ROM path from the command line

For the last case, Play Presence performs bounded, read-only inspection of the RetroArch process memory. A game is accepted only when a known libretro core and a real ROM path appear together in the same suitable memory region. This prevents old playlist or history entries from being mistaken for the active game.

Known helpers and non-game utilities, including `mcuCtrl.dge`, are ignored.

## How titles are chosen

Play Presence uses the following order:

1. The matching `<name>` entry in the system `gamelist.xml`
2. An optional manual title override
3. A cleaned version of the ROM filename

The fallback cleanup removes known file extensions and common metadata from the end of a filename. It also moves trailing articles such as `, The` to the front.

For example:

```text
Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba.zip
```

becomes:

```text
The Legend of Zelda - The Minish Cap
```

The cleanup is deliberately conservative. Unknown text, hack names, special editions, and collection separators are kept rather than guessed away.

## How artwork is found

Play Presence first checks the `<image>` value belonging to the exact matching game in `gamelist.xml`.

If that entry does not provide a usable image, Play Presence checks the system's `images` directory. Nested ROM folders are mirrored beneath `images`.

Example:

```text
/mnt/mmc/Roms/SFC/Super Mario World (USA).sfc.zip
/mnt/mmc/Roms/SFC/images/Super Mario World (USA).sfc.jpg
```

Supported artwork formats:

- JPEG
- PNG
- WebP

Before publishing an image, Play Presence checks that the file:

- Is a regular file
- Is not a symlink
- Stays inside the active system directory
- Has a supported extension
- Has a matching image signature
- Is not empty
- Is no larger than the configured limit

The default artwork limit is 2 MiB.

Play Presence never downloads, converts, resizes, replaces, or writes artwork.

## MQTT topics

The default topics are:

```text
rg40xxv/availability
rg40xxv/state
rg40xxv/artwork
```

The state topic contains JSON. The artwork topic contains the raw image bytes, without Base64 encoding or a JSON wrapper.

State and artwork are published with QoS 1 and retained messages. During an outage, Play Presence keeps only the latest state and latest artwork. It does not queue a history of game changes.

## Configuration

The installed configuration is stored at:

```text
/etc/play-presence/config.json
```

The MQTT password is stored separately at:

```text
/etc/play-presence/mqtt-password
```

An example configuration is included in the repository:

```text
config/config.example.json
```

Check the installed configuration with:

```sh
PYTHONPATH=/opt/play-presence/src \
python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

## Service management

Play Presence runs as:

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

Application files are installed under:

```text
/opt/play-presence
```

Temporary runtime evidence is stored under:

```text
/run/play-presence
```

## Security and resource use

Play Presence is intentionally small and passive.

It:

- Opens no listening port
- Accepts no inbound commands
- Does not control RetroArch or another emulator
- Does not execute ROM-derived text
- Keeps MQTT credentials out of command-line arguments
- Mounts ROM storage read-only inside the systemd service
- Writes no routine state to ROM directories
- Keeps only the current state and current artwork in memory
- Limits artwork to 2 MiB by default
- Uses bounded reconnect, retry, logging, and process-memory behavior

The project targets:

```text
Preferred RSS: 30 MiB or less
RSS ceiling: 40 MiB
Stable CPU: effectively 0.0 percent at reported precision
Routine process write growth: none
Long-run memory growth: none
```

## Troubleshooting

### The service does not start

Check the service status:

```sh
systemctl status play-presence.service
```

Then validate the configuration:

```sh
PYTHONPATH=/opt/play-presence/src \
python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
```

### Home Assistant shows old artwork

Start a game without artwork or return to the TF1 menu. Play Presence should publish an empty retained artwork message and clear the previous image.

If the image remains, check that the service is connected to MQTT and that Home Assistant received the `rg40xxv/artwork` update.

### A game has no artwork

Check the matching `<image>` value in the system `gamelist.xml` or place the image in the corresponding system `images` folder. The image filename must match the expected ROM-relative artwork name.

### A fallback title still contains extra text

Play Presence removes only metadata patterns it recognizes. This is intentional. It is safer to leave unfamiliar text in place than to remove part of a real game title.

## Development and validation

Run the automated test suite from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Check the installed or source version:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
python3 -m play_presence --version
```

Collect a bounded device snapshot:

```sh
PYTHONPATH=/opt/play-presence/src \
sudo -E python3 -m play_presence validate
```

More detailed project information is available in:

- [`CHANGELOG.md`](CHANGELOG.md)

## Contributing and feedback

Bug reports, feature requests, documentation corrections, and verified emulator observations are welcome through [GitHub Issues](https://github.com/swetoast/play_presence/issues).

When reporting a problem, include the Play Presence version, Anbernic model, Linux firmware, emulator, and steps needed to reproduce the issue. Do not include MQTT passwords or other credentials.

## Project status

The RG40XX V running TF1 stock firmware is the verified reference device. Support for other Linux-based Anbernic devices depends on their emulator process layout, ROM paths, and power interfaces.

Current development and remaining hardware validation are tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md).
