"""Kanal listesi için 'şu an / sıradaki' EPG bilgisini tembel ve önbellekli getirir."""
import threading
import time
from collections import deque

from .qt import QObject, QTimer, Signal


class EpgService(QObject):
    updated = Signal()
    _arrived = Signal(str, object)

    TTL = 15 * 60

    def __init__(self, workers=3):
        super().__init__()
        self.provider = None
        self._cache = {}   # item_id -> (ts, programlar)
        self._pending = set()
        self._queue = deque()
        self._cv = threading.Condition()
        self._arrived.connect(self._on_arrived)
        self._notify = QTimer(self)
        self._notify.setSingleShot(True)
        self._notify.setInterval(150)
        self._notify.timeout.connect(self.updated.emit)
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def set_provider(self, provider):
        with self._cv:
            self.provider = provider
            self._cache.clear()
            self._pending.clear()
            self._queue.clear()

    def programs(self, item, fetch=True):
        c = self._cache.get(item.id)
        now = time.time()
        if c and (now - c[0] < self.TTL):
            return c[1]
        if fetch and item.id not in self._pending and self.provider is not None:
            self._pending.add(item.id)
            with self._cv:
                self._queue.append(item)
                while len(self._queue) > 60:
                    old = self._queue.popleft()
                    self._pending.discard(old.id)
                self._cv.notify()
        return c[1] if c else None

    def now_next(self, item, fetch=True):
        progs = self.programs(item, fetch)
        if not progs:
            return None, None
        now = time.time()
        cur = nxt = None
        for i, p in enumerate(progs):
            if p["start"] <= now < p["end"]:
                cur = p
                nxt = progs[i + 1] if i + 1 < len(progs) else None
                break
            if p["start"] > now and cur is None:
                nxt = p
                break
        return cur, nxt

    def _worker(self):
        while True:
            with self._cv:
                while not self._queue:
                    self._cv.wait()
                item = self._queue.pop()
                prov = self.provider
            try:
                progs = prov.short_epg(item) if prov else []
            except Exception:  # noqa: BLE001
                progs = []
            self._arrived.emit(item.id, (prov, progs))

    def _on_arrived(self, item_id, payload):
        prov, progs = payload
        self._pending.discard(item_id)
        if prov is not self.provider:
            return
        self._cache[item_id] = (time.time(), progs or [])
        if progs and not self._notify.isActive():
            self._notify.start()
