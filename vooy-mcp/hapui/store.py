"""Process-local TTL/LRU storage. All reads/writes are synchronized; no disk persistence."""
from collections import OrderedDict
from dataclasses import dataclass, field
from copy import deepcopy
import secrets
import threading
import time
from .schema import HapuiError

@dataclass
class Problem:
    proposal: object
    places: list
    source_status: dict
    notes: list = field(default_factory=list)
    place_flags: dict = field(default_factory=dict)
    problem_id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    board_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created: float = field(default_factory=time.monotonic)
    rev: int = 1
    state: dict = field(default_factory=lambda: {'yielded':set(),'weights':{},'added':[],'removed':[]})
    undo: list = field(default_factory=list)
    result: dict | None = None
    lock: object = field(default_factory=threading.Lock,repr=False)

    def checkpoint(self):
        self.undo.append(deepcopy(self.state));self.undo=self.undo[-10:]

class Store:
    def __init__(self,ttl=6*3600,capacity=500,clock=time.monotonic):
        self.ttl=ttl;self.capacity=capacity;self.clock=clock
        self._items=OrderedDict();self._tokens={};self._lock=threading.RLock()

    def _purge(self):
        for key,p in list(self._items.items()):
            if self.clock()-p.created>=self.ttl:self._remove(key)

    def _remove(self,key):
        p=self._items.pop(key);self._tokens.pop(p.board_token,None)

    def put(self,p):
        with self._lock:
            self._purge();p.created=self.clock()
            self._items[p.problem_id]=p;self._tokens[p.board_token]=p.problem_id
            while len(self._items)>self.capacity:self._remove(next(iter(self._items)))
        return p

    def get(self,key):
        with self._lock:
            self._purge();p=self._items.get(key)
            if p is None:raise HapuiError('problem_not_found','문제가 없거나 만료되었습니다','problem_id','다시 propose_plans를 불러 주세요')
            self._items.move_to_end(key);return p

    def by_token(self,token):
        with self._lock:
            self._purge();key=self._tokens.get(token)
            if key is None:raise HapuiError('board_not_found','보드가 없거나 만료되었습니다','token','다시 코스를 만들어 새 링크를 받아 주세요')
            return self.get(key)

STORE=Store()
