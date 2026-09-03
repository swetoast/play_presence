# On-device acceptance runbook

This runbook closes the remaining hardware items in [`ROADMAP.md`](ROADMAP.md).
Every item here needs a physical RG40XX V on TF1 firmware; nothing here is a
code task. Run each block over SSH as root on the handheld, record the output,
and tick the matching roadmap box when the pass criteria are met.

The commands reuse the tooling the daemon already ships. Where an output file is
written, its name carries the project version (currently `v0.7.0`).

Most of this is automated by [`deploy/acceptance.sh`](../deploy/acceptance.sh),
which runs the checks below, scores the `validate` assessment, guides the manual
steps, and restores state after the destructive ones. Run `sh deploy/acceptance.sh help`
on the device for the command list; `sh deploy/acceptance.sh all` runs the
non-destructive automated set. The sections below document each step directly.

## 0. Preconditions

```sh
PYTHONPATH=/opt/play-presence/src python3 -m play_presence --version
PYTHONPATH=/opt/play-presence/src python3 -m play_presence check-config \
  --config /etc/play-presence/config.json
systemctl is-enabled play-presence.service
systemctl is-active play-presence.service
```

Pass: version reports `0.7.0`, configuration validates, service is enabled and
active.

## 1. Reboot persistence and clean start (P5-SVC-003)

```sh
sudo -E python3 -m play_presence probe prepare --state-dir /var/lib/play-presence-probe
reboot
# after the device comes back:
sudo -E python3 -m play_presence probe verify --state-dir /var/lib/play-presence-probe
systemctl show play-presence.service --property=NRestarts --value
```

Pass: probe verify reports `pass`, and `NRestarts` is `0` after the boot (the
open item is a *clean zero-restart* boot; a boot that needed a bounded recovery
does not satisfy it).

## 2. Supervision after unexpected termination (P5-SVC-005)

```sh
systemctl show play-presence.service --property=MainPID --value   # note the PID
kill -9 <MainPID>
sleep 65
systemctl is-active play-presence.service
systemctl show play-presence.service --property=NRestarts --value
```

Pass: the service returns to `active` after roughly `RestartSec` (60 s) and
`NRestarts` increments by exactly one. This is the "corrected supervision
observation" from the 0.6.7 evidence list.

## 3. Invalid-configuration rate limit (P5-SVC-006)

Static review is complete: the unit sets `StartLimitIntervalSec=600`,
`StartLimitBurst=3`, `RestartSec=60`, and an `ExecStartPre` `check-config` gate,
so three failed starts inside ten minutes stop the unit. Device confirmation:

```sh
cp /etc/play-presence/config.json /root/config.json.bak
printf 'not json' > /etc/play-presence/config.json
systemctl restart play-presence.service || true
sleep 200            # allow the bounded restart attempts
systemctl is-failed play-presence.service
systemctl status play-presence.service | sed -n '1,12p'
# restore:
cp /root/config.json.bak /etc/play-presence/config.json
systemctl reset-failed play-presence.service
systemctl restart play-presence.service
```

Pass: systemd stops retrying and the unit ends `failed` with a start-limit
message; after restoring the config the service starts cleanly.

## 4. Idle CPU, gameplay CPU, and long-run stability (P5-PERF-001/002/004)

A short window (default one sample) confirms shape; a longer window confirms
no growth. `validate` writes a bounded JSON evidence file and prints its path.

```sh
# short idle snapshot (device at the launcher, no game running):
PYTHONPATH=/opt/play-presence/src sudo -E python3 -m play_presence validate

# gameplay snapshot with artwork loaded (start a game with local artwork first):
PYTHONPATH=/opt/play-presence/src sudo -E python3 -m play_presence validate

# extended no-growth window (one hour at 60 s intervals):
PYTHONPATH=/opt/play-presence/src sudo -E python3 -m play_presence validate \
  --duration 3600 --interval 60
```

Read the `assessment` block of each result file. Pass criteria:

- `cpu_zero_at_reported_precision` is `true`
- `rss_at_or_below_preferred_limit` is `true` and `rss_below_release_ceiling` is `true`
- for the long run: `growth_window_usable` is `true`, and `rss_growth_zero`,
  `pss_growth_zero`, and `process_write_growth_zero` are all `true`
- `no_rom_descriptor_observed` is `true` in every run

The gameplay run with artwork loaded is the 0.6.8 snapshot still outstanding
(P5-PERF-002, P5-HW-ART-003).

## 5. Persistent-write and journald review (P5-SEC-001, P5-SEC-002)

Static review is complete: during `run` the daemon performs no persistent
writes. The only write path is the volatile failure record under the tmpfs
`RuntimeDirectory` (`/run/play-presence/last-failure.json`); ROM storage is
`ReadOnlyPaths`, and `ProtectSystem=full` with `ProtectHome=true` seal the rest.
There is no per-poll logging, and every warning passes through a 60-second
error limiter, so log volume is bounded by event rate rather than poll rate.

Device confirmation:

```sh
# from any validate result:
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("write growth:", d["summary"]["write_bytes_growth"])' \
  /mnt/mmc/play-presence-validation-v0.7.0.json
journalctl -u play-presence.service -b --no-pager | wc -l
```

Pass: `write_bytes_growth` is `0` over the window, and the boot journal line
count is small and does not grow while idle.

## 6. Network outage matrix (P5-SVC-004, P5-SEC-004)

```sh
# broker outage: stop the broker (or block it), watch, then restore.
journalctl -u play-presence.service -f    # in one session
# in another: take the broker down for ~2 minutes, then bring it back.
```

Pass: on outage the daemon logs a single bounded disconnect warning (not a
per-poll stream), and on recovery it republishes availability `online`, the
latest retained state, and the latest artwork. Repeat for a Wi-Fi outage on the
handheld (disable/enable Wi-Fi). These are the "manual Wi-Fi outage and
recovery" and "corrected broker-outage observation" items.

## 7. Detection transition matrix (0.6.7 evidence, P5-SEC-004)

With a Home Assistant MQTT client subscribed to the state topic, walk the
launcher through: idle → DGE game → idle; idle → RetroArch (content on the
command line) → idle; a same-core RetroArch switch between two ROMs; and a
DGE → RetroArch → DGE sequence. Confirm each transition publishes the correct
`game`, `system`, `emulator`, and `core`, with no synthetic idle between
back-to-back games.

Pass: every transition is reflected once and correctly; the same-core switch
resolves to the newly active ROM.

## 8. Artwork on device (P5-HW-ART-001/002/003)

With a game that has a valid local image (either a `gamelist.xml` `<image>` or a
mirrored `images/` file):

- Start the game and confirm `image.play_presence_current_game_artwork` renders
  the artwork in Home Assistant (P5-HW-ART-001).
- Return to the launcher (or start a game without artwork) and confirm the
  previous image clears, i.e. an empty retained payload is published to the
  artwork topic (P5-HW-ART-002).
- Capture one `validate` snapshot with the artwork loaded and confirm RSS stays
  below the 40 MiB ceiling (P5-HW-ART-003; see section 4).

## Recording results

For each section, save the command output (and any `validate`/`probe` result
file) alongside the roadmap, then tick the corresponding boxes in
[`ROADMAP.md`](ROADMAP.md) and note the observations in
[`VALIDATION.md`](VALIDATION.md). When every applicable box is ticked, the
release-gate hardware line can close.
