#!/bin/sh
# Play Presence on-device acceptance runner.
#
# Executes the hardware acceptance steps from docs/ACCEPTANCE.md on the RG40XX V.
# Run as root on the device. Automates what can be automated, guides the manual
# checks, and restores state after the destructive ones. POSIX sh (dash) safe.
#
#   sh deploy/acceptance.sh <command>
#
# Commands:
#   preconditions     version, config validity, service enabled/active
#   resources [label] [duration] [interval]
#                     run `validate` and score CPU/RSS/PSS/write assessment
#                     label defaults to "idle"; duration 0 = single snapshot
#   writes            read the latest result: write growth + boot journal size
#   supervision       force-kill the daemon; confirm systemd restarts it
#   ratelimit         corrupt config to confirm the start limit, then restore
#   reboot-prepare    pre-reboot probe (reboot yourself, then reboot-verify)
#   reboot-verify     post-reboot probe (pass/fail via exit code)
#   broker-outage     guided broker down/up with journal capture
#   transitions       guided detection matrix checklist
#   artwork           guided Home Assistant artwork checklist
#   diagnose          service status, last-failure record, journal (if any)
#   all               non-destructive automated set (preconditions,
#                     resources idle 120s, writes) with a summary
#   help              this text
#
# Paths are overridable via environment: PP_PREFIX, PP_SRC, PP_SERVICE,
# PP_CONFIG, PP_RESULTS.
set -u

: "${PP_PREFIX:=/opt/play-presence}"
: "${PP_SRC:=$PP_PREFIX/src}"
: "${PP_SERVICE:=play-presence.service}"
: "${PP_CONFIG:=/etc/play-presence/config.json}"
: "${PP_RESULTS:=/mnt/mmc/play-presence-acceptance}"
: "${PP_RESTART_WAIT:=70}"
: "${PP_RATELIMIT_WAIT:=210}"

STAMP=$(date +%Y%m%d-%H%M%S 2>/dev/null || echo now)
LOG=""
FAILURES=0

say() {
    printf '%s\n' "$*"
    [ -n "$LOG" ] && printf '%s\n' "$*" >>"$LOG" 2>/dev/null
    return 0
}
section() { say ""; say "== $* =="; }
pass() { say "  [PASS] $*"; }
fail() { say "  [FAIL] $*"; FAILURES=$((FAILURES + 1)); }
manual() { say "  [MANUAL] $*"; }
note() { say "  - $*"; }

pp() { PYTHONPATH="$PP_SRC" python3 -m play_presence "$@"; }

need_root() {
    if [ "$(id -u 2>/dev/null || echo 1)" -ne 0 ]; then
        say "This must run as root on the device."
        exit 1
    fi
}

confirm() {
    ans=""
    printf '%s [y/N] ' "$1"
    if [ -r /dev/tty ]; then read ans </dev/tty; else read ans; fi
    case "$ans" in y | Y | yes | YES) return 0 ;; *) return 1 ;; esac
}

svc_prop() { systemctl show -p "$1" --value "$PP_SERVICE" 2>/dev/null || echo ""; }

wait_active() {
    i=0
    while [ "$i" -lt "${PP_ACTIVE_WAIT:-15}" ]; do
        [ "$(systemctl is-active "$PP_SERVICE" 2>/dev/null)" = active ] && return 0
        sleep 1
        i=$((i + 1))
    done
    [ "$(systemctl is-active "$PP_SERVICE" 2>/dev/null)" = active ]
}

journal_has_entries() {
    n=$(journalctl -u "$PP_SERVICE" -n 1 --no-pager 2>/dev/null | grep -c . 2>/dev/null || echo 0)
    [ "${n:-0}" -gt 0 ]
}

setup_results() {
    mkdir -p "$PP_RESULTS" 2>/dev/null
    LOG="$PP_RESULTS/acceptance-$STAMP.log"
    if ! : >"$LOG" 2>/dev/null; then LOG=""; fi
}

# ---------------------------------------------------------------------------

