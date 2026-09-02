import json
from pathlib import Path
import pytest
from rg40xx_game_presence.config import MetadataConfig
from rg40xx_game_presence.detection import SessionCandidate
from rg40xx_game_presence.metadata import MetadataError,TitleResolver,conservative_title,load_overrides,metadata_location,stream_gamelist_title

def candidate(root,system,relative):
 rom=root/system/relative;return SessionCandidate(1,100,'/tmp/emulator.dge',str(rom),str(root),system,'mame' if system=='MAME' else 'n64','Arcade' if system=='MAME' else 'Nintendo 64','xmame' if system=='MAME' else 'retroarch',None,rom.name,None)
def write_gamelist(path,games):
 rows=[]
 for gp,name in games:rows.append(f'<game><path>{gp}</path>{f"<name>{name}</name>" if name is not None else ""}<desc>ignored</desc></game>')
 path.write_text('<gameList>'+''.join(rows)+'</gameList>')
def test_metadata_location_compatibility(tmp_path):
 assert metadata_location(candidate(tmp_path,'N64','game.n64.zip'),MetadataConfig())==(tmp_path/'N64/gamelist.xml','./game.n64.zip');assert metadata_location(candidate(tmp_path,'MAME','sub/simpsons.zip'),MetadataConfig())==(tmp_path/'MAME/gamelist.xml','./sub/simpsons.zip')
def test_stream_match_namespace_and_missing(tmp_path):
 p=tmp_path/'gamelist.xml';write_gamelist(p,[('./other.zip','Other'),('./game.zip','Title')]);assert stream_gamelist_title(p,'./game.zip')=='Title';assert stream_gamelist_title(p,'./missing.zip') is None
 p.write_text('<gameList xmlns="urn:test"><game><path>./game.zip</path><name>Namespaced</name></game></gameList>');assert stream_gamelist_title(p,'./game.zip')=='Namespaced'
def test_missing_and_malformed_are_errors(tmp_path):
 with pytest.raises(MetadataError):stream_gamelist_title(tmp_path/'missing.xml','./game.zip')
 p=tmp_path/'bad.xml';p.write_text('<gameList><game>')
 with pytest.raises(MetadataError):stream_gamelist_title(p,'./game.zip')
def test_gamelist_precedes_override_and_override_fallback(tmp_path):
 system=tmp_path/'N64';system.mkdir();write_gamelist(system/'gamelist.xml',[('./game.n64.zip','Scraped')]);o=tmp_path/'o.json';o.write_text(json.dumps({'n64:./game.n64.zip':'Override'}));r=TitleResolver(MetadataConfig(overrides_file=o));assert r.resolve(candidate(tmp_path,'N64','game.n64.zip'))=='Scraped';(system/'gamelist.xml').unlink();assert TitleResolver(MetadataConfig(overrides_file=o)).resolve(candidate(tmp_path,'N64','game.n64.zip'))=='Override'
def test_override_bounded(tmp_path):
 p=tmp_path/'o.json';p.write_text('{"n64:./game.zip":"Title"}');assert load_overrides(MetadataConfig(overrides_file=p))['n64:./game.zip']=='Title'
 with pytest.raises(MetadataError):load_overrides(MetadataConfig(overrides_file=p,overrides_max_bytes=2))
@pytest.mark.parametrize(('filename','expected'),[('007 - GoldenEye (Europe).n64.zip','007 - GoldenEye'),('Super_Mario_World_(USA)_[!].sfc.zip','Super Mario World'),('Game (Rev 1).gba','Game'),('Collection 2.zip','Collection 2'),('simpsons.zip','simpsons'),('Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba.zip','The Legend of Zelda - The Minish Cap')])
def test_conservative_fallback(filename,expected):assert conservative_title(filename)==expected
def test_scraped_and_unscraped_mame(tmp_path):
 s=tmp_path/'MAME';s.mkdir();write_gamelist(s/'gamelist.xml',[('./simpsons.zip','The Simpsons')]);r=TitleResolver(MetadataConfig());assert r.resolve(candidate(tmp_path,'MAME','simpsons.zip'))=='The Simpsons';assert r.resolve(candidate(tmp_path,'MAME','pacman.zip'))=='pacman'
def test_malformed_falls_back_without_path_leak(tmp_path,caplog):
 s=tmp_path/'N64';s.mkdir();(s/'gamelist.xml').write_text('<broken');item=candidate(tmp_path,'N64','Secret Folder/Game (USA).n64.zip')
 with caplog.at_level('WARNING'):assert TitleResolver(MetadataConfig()).resolve(item)=='Game'
 assert str(tmp_path) not in caplog.text and 'Secret Folder' not in caplog.text
def test_stream_stops_after_match(tmp_path):
 p=tmp_path/'g.xml';p.write_text('<gameList><game><path>./game.zip</path><name>Title</name></game><broken');assert stream_gamelist_title(p,'./game.zip')=='Title'
