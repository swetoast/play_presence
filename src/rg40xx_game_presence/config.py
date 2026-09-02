"""Configuration loading and validation."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

class ConfigError(ValueError): pass
DEFAULT_ALIASES={"N64":("n64","Nintendo 64"),"Nintendo - Nintendo 64":("n64","Nintendo 64"),"GBA":("gba","Game Boy Advance"),"Nintendo - Gameboy Advance":("gba","Game Boy Advance"),"GB":("gb","Game Boy"),"GBC":("gbc","Game Boy Color"),"FC":("nes","Nintendo Entertainment System"),"NES":("nes","Nintendo Entertainment System"),"SFC":("snes","Super Nintendo"),"SNES":("snes","Super Nintendo"),"Nintendo - Super Nintendo Entertainment System":("snes","Super Nintendo"),"MD":("genesis","Mega Drive"),"GENESIS":("genesis","Mega Drive"),"SMS":("sms","Master System"),"GG":("gamegear","Game Gear"),"PCE":("pce","PC Engine"),"NGPC":("ngpc","Neo Geo Pocket Color"),"WS":("ws","WonderSwan"),"WSC":("wsc","WonderSwan Color"),"MAME":("mame","Arcade"),"Mame":("mame","Arcade"),"FBNEO":("fbneo","Arcade (NeoGeo)"),"FBA":("fba","Arcade"),"OPENBOR":("openbor","OpenBOR")}
@dataclass(frozen=True)
class PollConfig: playing_seconds:float=5; idle_usb_seconds:float=5; idle_battery_seconds:float=10; unknown_power_seconds:float=5
@dataclass(frozen=True)
class DetectionConfig:
    rom_roots:tuple[Path,...]=(Path('/mnt/mmc/Roms'),); retroarch_executable:Path=Path('/mnt/vendor/deep/retro/retroarch'); power_online_path:Path=Path('/sys/class/power_supply/axp2202-usb/online'); poll:PollConfig=field(default_factory=PollConfig); aliases:dict[str,tuple[str,str]]=field(default_factory=lambda:dict(DEFAULT_ALIASES))
@dataclass(frozen=True)
class MqttConfig:
    host:str='10.0.0.5'; port:int=1883; username:str='rg40xxv'; password_file:Path=Path('/etc/rg40xx-game-presence/mqtt-password'); client_id:str='rg40xxv-game-presence'; topic_prefix:str='rg40xxv'; keepalive_seconds:int=60
    @property
    def availability_topic(self): return f'{self.topic_prefix}/availability'
    @property
    def state_topic(self): return f'{self.topic_prefix}/state'
    @property
    def artwork_topic(self): return f'{self.topic_prefix}/artwork'
@dataclass(frozen=True)
class MetadataConfig:
    gamelist_filename:str='gamelist.xml'; overrides_file:Path|None=None; overrides_max_bytes:int=1048576; artwork_max_bytes:int=2097152
@dataclass(frozen=True)
class DiscoveryConfig: enabled:bool=True; include_system_sensor:bool=False; prefix:str='homeassistant'
@dataclass(frozen=True)
class AppConfig: detection:DetectionConfig=field(default_factory=DetectionConfig); mqtt:MqttConfig=field(default_factory=MqttConfig); discovery:DiscoveryConfig=field(default_factory=DiscoveryConfig); metadata:MetadataConfig=field(default_factory=MetadataConfig)
def _reject(v,a,l):
    u=sorted(set(v)-a)
    if u: raise ConfigError(f'{l} contains unknown key: {u[0]}')
def _nonempty(v,l):
    if not isinstance(v,str) or not v.strip(): raise ConfigError(f'{l} must be a non-empty string')
    return v.strip()
def _abs(v,l):
    if not isinstance(v,str) or not v or not Path(v).is_absolute(): raise ConfigError(f'{l} must be an absolute path')
    return Path(v)
def _int(v,l,lo,hi):
    if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi: raise ConfigError(f'{l} must be an integer from {lo} to {hi}')
    return v
def _pos(v,l):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or v<=0: raise ConfigError(f'{l} must be a positive number')
    return float(v)
def _bool(v,l):
    if not isinstance(v,bool): raise ConfigError(f'{l} must be a boolean')
    return v
def _topic(v):
    x=_nonempty(v,'mqtt.topic_prefix').strip('/')
    if '#' in x or '+' in x: raise ConfigError('mqtt.topic_prefix must not contain MQTT wildcards')
    return x
def load_config(path,check_password_file=False):
    try: raw=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError) as e: raise ConfigError(f'cannot read configuration: {type(e).__name__}') from e
    if not isinstance(raw,dict): raise ConfigError('configuration root must be an object')
    _reject(raw,{'detection','mqtt','home_assistant','metadata'},'configuration')
    d=raw.get('detection',{})
    if not isinstance(d,dict): raise ConfigError('detection must be an object')
    _reject(d,{'rom_roots','retroarch_executable','power_online_path','playing_poll_seconds','idle_usb_poll_seconds','idle_battery_poll_seconds','unknown_power_poll_seconds','system_aliases'},'detection')
    roots_raw=d.get('rom_roots',['/mnt/mmc/Roms'])
    if not isinstance(roots_raw,list) or not roots_raw: raise ConfigError('detection.rom_roots must be a non-empty list')
    roots=tuple(_abs(x,'detection.rom_roots entry') for x in roots_raw)
    if len(set(roots)) != len(roots): raise ConfigError('detection.rom_roots contains duplicates')
    aliases=dict(DEFAULT_ALIASES)
    aliases_raw=d.get('system_aliases',{})
    if not isinstance(aliases_raw,dict): raise ConfigError('detection.system_aliases must be an object')
    for folder,val in aliases_raw.items():
        if not isinstance(folder,str) or not folder.strip() or not isinstance(val,dict): raise ConfigError('each system alias must be an object with a non-empty folder name')
        _reject(val,{'id','name'},f'system alias {folder}'); aliases[folder]=(_nonempty(val.get('id'), 'system alias id'),_nonempty(val.get('name'),'system alias name'))
    m=raw.get('mqtt',{})
    if not isinstance(m,dict): raise ConfigError('mqtt must be an object')
    _reject(m,{'host','port','username','password_file','client_id','topic_prefix','keepalive_seconds'},'mqtt')
    pw=_abs(m.get('password_file','/etc/rg40xx-game-presence/mqtt-password'),'mqtt.password_file')
    if check_password_file:
        try: secret=pw.read_text(encoding='utf-8').strip()
        except OSError as e: raise ConfigError(f'cannot read MQTT password file: {type(e).__name__}') from e
        if not secret: raise ConfigError('MQTT password file is empty')
    md=raw.get('metadata',{})
    if not isinstance(md,dict): raise ConfigError('metadata must be an object')
    _reject(md,{'gamelist_filename','overrides_file','overrides_max_bytes','artwork_max_bytes'},'metadata')
    fn=_nonempty(md.get('gamelist_filename','gamelist.xml'),'metadata.gamelist_filename')
    if Path(fn).name!=fn: raise ConfigError('metadata.gamelist_filename must be a filename')
    ov=md.get('overrides_file','')
    h=raw.get('home_assistant',{})
    if not isinstance(h,dict): raise ConfigError('home_assistant must be an object')
    _reject(h,{'enabled','include_system_sensor','discovery_prefix'},'home_assistant')
    return AppConfig(
      DetectionConfig(roots,_abs(d.get('retroarch_executable','/mnt/vendor/deep/retro/retroarch'),'detection.retroarch_executable'),_abs(d.get('power_online_path','/sys/class/power_supply/axp2202-usb/online'),'detection.power_online_path'),PollConfig(_pos(d.get('playing_poll_seconds',5),'playing_poll_seconds'),_pos(d.get('idle_usb_poll_seconds',5),'idle_usb_poll_seconds'),_pos(d.get('idle_battery_poll_seconds',10),'idle_battery_poll_seconds'),_pos(d.get('unknown_power_poll_seconds',5),'unknown_power_poll_seconds')),aliases),
      MqttConfig(_nonempty(m.get('host','10.0.0.5'),'mqtt.host'),_int(m.get('port',1883),'mqtt.port',1,65535),_nonempty(m.get('username','rg40xxv'),'mqtt.username'),pw,_nonempty(m.get('client_id','rg40xxv-game-presence'),'mqtt.client_id'),_topic(m.get('topic_prefix','rg40xxv')),_int(m.get('keepalive_seconds',60),'mqtt.keepalive_seconds',10,3600)),
      DiscoveryConfig(_bool(h.get('enabled',True),'home_assistant.enabled'),_bool(h.get('include_system_sensor',False),'home_assistant.include_system_sensor'),_topic(h.get('discovery_prefix','homeassistant'))),
      MetadataConfig(fn,_abs(ov,'metadata.overrides_file') if ov else None,_int(md.get('overrides_max_bytes',1048576),'metadata.overrides_max_bytes',1,16777216),_int(md.get('artwork_max_bytes',2097152),'metadata.artwork_max_bytes',1024,16777216)))