cmd_preconditions() {
    section "Preconditions"
    say "  version: $(pp --version 2>/dev/null || echo '?')"
    if pp check-config --config "$PP_CONFIG" >/dev/null 2>&1; then
        pass "configuration validates"
    else
        fail "configuration did not validate ($PP_CONFIG)"
    fi
    if [ "$(systemctl is-enabled "$PP_SERVICE" 2>/dev/null)" = enabled ]; then
        pass "service enabled"
    else
        fail "service not enabled"
    fi
    if wait_active; then
        pass "service active"
    else
        fail "service not active (substate: $(svc_prop SubState)); may be mid-restart - re-run shortly, or 'diagnose'"
    fi
}

eval_assessment() {
    python3 - "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("    could not read result:", exc)
    sys.exit(2)
a = d.get("assessment", {})
s = d.get("summary", {})
order = [
    "growth_window_usable", "cpu_within_negligible_limit",
    "rss_at_or_below_preferred_limit", "rss_below_release_ceiling",
    "rss_growth_zero", "pss_growth_zero", "process_write_growth_zero",
    "no_rom_descriptor_observed",
]
failed = False
for k in order:
    v = a.get(k)
    tag = "PASS" if v is True else ("FAIL" if v is False else "n/a ")
    if v is False:
        failed = True
    print("    [%s] %s" % (tag, k))
print("    cpu_literal_zero=%s (informational)" % a.get("cpu_zero_at_reported_precision"))
print("    rss_max_kib=%s cpu_percent=%s write_growth=%s samples=%s" % (
    s.get("rss_max_kib"), s.get("cpu_percent_over_window"),
    s.get("write_bytes_growth"), s.get("sample_count")))
sys.exit(1 if failed else 0)
PY
}

cmd_resources() {
    label="${1:-idle}"
    duration="${2:-0}"
    interval="${3:-60}"
    section "Resources ($label): validate duration=${duration}s interval=${interval}s"
    if ! wait_active; then
        fail "service is not active; cannot sample. Run: sh $0 diagnose"
        return 0
    fi
    [ "$duration" -gt 0 ] 2>/dev/null && say "  sampling for ~${duration}s, please wait..."
    out="$PP_RESULTS/validate-$label-$STAMP.json"
    if pp validate --duration "$duration" --interval "$interval" --output "$out" >/dev/null 2>&1; then
        note "result: $out"
        if eval_assessment "$out"; then
            pass "no failing assessment for this window"
        else
            fail "an assessment metric is False (see above)"
        fi
        if [ "$duration" -eq 0 ] 2>/dev/null; then
            note "single snapshot: growth and CPU need a longer run (e.g. 'resources $label 3600 60')"
        fi
    else
        fail "validate did not complete (is the service running as root?)"
    fi
}

cmd_writes() {
    section "Persistent writes and journal size"
    latest=$(ls -1t "$PP_RESULTS"/validate-*.json 2>/dev/null | head -1)
    if [ -n "$latest" ]; then
        note "reading: $latest"
        python3 - "$latest" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
s = d.get("summary", {})
a = d.get("assessment", {})
print("    write_bytes_growth:", s.get("write_bytes_growth"))
print("    process_write_growth_zero:", a.get("process_write_growth_zero"))
PY
    else
        note "no validate result yet; run 'resources' first (ideally a long window)"
    fi
    if journal_has_entries; then
        lines=$(journalctl -u "$PP_SERVICE" -b --no-pager 2>/dev/null | wc -l | tr -d ' ')
        note "boot journal lines for $PP_SERVICE: ${lines:-0} (expect small and non-growing while idle)"
    else
        note "journald has no entries for this unit - journal storage appears disabled on this device"
        note "no journald growth to bound here; if logs are forwarded to syslog, check /var/log instead"
    fi
}

