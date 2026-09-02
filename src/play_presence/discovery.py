from __future__ import annotations
import json

def _device():return {'identifiers':['rg40xxv_game_presence'],'name':'RG40XX V','manufacturer':'Anbernic','model':'RG40XX V'}
def _json(v):return json.dumps(v,ensure_ascii=True,separators=(',',':'),sort_keys=True)
def discovery_records(mqtt,config):
    p=config.prefix; topics=(f'{p}/sensor/rg40xxv_game/config',f'{p}/binary_sensor/rg40xxv_playing/config',f'{p}/sensor/rg40xxv_system/config',f'{p}/image/rg40xxv_artwork/config')
    if not config.enabled:return tuple((t,'') for t in topics)
    common={'availability_topic':mqtt.availability_topic,'payload_available':'online','payload_not_available':'offline','device':_device()}
    game={**common,'name':'Current game','unique_id':'rg40xxv_current_game','state_topic':mqtt.state_topic,'value_template':"{{ value_json.game if value_json.state | default('idle') == 'playing' and value_json.game | default(none) else 'Idle' }}",'json_attributes_topic':mqtt.state_topic,'json_attributes_template':"{{ {'state': value_json.state | default('idle'), 'system': value_json.system | default(none), 'system_id': value_json.system_id | default(none), 'emulator': value_json.emulator | default(none), 'core': value_json.core | default(none), 'rom_file': value_json.rom_file | default(none), 'started_at': value_json.started_at | default(none), 'artwork_available': value_json.artwork_available | default(false), 'artwork_content_type': value_json.artwork_content_type | default(none)} | tojson }}",'icon':'mdi:controller-classic'}
    playing={**common,'name':'Playing','unique_id':'rg40xxv_playing','state_topic':mqtt.state_topic,'value_template':"{{ 'ON' if value_json.state | default('idle') == 'playing' else 'OFF' }}",'payload_on':'ON','payload_off':'OFF','device_class':'running','icon':'mdi:gamepad-variant'}
    art={**common,'name':'Current game artwork','unique_id':'rg40xxv_current_game_artwork','image_topic':mqtt.artwork_topic}
    records=[(topics[0],_json(game)),(topics[1],_json(playing))]
    if config.include_system_sensor:
        system={**common,'name':'System','unique_id':'rg40xxv_system','state_topic':mqtt.state_topic,'value_template':"{{ value_json.system if value_json.state | default('idle') == 'playing' and value_json.system | default(none) else 'Idle' }}",'icon':'mdi:chip'}
        records.append((topics[2],_json(system)))
    else:records.append((topics[2],''))
    records.append((topics[3],_json(art)))
    return tuple(records)
