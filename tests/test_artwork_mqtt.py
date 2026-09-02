import json
from pathlib import Path
from rg40xx_game_presence.config import MqttConfig,DiscoveryConfig
from rg40xx_game_presence.discovery import discovery_records
from rg40xx_game_presence.mqtt import MqttPresence,PublicState
class R:
 rc=0
 def is_published(self):return True
class C:
 def __init__(self,**kw):self.calls=[]
 def username_pw_set(self,*a):pass
 def will_set(self,*a,**k):pass
 def reconnect_delay_set(self,*a,**k):pass
 def max_queued_messages_set(self,*a):pass
 def publish(self,*a,**k):self.calls.append((a,k));return R()
 def connect_async(self,*a):pass
 def loop_start(self):pass
 def loop_stop(self):pass
 def disconnect(self):pass
def setup(tmp_path):
 p=tmp_path/'pw';p.write_text('x');cfg=MqttConfig(password_file=p);c=C();m=MqttPresence(cfg,lambda **kw:c,lambda:discovery_records(cfg,DiscoveryConfig()));m.client.on_connect(c,None,{},0);return m,c,cfg
def test_discovery_image_entity(tmp_path):
 m,c,cfg=setup(tmp_path); payloads=[a for a,k in c.calls if a[0].endswith('/image/rg40xxv_artwork/config')]; assert payloads; assert json.loads(payloads[-1][1])['image_topic']==cfg.artwork_topic
def test_binary_artwork_and_idle_tombstone(tmp_path):
 m,c,cfg=setup(tmp_path);playing=PublicState('playing','Game','GBA','gba','retroarch',None,'Game.zip',None,True,'image/jpeg');assert m.update(playing,b'JPEG');assert any(a[0]==cfg.artwork_topic and a[1]==b'JPEG' for a,k in c.calls);idle=PublicState('idle',None,None,None,None,None,None,None);assert m.update(idle,b'');assert any(a[0]==cfg.artwork_topic and a[1]==b'' for a,k in c.calls)
def test_reconnect_republishes_artwork(tmp_path):
 m,c,cfg=setup(tmp_path);m.update(PublicState('playing','Game','GBA','gba','retroarch',None,'Game.zip',None,True,'image/png'),b'PNG');before=len([1 for a,k in c.calls if a[0]==cfg.artwork_topic]);m.client.on_disconnect(c,None,1);m.client.on_connect(c,None,{},0);after=len([1 for a,k in c.calls if a[0]==cfg.artwork_topic]);assert after==before+1

def test_artwork_failure_remains_pending_and_retries(tmp_path):
    m,c,cfg=setup(tmp_path)
    original=c.publish
    failed={"done":False}
    def publish(topic,payload,**kwargs):
        result=original(topic,payload,**kwargs)
        if topic==cfg.artwork_topic and not failed["done"]:
            failed["done"]=True
            result.rc=1
        return result
    c.publish=publish
    state=PublicState('playing','Game','GBA','gba','retroarch',None,'Game.zip',None,True,'image/jpeg')
    assert not m.update(state,b'\xff\xd8\xffDATA')
    assert m.retry_pending()
    artwork=[a for a,k in c.calls if a[0]==cfg.artwork_topic]
    assert len(artwork)>=2
