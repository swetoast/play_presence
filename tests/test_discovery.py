import json
from play_presence.config import DiscoveryConfig, MqttConfig
from play_presence.discovery import discovery_records

NEW_TOPICS = {
    "homeassistant/sensor/play_presence_current_game/config",
    "homeassistant/binary_sensor/play_presence_playing/config",
    "homeassistant/sensor/play_presence_system/config",
    "homeassistant/image/play_presence_current_game_artwork/config",
}
LEGACY_TOPICS = {
    "homeassistant/sensor/rg40xxv_game/config",
    "homeassistant/binary_sensor/rg40xxv_playing/config",
    "homeassistant/sensor/rg40xxv_system/config",
    "homeassistant/image/rg40xxv_artwork/config",
}

def records(include_system=False, enabled=True):
    return discovery_records(
        MqttConfig(topic_prefix="handheld"),
        DiscoveryConfig(enabled=enabled, include_system_sensor=include_system),
    )

def payloads(include_system=False):
    return {topic: json.loads(payload) if payload else None for topic, payload in records(include_system)}

def active_values(include_system=True):
    return [value for topic, value in payloads(include_system).items() if topic in NEW_TOPICS and value]

def test_default_discovery_has_new_topics_and_legacy_tombstones():
    values = payloads()
    assert set(values) == NEW_TOPICS | LEGACY_TOPICS
    assert values["homeassistant/sensor/play_presence_system/config"] is None
    assert all(values[topic] is None for topic in LEGACY_TOPICS)

def test_play_presence_ids_and_shared_device():
    values = payloads(True)
    active = active_values(True)
    assert [value["unique_id"] for value in active] == [
        "play_presence_current_game",
        "play_presence_playing",
        "play_presence_system",
        "play_presence_current_game_artwork",
    ]
    assert values["homeassistant/sensor/play_presence_current_game/config"]["default_entity_id"] == "sensor.play_presence_current_game"
    assert values["homeassistant/binary_sensor/play_presence_playing/config"]["default_entity_id"] == "binary_sensor.play_presence_playing"
    assert all(value["device"]["identifiers"] == ["play_presence"] for value in active)
    assert all(value["device"]["name"] == "Play Presence" for value in active)

def test_topics_and_availability():
    for topic, value in payloads(True).items():
        if topic in LEGACY_TOPICS:
            assert value is None
            continue
        assert value["availability_topic"] == "handheld/availability"
        assert value["payload_available"] == "online"
        assert value["payload_not_available"] == "offline"
        if "/image/" in topic:
            assert value["image_topic"] == "handheld/artwork"
        else:
            assert value["state_topic"] == "handheld/state"

def test_templates_are_public_and_null_safe():
    game = payloads()["homeassistant/sensor/play_presence_current_game/config"]
    template = game["json_attributes_template"]
    assert "default('idle')" in game["value_template"]
    assert "artwork_available" in template
    assert "artwork_content_type" in template
    for forbidden in ("pid", "process_start_ticks", "rom_path", "password", "power"):
        assert forbidden not in template

def test_playing_contract_and_system_opt_in():
    values = payloads()
    playing = values["homeassistant/binary_sensor/play_presence_playing/config"]
    assert playing["payload_on"] == "ON"
    assert playing["payload_off"] == "OFF"
    assert playing["device_class"] == "running"
    assert values["homeassistant/sensor/play_presence_system/config"] is None
    assert payloads(True)["homeassistant/sensor/play_presence_system/config"] is not None

def test_disabled_discovery_clears_new_and_legacy_topics():
    disabled = records(enabled=False)
    assert len(disabled) == 8
    assert all(payload == "" for _, payload in disabled)

def test_custom_prefix_and_compact_json():
    result = discovery_records(MqttConfig(), DiscoveryConfig(prefix="custom", include_system_sensor=True))
    assert all(topic.startswith("custom/") for topic, _ in result)
    for topic, payload in result:
        if topic.endswith(("rg40xxv_game/config", "rg40xxv_playing/config", "rg40xxv_system/config", "rg40xxv_artwork/config")):
            assert payload == ""
        else:
            assert json.loads(payload)
            assert "\n" not in payload
