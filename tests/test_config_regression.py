import json
import pytest
from play_presence.config import ConfigError, load_config

def write(tmp_path,value):
 p=tmp_path/'config.json';p.write_text(json.dumps(value));return p

def test_duplicate_rom_roots_still_rejected(tmp_path):
 with pytest.raises(ConfigError):load_config(write(tmp_path,{'detection':{'rom_roots':['/a','/a']}}))

def test_non_object_sections_still_rejected(tmp_path):
 for section in ('detection','mqtt','metadata','home_assistant'):
  with pytest.raises(ConfigError):load_config(write(tmp_path,{section:[]}))

def test_existing_config_without_artwork_key_remains_valid(tmp_path):
 cfg=load_config(write(tmp_path,{}));assert cfg.metadata.artwork_max_bytes==2*1024*1024
