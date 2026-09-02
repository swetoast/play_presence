"""Command-line entry point for the project."""

from __future__ import annotations

import argparse
import signal
import sys
import logging
import threading
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .daemon import local_state_json, run_local_detector
from .discovery import discovery_records
from .metadata import TitleResolver
from .mqtt import MqttPresence, public_state_from_local
from .platform_probe import ProbeError, run_prepare, run_verify
from .validation import (
    ValidationError, collect as collect_validation, record_runtime_failure, write_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="play-presence")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    probe = commands.add_parser("probe", help="run Phase 0 platform verification")
    stages = probe.add_subparsers(dest="stage", required=True)

    prepare = stages.add_parser("prepare", help="perform pre-reboot checks")
    prepare.add_argument("--state-dir", default="/var/lib/play-presence-probe")
    prepare.add_argument("--no-systemd", action="store_true")
    prepare.add_argument("--mqtt-host", default="")
    prepare.add_argument("--mqtt-port", type=int, default=1883)
    prepare.add_argument("--mqtt-username", default="")
    prepare.add_argument("--mqtt-password-file", default="")

    verify = stages.add_parser("verify", help="perform post-reboot checks")
    verify.add_argument("--state-dir", default="/var/lib/play-presence-probe")
    verify.add_argument("--output", default="/mnt/mmc/play-presence-phase0-v0.1.0.json")
    verify.add_argument("--keep-artifacts", action="store_true")

    check = commands.add_parser("check-config", help="validate Phase 1 configuration")
    check.add_argument("--config", required=True)
    check.add_argument("--skip-password-file", action="store_true")

    run = commands.add_parser("run-local", help="run the Phase 1 detector without MQTT")
    run.add_argument("--config", required=True)

    service = commands.add_parser("run", help="run the complete presence daemon")
    service.add_argument("--config", required=True)

    validate = commands.add_parser("validate", help="collect bounded Phase 5 service evidence")
    validate.add_argument("--duration", type=int, default=0)
    validate.add_argument("--interval", type=int, default=60)
    validate.add_argument(
        "--output",
        type=Path,
        default=Path("/mnt/mmc/play-presence-validation-v0.6.8.json"),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    runtime_phase = "dispatch"
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "probe" and args.stage == "prepare":
            return run_prepare(
                args.state_dir,
                use_systemd=not args.no_systemd,
                mqtt_host=args.mqtt_host,
                mqtt_port=args.mqtt_port,
                mqtt_username=args.mqtt_username,
                mqtt_password_file=args.mqtt_password_file,
            )
        if args.command == "probe" and args.stage == "verify":
            return run_verify(args.state_dir, args.output, keep_artifacts=args.keep_artifacts)
        if args.command == "check-config":
            load_config(args.config, check_password_file=not args.skip_password_file)
            print("Configuration is valid.")
            return 0
        if args.command == "run-local":
            config = load_config(args.config)
            stop_event = threading.Event()
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda _signum, _frame: stop_event.set())
            run_local_detector(config.detection, stop_event, lambda state: print(local_state_json(state), flush=True))
            return 0
        if args.command == "run":
            runtime_phase = "load-config"
            config = load_config(args.config, check_password_file=True)
            stop_event = threading.Event()
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda _signum, _frame: stop_event.set())
            resolver = TitleResolver(config.metadata)
            mqtt = MqttPresence(
                config.mqtt,
                discovery_provider=lambda: discovery_records(config.mqtt, config.discovery),
            )
            runtime_phase = "mqtt-start"
            mqtt.start()
            try:
                runtime_phase = "detector"
                run_local_detector(
                    config.detection,
                    stop_event,
                    lambda state: mqtt.update(public_state_from_local(state), state.artwork),
                    metadata_resolver=resolver.resolve_metadata,
                    on_poll=mqtt.retry_pending,
                )
            finally:
                runtime_phase = "mqtt-stop"
                mqtt.stop(graceful=True)
            return 0
        if args.command == "validate":
            result = collect_validation(args.duration, args.interval)
            write_result(result, args.output)
            print(f"Validation result: {args.output}")
            return 0
    except (ProbeError, ConfigError, ValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if getattr(args, "command", None) == "run":
            record_runtime_failure(runtime_phase, exc)
        logging.getLogger(__name__).exception("Fatal daemon error during %s", runtime_phase)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
