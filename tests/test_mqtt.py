import json
from pathlib import Path
import pytest
from rg40xx_game_presence.config import ConfigError,MqttConfig
from rg40xx_game_presence.daemon import LocalState
from rg40xx_game_presence.detection import SessionCandidate
from rg40xx_game_presence.mqtt import ErrorLimiter,MqttPresence,PublicState,public_state_from_local
class Result:
 def __init__(self,rc=0,published=True):self.rc=rc;self.published=published
 def is_published(self):return self.published
class Client:
 def __init__(self,**kw):self.kwargs=kw;self.calls=[];self.on_connect=None;self.on_disconnect=None
 def username_pw_set(self,*a):self.calls.append(('credentials',*a))
 def will_set(self,*a,**k):self.calls.append(('will',*a,k))
 def reconnect_delay_set(self,*a,**k):self.calls.append(('reconnect',a,k))
 def max_queued_messages_set(self,*a):self.calls.append(('queue',*a))
 def connect_async(self,*a):self.calls.append(('connect',*a))
 def loop_start(self):self.calls.append(('loop_start',))
 def loop_stop(self):self.calls.append(('loop_stop',))
 def disconnect(self):self.calls.append(('disconnect',))
 def publish(self,topic,payload,qos,retain):self.calls.append(('publish',topic,payload,qos,retain));return Result()
def make(tmp_path,discovery=()):
 p=tmp_path/'pw';p.write_text('secret');cfg=MqttConfig(password_file=p);c=Client();m=MqttPresence(cfg,lambda **kw:(setattr(c,'kwargs',kw) or c),lambda:discovery);return m,c,cfg
def playing():return PublicState('playing','Test Game','Game Boy Advance','gba','gba_emu',None,'test.gba.zip',None)
def pubs(c,t):return [x for x in c.calls if x[0]=='publish' and x[1]==t]
def test_client_configuration(tmp_path):
 m,c,cfg=make(tmp_path);assert c.kwargs=={'client_id':'rg40xxv-game-presence','clean_session':True,'protocol':4};assert ('queue',8) in c.calls
def test_start(tmp_path):
 m,c,cfg=make(tmp_path);m.start();assert ('connect','10.0.0.5',1883,60) in c.calls and ('loop_start',) in c.calls
def test_disconnected_latest_only_and_reconnect(tmp_path):
 m,c,cfg=make(tmp_path,(('homeassistant/test/config','{}'),));m.update(playing());m.update(PublicState('idle',None,None,None,None,None,None,None));c.on_connect(c,None,{},0);assert len(pubs(c,cfg.state_topic))==1 and json.loads(pubs(c,cfg.state_topic)[0][2])['state']=='idle';assert pubs(c,'homeassistant/test/config')
def test_change_only_and_artwork(tmp_path):
 m,c,cfg=make(tmp_path);c.on_connect(c,None,{},0);state=playing();assert m.update(state,b'img');assert not m.update(state,b'img');assert len(pubs(c,cfg.state_topic))==1 and len(pubs(c,cfg.artwork_topic))==1
def test_reconnect_republishes_latest(tmp_path):
 m,c,cfg=make(tmp_path);m.update(playing(),b'img');c.on_connect(c,None,{},0);c.on_disconnect(c,None,1);c.on_connect(c,None,{},0);assert len(pubs(c,cfg.state_topic))==2 and len(pubs(c,cfg.artwork_topic))==2
def test_graceful_stop(tmp_path):
 m,c,cfg=make(tmp_path);m.start();c.on_connect(c,None,{},0);m.stop(True);assert pubs(c,cfg.availability_topic)[-1][2]=='offline' and ('disconnect',) in c.calls and ('loop_stop',) in c.calls
def test_rejected_auth(tmp_path):
 m,c,cfg=make(tmp_path);c.on_connect(c,None,{},5);assert not m.connected and not pubs(c,cfg.availability_topic)
def test_password_error(tmp_path):
 p=tmp_path/'empty';p.write_text('')
 with pytest.raises(ConfigError):MqttPresence(MqttConfig(password_file=p),client_factory=Client)
def test_public_state_boundary_and_idle_shape():
 s=SessionCandidate(123,456,'/tmp/gba.dge','/mnt/mmc/Roms/GBA/test.zip','/mnt/mmc/Roms','GBA','gba','GBA','gba',None,'test.zip',None);p=public_state_from_local(LocalState('playing',s,'Resolved',b'img','image/jpeg'));payload=p.to_json();assert p.game=='Resolved' and '/mnt/mmc' not in payload and '123' not in payload
 idle=json.loads(public_state_from_local(LocalState('idle',None)).to_json());assert idle['state']=='idle' and idle['artwork_available'] is False and idle['artwork_content_type'] is None
def test_error_limiter():
 values=iter([0.,10.,61.]);l=ErrorLimiter(60,lambda:next(values));assert l.allow('x') and not l.allow('x') and l.allow('x')
def test_recovery_failure_logged(tmp_path,caplog):
 m,c,cfg=make(tmp_path,(('homeassistant/test/config','{}'),));m.update(playing());orig=c.publish;calls=0
 def fail(topic,payload,qos,retain):
  nonlocal calls;calls+=1;r=orig(topic,payload,qos,retain);r.rc=4 if calls==1 else 0;return r
 c.publish=fail
 with caplog.at_level('WARNING'):c.on_connect(c,None,{},0)
 assert 'retained recovery was incomplete' in caplog.text
