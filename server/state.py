"""Bounded process-local sessions and a shared per-IP token bucket (one worker)."""
import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Session:
    request: object
    places: list
    messages: dict


class SessionStore:
    def __init__(self, capacity=100, ttl=1800, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def _prune(self, now):
        for key in [key for key, (expires, _) in self.entries.items() if expires <= now]:
            del self.entries[key]

    def put(self, session):
        with self.lock:
            now = self.clock()
            self._prune(now)
            key = str(uuid4())
            self.entries[key] = (now + self.ttl, copy.deepcopy(session))
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
            return key

    def get(self, key):
        with self.lock:
            self._prune(self.clock())
            if key not in self.entries:
                return None
            self.entries.move_to_end(key)
            return copy.deepcopy(self.entries[key][1])


class TokenBuckets:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, ip, rate):
        with self.lock:
            now = self.clock()
            # Idle buckets are full again after a minute; discard them.
            while self.entries and next(iter(self.entries.values()))[1] <= now - 60:
                self.entries.popitem(last=False)
            tokens, last = self.entries.pop(ip, (float(rate), now))
            tokens = min(float(rate), tokens + (now - last) * rate / 60)
            allowed = tokens >= 1
            self.entries[ip] = (tokens - 1 if allowed else tokens, now)
            return allowed
