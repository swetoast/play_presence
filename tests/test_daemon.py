from pathlib import Path
from rg40xx_game_presence.daemon import SessionTracker,local_state_json
from rg40xx_game_presence.detection import SessionCandidate

def item(pid,ticks,name):
 p=f'/mnt/mmc/Roms/GBA/{name}.zip';return SessionCandidate(pid,ticks,'/tmp/gba.dge',p,'/mnt/mmc/Roms','GBA','gba','Game Boy Advance','gba',None,Path(p).name,None)
def test_idle_play_change_and_confirmed_idle():
 t=SessionTracker();assert t.update(None)[0].state=='idle';a=item(1,100,'First');b=item(2,200,'Second');assert t.update(a)[1];assert t.update(b)[1];assert t.update(None)[0].state=='playing';assert t.update(None)[0].state=='idle'
def test_replacement_cancels_pending_idle():
 t=SessionTracker();a=item(1,100,'First');b=item(2,200,'Second');t.update(a);t.update(None);state,changed=t.update(b);assert state.session==b and changed and not t.pending_idle
def test_same_identity_and_json_safe():
 t=SessionTracker();a=item(1,100,'Game');t.update(a);state,changed=t.update(a);assert not changed and 'Game.zip' in local_state_json(state)
def test_detector_emits_initial_idle(monkeypatch):
 import threading
 from rg40xx_game_presence import daemon
 from rg40xx_game_presence.config import DetectionConfig
 stop=threading.Event();seen=[];monkeypatch.setattr(daemon,'scan_candidates',lambda c:[]);monkeypatch.setattr(daemon,'next_interval',lambda c,p:5)
 def get(s):seen.append(s);stop.set()
 daemon.run_local_detector(DetectionConfig(),stop,get);assert len(seen)==1 and seen[0].state=='idle'
def test_title_resolved_only_on_identity_change(monkeypatch):
 import threading
 from rg40xx_game_presence import daemon
 from rg40xx_game_presence.config import DetectionConfig
 first=item(1,100,'First');scans=iter([[first],[first],[],[]]);stop=threading.Event();resolved=[];seen=[]
 monkeypatch.setattr(daemon,'scan_candidates',lambda c:next(scans));monkeypatch.setattr(daemon,'select_candidate',lambda cs,current:cs[0] if cs else None);monkeypatch.setattr(daemon,'next_interval',lambda c,p:0)
 def recv(s):seen.append(s);stop.set() if s.state=='idle' else None
 daemon.run_local_detector(DetectionConfig(),stop,recv,title_resolver=lambda s:resolved.append(s.identity) or 'Resolved')
 assert resolved==[first.identity] and seen[0].game=='Resolved' and seen[-1].state=='idle'
def test_poll_callback_runs_without_visible_change(monkeypatch):
 import threading
 from rg40xx_game_presence import daemon
 from rg40xx_game_presence.config import DetectionConfig
 first=item(1,100,'First');scans=iter([[first],[first]]);stop=threading.Event();poll=[];seen=[]
 monkeypatch.setattr(daemon,'scan_candidates',lambda c:next(scans));monkeypatch.setattr(daemon,'select_candidate',lambda cs,current:cs[0]);monkeypatch.setattr(daemon,'next_interval',lambda c,p:0)
 def recv(s):seen.append(s)
 def on_poll():poll.append(1);stop.set()
 daemon.run_local_detector(DetectionConfig(),stop,recv,on_poll=on_poll)
 assert len(seen)==1 and poll==[1]