cmd_supervision() {
    section "Supervision after unexpected termination (P5-SVC-005)"
    if ! confirm "Force-kill the daemon and confirm systemd restarts it?"; then
        note "skipped"
        return 0
    fi
    before=$(svc_prop NRestarts)
    pid=$(svc_prop MainPID)
    say "  main pid: ${pid:-none}, restarts before: ${before:-?}"
    case "$pid" in '' | 0) fail "no running main process"; return 0 ;; esac
    kill -9 "$pid" 2>/dev/null
    say "  waiting ${PP_RESTART_WAIT}s for restart..."
    sleep "$PP_RESTART_WAIT"
    after=$(svc_prop NRestarts)
    active=$(systemctl is-active "$PP_SERVICE" 2>/dev/null || echo inactive)
    say "  active: $active, restarts after: ${after:-?}"
    if [ "$active" = active ] && [ "${after:-0}" -gt "${before:-0}" ] 2>/dev/null; then
        pass "service recovered with one additional restart"
    else
        fail "service did not recover as expected"
    fi
}

ratelimit_restore() {
    [ -f "$PP_CONFIG.acceptance-bak" ] || return 0
    cp "$PP_CONFIG.acceptance-bak" "$PP_CONFIG"
    rm -f "$PP_CONFIG.acceptance-bak"
    systemctl reset-failed "$PP_SERVICE" >/dev/null 2>&1
    systemctl restart "$PP_SERVICE" >/dev/null 2>&1
    return 0
}

cmd_ratelimit() {
    section "Invalid-config restart limit (P5-SVC-006)"
    say "  Static review is already complete; this confirms the systemd behaviour."
    if ! confirm "Temporarily corrupt the config (auto-restored) to test the start limit?"; then
        note "skipped"
        return 0
    fi
    cp "$PP_CONFIG" "$PP_CONFIG.acceptance-bak"
    trap 'ratelimit_restore; trap - INT TERM; exit 1' INT TERM
    printf 'not valid json\n' >"$PP_CONFIG"
    systemctl restart "$PP_SERVICE" >/dev/null 2>&1
    say "  waiting ${PP_RATELIMIT_WAIT}s for the start limit to trip..."
    sleep "$PP_RATELIMIT_WAIT"
    if systemctl is-failed "$PP_SERVICE" >/dev/null 2>&1; then
        pass "service stopped retrying and entered failed state"
    else
        fail "service did not reach the failed state within the window"
    fi
    systemctl status "$PP_SERVICE" --no-pager 2>/dev/null | sed -n '1,6p' | while IFS= read -r l; do say "    $l"; done
    ratelimit_restore
    trap - INT TERM
    if [ "$(systemctl is-active "$PP_SERVICE" 2>/dev/null)" = active ]; then
        pass "config restored, service active"
    else
        fail "service not active after restore"
    fi
}

cmd_reboot_prepare() {
    section "Reboot persistence: prepare (P5-SVC-003)"
    if pp probe prepare; then
        note "prepared. Now reboot the device, then run: sh $0 reboot-verify"
    else
        fail "probe prepare failed"
    fi
}

cmd_reboot_verify() {
    section "Reboot persistence: verify (P5-SVC-003)"
    if pp probe verify; then
        pass "post-reboot probe passed"
    else
        fail "post-reboot probe failed"
    fi
    say "  restarts since boot: $(svc_prop NRestarts) (expect 0 for a clean start)"
}

cmd_broker_outage() {
    section "Broker outage and recovery (P5-SVC-004 / P5-SEC-004)"
    note "journald is Storage=none here, so watch MQTT/HA instead of the journal. In another window:"
    note "  mosquitto_sub -h <BROKER> -u <user> -P <pass> -t 'play-presence/#' -v"
    note "  (or watch the play_presence entities in Home Assistant)"
    if journal_has_entries; then
        note "Recent journal before outage:"
        journalctl -u "$PP_SERVICE" -n 8 --no-pager 2>/dev/null | while IFS= read -r l; do say "    $l"; done
    fi
    manual "Take the MQTT broker down ~2 min. Expect: entities go UNAVAILABLE (offline Last Will fires)."
    manual "Bring the broker back. Expect: reconnect republishes availability=online, current state, and artwork."
    if ! confirm "Continue when you have observed unavailable-then-recovered?"; then
        note "skipped"
        return 0
    fi
    if journal_has_entries; then
        note "Journal after recovery:"
        journalctl -u "$PP_SERVICE" -n 25 --no-pager 2>/dev/null | while IFS= read -r l; do say "    $l"; done
    fi
    manual "Confirm the entities returned in HA with the correct current state and artwork (no duplicates)."
}

