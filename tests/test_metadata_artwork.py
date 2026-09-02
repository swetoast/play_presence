from pathlib import Path
from rg40xx_game_presence.config import MetadataConfig
from rg40xx_game_presence.detection import SessionCandidate
from rg40xx_game_presence.metadata import TitleResolver,conservative_title

def item(root,relative):
 p=root/'GBA'/relative
 return SessionCandidate(1,1,'/tmp/gba.dge',str(p),str(root),'GBA','gba','Game Boy Advance','gba',None,p.name,None)
def test_real_filename_cleanup():
 assert conservative_title('Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba.zip')=='The Legend of Zelda - The Minish Cap'
 assert conservative_title('Super Mario All-Stars + Super Mario World (USA).sfc.zip')=='Super Mario All-Stars + Super Mario World'
 assert conservative_title('Legend of Zelda, The - Parallel Worlds.smc.zip')=='The Legend of Zelda - Parallel Worlds'
 assert conservative_title('Game (Special Edition).gba.zip')=='Game (Special Edition)'
def test_gamelist_image_bytes(tmp_path):
 system=tmp_path/'GBA';system.mkdir();rom=system/'Game.gba.zip';rom.write_bytes(b'x');images=system/'images';images.mkdir();(images/'Game.gba.jpg').write_bytes(b'\xff\xd8\xffJPEG')
 (system/'gamelist.xml').write_text('<gameList><game><path>./Game.gba.zip</path><name>Game Name</name><image>./images/Game.gba.jpg</image></game></gameList>')
 result=TitleResolver(MetadataConfig()).resolve_metadata(item(tmp_path,'Game.gba.zip'))
 assert result.title=='Game Name' and result.artwork==b'\xff\xd8\xffJPEG' and result.artwork_content_type=='image/jpeg'
def test_nested_mirrored_fallback(tmp_path):
 system=tmp_path/'GBA';(system/'sub').mkdir(parents=True);rom=system/'sub/Game.gba.zip';rom.write_bytes(b'x');(system/'images/sub').mkdir(parents=True);(system/'images/sub/Game.gba.png').write_bytes(b'\x89PNG\r\n\x1a\nPNG')
 result=TitleResolver(MetadataConfig()).resolve_metadata(item(tmp_path,'sub/Game.gba.zip'))
 assert result.artwork==b'\x89PNG\r\n\x1a\nPNG' and result.artwork_content_type=='image/png'
def test_rejects_symlink_and_oversize(tmp_path):
 system=tmp_path/'GBA';system.mkdir();rom=system/'Game.gba.zip';rom.write_bytes(b'x');outside=tmp_path/'outside.jpg';outside.write_bytes(b'x');(system/'gamelist.xml').write_text('<gameList><game><path>./Game.gba.zip</path><name>Game</name><image>./cover.jpg</image></game></gameList>');(system/'cover.jpg').symlink_to(outside)
 result=TitleResolver(MetadataConfig(artwork_max_bytes=1024)).resolve_metadata(item(tmp_path,'Game.gba.zip'))
 assert result.artwork is None

def test_rejects_extension_signature_mismatch(tmp_path):
 system=tmp_path/'GBA';system.mkdir();rom=system/'Game.gba.zip';rom.write_bytes(b'x');(system/'images').mkdir();(system/'images/Game.gba.jpg').write_bytes(b'not-a-jpeg')
 result=TitleResolver(MetadataConfig()).resolve_metadata(item(tmp_path,'Game.gba.zip'))
 assert result.artwork is None

def test_default_artwork_limit_is_two_mib():
 assert MetadataConfig().artwork_max_bytes == 2 * 1024 * 1024

def test_verified_aliases_are_preserved():
 from rg40xx_game_presence.config import DEFAULT_ALIASES
 assert DEFAULT_ALIASES['Nintendo - Nintendo 64'][0]=='n64'
 assert DEFAULT_ALIASES['Nintendo - Gameboy Advance'][0]=='gba'
 assert DEFAULT_ALIASES['Nintendo - Super Nintendo Entertainment System'][0]=='snes'
 assert DEFAULT_ALIASES['Mame'][0]=='mame'

def test_webp_signature_is_accepted(tmp_path):
 system=tmp_path/'GBA';system.mkdir();rom=system/'Game.gba.zip';rom.write_bytes(b'x');(system/'images').mkdir();payload=b'RIFF\x04\x00\x00\x00WEBPdata';(system/'images/Game.gba.webp').write_bytes(payload)
 result=TitleResolver(MetadataConfig()).resolve_metadata(item(tmp_path,'Game.gba.zip'))
 assert result.artwork==payload and result.artwork_content_type=='image/webp'

def test_oversized_regular_artwork_is_rejected(tmp_path):
 system=tmp_path/'GBA';system.mkdir();rom=system/'Game.gba.zip';rom.write_bytes(b'x');(system/'images').mkdir();(system/'images/Game.gba.jpg').write_bytes(b'\xff\xd8\xff'+b'x'*1024)
 result=TitleResolver(MetadataConfig(artwork_max_bytes=512)).resolve_metadata(item(tmp_path,'Game.gba.zip'))
 assert result.artwork is None
