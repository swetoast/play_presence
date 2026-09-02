import json
from play_presence.config import DiscoveryConfig,MqttConfig
from play_presence.discovery import discovery_records

def records(system=False,enabled=True):return discovery_records(MqttConfig(topic_prefix='handheld'),DiscoveryConfig(enabled=enabled,include_system_sensor=system))
def payloads(system=False):return {t:(json.loads(p) if p else None) for t,p in records(system)}
def test_default_entities_include_artwork_and_system_tombstone():
 v=payloads();assert set(v)=={'homeassistant/sensor/rg40xxv_game/config','homeassistant/binary_sensor/rg40xxv_playing/config','homeassistant/sensor/rg40xxv_system/config','homeassistant/image/rg40xxv_artwork/config'};assert v['homeassistant/sensor/rg40xxv_system/config'] is None
def test_stable_ids_and_shared_device():
 v=payloads(True);ids=[x['unique_id'] for x in v.values() if x];assert ids==['rg40xxv_current_game','rg40xxv_playing','rg40xxv_system','rg40xxv_current_game_artwork'];devices=[x['device'] for x in v.values() if x];assert all(x==devices[0] for x in devices)
def test_topics_and_availability():
 for topic,v in payloads(True).items():
  assert v['availability_topic']=='handheld/availability' and v['payload_available']=='online' and v['payload_not_available']=='offline'
  if '/image/' in topic:assert v['image_topic']=='handheld/artwork'
  else:assert v['state_topic']=='handheld/state'
def test_templates_public_and_null_safe():
 game=payloads()['homeassistant/sensor/rg40xxv_game/config'];template=game['json_attributes_template'];assert "default('idle')" in game['value_template'];assert 'artwork_available' in template and 'artwork_content_type' in template
 for bad in ('pid','process_start_ticks','rom_path','password','power'):assert bad not in template
def test_playing_contract_and_system_opt_in():
 v=payloads();p=v['homeassistant/binary_sensor/rg40xxv_playing/config'];assert p['payload_on']=='ON' and p['payload_off']=='OFF' and p['device_class']=='running';assert v['homeassistant/sensor/rg40xxv_system/config'] is None;assert payloads(True)['homeassistant/sensor/rg40xxv_system/config']
def test_disable_clears_all_four_records():
 disabled=records(enabled=False);assert len(disabled)==4 and all(p=='' for _,p in disabled)
def test_custom_prefix_and_compact_json():
 result=discovery_records(MqttConfig(),DiscoveryConfig(prefix='custom',include_system_sensor=True));assert all(t.startswith('custom/') for t,_ in result);assert all(json.loads(p) and '\n' not in p for _,p in result)