cmd_diagnose() {
    section "Diagnostics"
    systemctl status "$PP_SERVICE" --no-pager -l 2>/dev/null | sed -n '1,12p' | while IFS= read -r l; do say "  $l"; done
    say "  ---"
    if [ -f /run/play-presence/last-failure.json ]; then
        note "last-failure.json:"
        while IFS= read -r l; do say "    $l"; done </run/play-presence/last-failure.json
    else
        note "no runtime failure record (/run/play-presence/last-failure.json absent)"
    fi
    say "  ---"
    if journal_has_entries; then
        note "recent journal:"
        journalctl -u "$PP_SERVICE" -n 20 --no-pager 2>/dev/null | while IFS= read -r l; do say "    $l"; done
    else
        note "journald has no entries for this unit (storage disabled or logs routed elsewhere)"
    fi
}

cmd_transitions() {
    section "Detection transition matrix (P5-SEC-004)"
    note "First, watch the MQTT state so you can see each transition. In another window:"
    note "  mosquitto_sub -h <BROKER> -u <user> -P <pass> -t 'play-presence/#' -v"
    note "  (or watch sensor.play_presence_current_game / binary_sensor.play_presence_playing in HA)"
    note "journald is Storage=none here, so the journal cannot show this - use the MQTT/HA view."
    manual "Then drive the device and confirm each is reflected once, correctly, in the state payload:"
    note "idle -> DGE game (state=playing, right game/system) -> idle"
    note "idle -> RetroArch (state=playing, right game/system/core) -> idle"
    note "same-core RetroArch switch between two ROMs (game field updates to the new ROM)"
    note "DGE -> RetroArch -> DGE back-to-back (each new game shows; no idle flicker between)"
}

cmd_artwork() {
    section "Artwork on device (P5-HW-ART-001 / P5-HW-ART-003)"
    manual "Start a game with a valid local image; confirm the artwork renders in HA (P5-HW-ART-001)"
    manual "Return to the launcher; confirm the image clears (P5-HW-ART-002 already recorded)"
    note "For P5-HW-ART-003, capture RSS with artwork loaded: sh $0 resources game 0 60"
}

cmd_all() {
    section "Automated non-destructive set"
    cmd_preconditions
    cmd_resources idle 120 60
    cmd_writes
    section "Summary"
    if [ "$FAILURES" -eq 0 ]; then
        say "  All automated checks passed."
    else
        say "  $FAILURES automated check(s) failed - see above."
    fi
    say ""
    say "  Run these individually (destructive, timed, or manual):"
    note "sh $0 supervision              # force-kill restart"
    note "sh $0 ratelimit                # invalid-config start limit (~${PP_RATELIMIT_WAIT}s)"
    note "sh $0 reboot-prepare           # then reboot, then reboot-verify"
    note "sh $0 broker-outage            # guided broker down/up"
    note "sh $0 resources idle 3600 60   # extended no-growth window"
    note "sh $0 resources game 0 60      # RSS snapshot while playing (artwork)"
    note "sh $0 transitions              # detection matrix checklist"
    note "sh $0 artwork                  # Home Assistant artwork checklist"
    [ -n "$LOG" ] && say "" && say "  Log: $LOG"
    return 0
}

usage() { sed -n '2,40p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; }

main() {
    command="${1:-help}"
    case "$command" in
    help | -h | --help) usage; return 0 ;;
    esac
    need_root
    setup_results
    shift 2>/dev/null || true
    case "$command" in
    preconditions) cmd_preconditions ;;
    resources) cmd_resources "$@" ;;
    writes) cmd_writes ;;
    supervision) cmd_supervision ;;
    ratelimit) cmd_ratelimit ;;
    reboot-prepare) cmd_reboot_prepare ;;
    reboot-verify) cmd_reboot_verify ;;
    broker-outage) cmd_broker_outage ;;
    transitions) cmd_transitions ;;
    artwork) cmd_artwork ;;
    diagnose) cmd_diagnose ;;
    all) cmd_all ;;
    *) say "Unknown command: $command"; usage; return 1 ;;
    esac
    [ "$FAILURES" -eq 0 ]
}

main "$@"
