"""Local state machine and detector runner."""
from __future__ import annotations
import json, threading
from dataclasses import asdict,dataclass
from typing import Callable,Any
from .config import DetectionConfig
from .detection import SessionCandidate,next_interval,scan_candidates,select_candidate
@dataclass(frozen=True)
class LocalState:
    state:str; session:SessionCandidate|None; game:str|None=None; artwork:bytes|None=None; artwork_content_type:str|None=None
class SessionTracker:
    def __init__(self):self.current=None;self.pending_idle=False
    def update(self,detected):
        if detected is not None:
            changed=self.current is None or detected.identity!=self.current.identity or detected.started_at!=self.current.started_at
            self.current=detected;self.pending_idle=False;return LocalState('playing',detected),changed
        if self.current is None:self.pending_idle=False;return LocalState('idle',None),False
        if not self.pending_idle:self.pending_idle=True;return LocalState('playing',self.current),False
        self.current=None;self.pending_idle=False;return LocalState('idle',None),True
def local_state_json(state):return json.dumps({'state':state.state,'session':asdict(state.session) if state.session else None},ensure_ascii=True,sort_keys=True)
def run_local_detector(config,stop_event,on_change=None,title_resolver=None,metadata_resolver=None,on_poll=None):
    tracker=SessionTracker();emitted=False;identity=None;game=None;art=None;ctype=None
    while not stop_event.is_set():
        state,changed=tracker.update(select_candidate(scan_candidates(config),tracker.current))
        if state.state=='playing' and state.session:
            if state.session.identity!=identity:
                identity=state.session.identity
                if metadata_resolver:
                    value=metadata_resolver(state.session);game=value.title;art=value.artwork;ctype=value.artwork_content_type
                else: game=title_resolver(state.session) if title_resolver else state.session.rom_file;art=ctype=None
            state=LocalState('playing',state.session,game,art,ctype)
        else: identity=game=art=ctype=None;state=LocalState('idle',None)
        if (changed or not emitted) and on_change:on_change(state);emitted=True
        elif on_poll:on_poll()
        stop_event.wait(next_interval(config,state.state=='playing'))
