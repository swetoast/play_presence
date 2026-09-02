from __future__ import annotations

import json


def _device():
    return {
        "identifiers": ["play_presence"],
        "name": "Play Presence",
        "manufacturer": "Anbernic",
        "model": "Play Presence",
    }


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def discovery_records(mqtt, config):
    prefix = config.prefix
    topics = (
        f"{prefix}/sensor/play_presence_current_game/config",
        f"{prefix}/binary_sensor/play_presence_playing/config",
        f"{prefix}/sensor/play_presence_system/config",
        f"{prefix}/image/play_presence_current_game_artwork/config",
    )
    legacy_topics = (
        f"{prefix}/sensor/rg40xxv_game/config",
        f"{prefix}/binary_sensor/rg40xxv_playing/config",
        f"{prefix}/sensor/rg40xxv_system/config",
        f"{prefix}/image/rg40xxv_artwork/config",
    )
    if not config.enabled:
        return tuple((topic, "") for topic in topics + legacy_topics)

    common = {
        "availability_topic": mqtt.availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": _device(),
    }
    game = {
        **common,
        "name": "Current game",
        "unique_id": "play_presence_current_game",
        "default_entity_id": "sensor.play_presence_current_game",
        "state_topic": mqtt.state_topic,
        "value_template": "{{ value_json.game if value_json.state | default('idle') == 'playing' and value_json.game | default(none) else 'Idle' }}",
        "json_attributes_topic": mqtt.state_topic,
        "json_attributes_template": "{{ {'state': value_json.state | default('idle'), 'system': value_json.system | default(none), 'system_id': value_json.system_id | default(none), 'emulator': value_json.emulator | default(none), 'core': value_json.core | default(none), 'rom_file': value_json.rom_file | default(none), 'started_at': value_json.started_at | default(none), 'artwork_available': value_json.artwork_available | default(false), 'artwork_content_type': value_json.artwork_content_type | default(none)} | tojson }}",
        "icon": "mdi:controller-classic",
    }
    playing = {
        **common,
        "name": "Playing",
        "unique_id": "play_presence_playing",
        "default_entity_id": "binary_sensor.play_presence_playing",
        "state_topic": mqtt.state_topic,
        "value_template": "{{ 'ON' if value_json.state | default('idle') == 'playing' else 'OFF' }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "running",
        "icon": "mdi:gamepad-variant",
    }
    artwork = {
        **common,
        "name": "Current game artwork",
        "unique_id": "play_presence_current_game_artwork",
        "default_entity_id": "image.play_presence_current_game_artwork",
        "image_topic": mqtt.artwork_topic,
    }

    records = [(topics[0], _json(game)), (topics[1], _json(playing))]
    if config.include_system_sensor:
        system = {
            **common,
            "name": "System",
            "unique_id": "play_presence_system",
            "default_entity_id": "sensor.play_presence_system",
            "state_topic": mqtt.state_topic,
            "value_template": "{{ value_json.system if value_json.state | default('idle') == 'playing' and value_json.system | default(none) else 'Idle' }}",
            "icon": "mdi:chip",
        }
        records.append((topics[2], _json(system)))
    else:
        records.append((topics[2], ""))
    records.append((topics[3], _json(artwork)))
    records.extend((topic, "") for topic in legacy_topics)
    return tuple(records)
