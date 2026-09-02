import json
from pathlib import Path
import pytest
from rg40xx_game_presence.config import ConfigError, load_config

def write_config(tmp_path: Path, value: object) -> Path:
    path=tmp_path/'config.json';path.write_text(json.dumps(value),encoding='utf-8');return path

def test_defaults(tmp_path):
    c=load_config(write_config(tmp_path,{}));assert c.detection.rom_roots==(Path('/mnt/mmc/Roms'),);assert c.detection.poll.idle_battery_seconds==10;assert c.detection.aliases['SFC']==('snes','Super Nintendo');assert c.metadata.artwork_max_bytes==2097152

def test_custom_alias_and_intervals(tmp_path):
    c=load_config(write_config(tmp_path,{'detection':{'rom_roots':['/mnt/mmc/Roms','/mnt/sdcard/Roms'],'playing_poll_seconds':4,'system_aliases':{'PS':{'id':'psx','name':'PlayStation'}}}}));assert c.detection.poll.playing_seconds==4;assert c.detection.aliases['PS']==('psx','PlayStation')
@pytest.mark.parametrize('value',[0,-1,True,'5'])
def test_invalid_interval(tmp_path,value):
    with pytest.raises(ConfigError,match='positive number'):load_config(write_config(tmp_path,{'detection':{'playing_poll_seconds':value}}))
def test_rejects_relative_rom_root(tmp_path):
    with pytest.raises(ConfigError,match='absolute path'):load_config(write_config(tmp_path,{'detection':{'rom_roots':['Roms']}}))
def test_error_does_not_echo_document(tmp_path):
    p=tmp_path/'config.json';p.write_text('{"password":"do-not-leak"')
    with pytest.raises(ConfigError) as e:load_config(p)
    assert 'do-not-leak' not in str(e.value)
def test_mqtt_configuration_and_topics(tmp_path):
    pw=tmp_path/'pw';pw.write_text('secret\n');c=load_config(write_config(tmp_path,{'mqtt':{'host':'broker.local','port':1884,'username':'device','password_file':str(pw),'client_id':'presence','topic_prefix':'/handheld/presence/','keepalive_seconds':90}}),check_password_file=True);assert c.mqtt.host=='broker.local';assert c.mqtt.availability_topic=='handheld/presence/availability';assert c.mqtt.state_topic=='handheld/presence/state';assert c.mqtt.artwork_topic=='handheld/presence/artwork'
def test_mqtt_password_file_checked(tmp_path):
    with pytest.raises(ConfigError,match='cannot read MQTT password file'):load_config(write_config(tmp_path,{'mqtt':{'password_file':str(tmp_path/'missing')}}),check_password_file=True)
@pytest.mark.parametrize('prefix',['','bad/#','bad/+'])
def test_rejects_invalid_topic_prefix(tmp_path,prefix):
    with pytest.raises(ConfigError):load_config(write_config(tmp_path,{'mqtt':{'topic_prefix':prefix}}))
def test_home_assistant_defaults_and_configuration(tmp_path):
    c=load_config(write_config(tmp_path,{}));assert c.discovery.enabled and not c.discovery.include_system_sensor and c.discovery.prefix=='homeassistant'
    c=load_config(write_config(tmp_path,{'home_assistant':{'enabled':False,'include_system_sensor':True,'discovery_prefix':'ha-test'}}));assert not c.discovery.enabled and c.discovery.include_system_sensor and c.discovery.prefix=='ha-test'
@pytest.mark.parametrize('field',['enabled','include_system_sensor'])
def test_home_assistant_flags_require_booleans(tmp_path,field):
    with pytest.raises(ConfigError,match='boolean'):load_config(write_config(tmp_path,{'home_assistant':{field:'yes'}}))
def test_metadata_configuration(tmp_path):
    o=tmp_path/'overrides.json';c=load_config(write_config(tmp_path,{'metadata':{'gamelist_filename':'games.xml','overrides_file':str(o),'overrides_max_bytes':4096,'artwork_max_bytes':1024}}));assert c.metadata.gamelist_filename=='games.xml' and c.metadata.overrides_file==o and c.metadata.overrides_max_bytes==4096 and c.metadata.artwork_max_bytes==1024
def test_metadata_filename_must_not_be_path(tmp_path):
    with pytest.raises(ConfigError,match='must be a filename'):load_config(write_config(tmp_path,{'metadata':{'gamelist_filename':'sub/games.xml'}}))
@pytest.mark.parametrize(('document','label'),[({'detection':{'polling_typo':5}},'detection'),({'mqtt':{'usernmae':'bad'}},'mqtt'),({'metadata':{'game_list':'bad.xml'}},'metadata'),({'home_assistant':{'discovery_enabled':True}},'home_assistant'),({'detection':{'system_aliases':{'X':{'id':'x','name':'X','extra':True}}}},'system alias X')])
def test_unknown_keys_rejected(tmp_path,document,label):
    with pytest.raises(ConfigError,match=label):load_config(write_config(tmp_path,document))
