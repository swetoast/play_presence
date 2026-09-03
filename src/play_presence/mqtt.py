"""Bounded MQTT presence and artwork transport using Paho MQTT 1.5.x."""
from __future__ import annotations
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from .config import ConfigError, MqttConfig
from .daemon import LocalState
_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class PublicState:
    state: str
    game: str | None
    system: str | None
    system_id: str | None
    emulator: str | None
    core: str | None
    rom_file: str | None
    started_at: str | None
    artwork_available: bool = False
    artwork_content_type: str | None = None
    def to_payload(self) -> dict[str, str | bool | None]:
        """Return only the approved game-focused MQTT state contract."""
        return {
            "state": self.state,
            "game": self.game,
            "system": self.system,
            "system_id": self.system_id,
            "emulator": self.emulator,
            "core": self.core,
            "rom_file": self.rom_file,
            "started_at": self.started_at,
            "artwork_available": self.artwork_available,
            "artwork_content_type": self.artwork_content_type,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

def public_state_from_local(local: LocalState) -> PublicState:
    session = local.session
    if local.state != "playing" or session is None:
        return PublicState("idle", None, None, None, None, None, None, None)
    return PublicState("playing", local.game or session.rom_file, session.system_name,
                       session.system_id, session.emulator, session.core,
                       session.rom_file, session.started_at,
                       local.artwork is not None, local.artwork_content_type)

def _read_password(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"cannot read MQTT password file: {type(exc).__name__}") from exc
    if not value:
        raise ConfigError("MQTT password file is empty")
    return value

class ErrorLimiter:
    def __init__(self, interval_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.interval_seconds = interval_seconds
        self.clock = clock
        self._last: dict[str, float] = {}
    def allow(self, key: str) -> bool:
        now = self.clock(); previous = self._last.get(key)
        if previous is not None and now - previous < self.interval_seconds:
            return False
        self._last[key] = now
        return True

class MqttPresence:
    def __init__(self, config: MqttConfig, client_factory: Callable[..., Any] | None = None,
                 discovery_provider: Callable[[], Iterable[tuple[str, str]]] | None = None) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._connected = False
        self._started = False
        self._latest: PublicState | None = None
        self._latest_artwork = b""
        self._last_state: str | None = None
        self._last_artwork: bytes | None = None
        self._pending_state = False
        self._pending_artwork = False
        self._limiter = ErrorLimiter()
        self._discovery_provider = discovery_provider or (lambda: ())
        if client_factory is None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError as exc:
                raise ConfigError("Paho MQTT is not installed") from exc
            client_factory = mqtt.Client
        self.client = client_factory(client_id=config.client_id, clean_session=True, protocol=4)
        self.client.username_pw_set(config.username, _read_password(config.password_file))
        self.client.will_set(config.availability_topic, payload="offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=2, max_delay=60)
        self.client.max_queued_messages_set(8)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def start(self) -> None:
        if self._started: return
        self._started = True
        self.client.connect_async(self.config.host, self.config.port, self.config.keepalive_seconds)
        self.client.loop_start()

    def _publish(self, topic: str, payload: str | bytes, label: str) -> Any | None:
        result = self.client.publish(topic, payload, qos=1, retain=True)
        rc = getattr(result, "rc", 0)
        if rc != 0:
            if self._limiter.allow(f"{label}-{rc}"):
                _LOGGER.warning("MQTT %s publish failed with code %s", label, rc)
            return None
        return result

    def _flush_latest(self) -> bool:
        with self._lock:
            if not self._connected or self._latest is None: return False
            payload = self._latest.to_json(); image = self._latest_artwork
            send_state = self._pending_state or payload != self._last_state
            send_art = self._pending_artwork or image != self._last_artwork
        state_ok = not send_state or self._publish(self.config.state_topic, payload, "state") is not None
        art_ok = not send_art or self._publish(self.config.artwork_topic, image, "artwork") is not None
        with self._lock:
            if state_ok and send_state: self._last_state = payload; self._pending_state = False
            elif send_state: self._pending_state = True
            if art_ok and send_art: self._last_artwork = image; self._pending_artwork = False
            elif send_art: self._pending_artwork = True
        return state_ok and art_ok and (send_state or send_art)

    def update(self, state: PublicState, artwork: bytes | None = None) -> bool:
        payload = state.to_json(); image = artwork or b""
        with self._lock:
            self._latest = state; self._latest_artwork = image
            self._pending_state = self._pending_state or payload != self._last_state
            self._pending_artwork = self._pending_artwork or image != self._last_artwork
        return self._flush_latest()

    def retry_pending(self) -> bool:
        """Retry only the bounded latest state/artwork after a transient rejection."""
        return self._flush_latest()

    def stop(self, graceful: bool = True) -> None:
        if not self._started: return
        if graceful and self.connected:
            result = self._publish(self.config.availability_topic, "offline", "offline")
            try:
                if result is None: raise RuntimeError("offline publish rejected")
                deadline = time.monotonic() + 2.0
                while not result.is_published() and time.monotonic() < deadline: time.sleep(0.05)
                if not result.is_published(): _LOGGER.warning("MQTT offline publication was not acknowledged before shutdown")
            except (AttributeError, RuntimeError, ValueError):
                _LOGGER.warning("MQTT offline publication status was unavailable during shutdown")
        try: self.client.disconnect()
        finally:
            self.client.loop_stop()
            with self._lock: self._connected = False
            self._started = False

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc != 0:
            with self._lock:
                self._connected = False
            if self._limiter.allow(f"connect-{rc}"):
                _LOGGER.warning("MQTT connection rejected with code %s", rc)
            return

        # Availability is the highest-priority retained message. Publishing it
        # before discovery prevents a bounded Paho queue from leaving the old
        # retained offline value in place.
        with self._lock:
            self._connected = True
            self._last_state = None
            self._last_artwork = None
            has_latest = self._latest is not None
            self._pending_state = has_latest
            self._pending_artwork = has_latest

        recovery_ok = True
        if self._publish(self.config.availability_topic, "online", "availability") is None:
            recovery_ok = False

        # Restore the latest game state and artwork before discovery traffic.
        if has_latest and not self._flush_latest():
            recovery_ok = False

        # Discovery is lower priority. Failed records are retried on the next
        # connection rather than being allowed to block availability.
        for topic, payload in tuple(self._discovery_provider()):
            if self._publish(topic, payload, "discovery") is None:
                recovery_ok = False

        if recovery_ok:
            _LOGGER.info("MQTT connected")
        else:
            _LOGGER.warning("MQTT connected but retained recovery was incomplete")

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        with self._lock: self._connected = False
        if rc != 0 and self._limiter.allow(f"disconnect-{rc}"):
            _LOGGER.warning("MQTT disconnected unexpectedly with code %s", rc)
        else: _LOGGER.info("MQTT disconnected")
