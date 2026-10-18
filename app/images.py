"""Poster/logo görsellerini arka planda indirip ölçekleyen, disk + bellek önbellekli yükleyici."""
import hashlib
import os
import threading
from collections import OrderedDict, deque

import requests

from .config import IMAGE_CACHE_DIR
from .qt import QImage, QObject, QPixmap, QSize, Qt, QTimer, Signal


class ImageLoader(QObject):
    loaded = Signal()           # bir veya daha fazla görsel hazır (toplu bildirim)
    _arrived = Signal(str, object)

    def __init__(self, workers=6, mem_items=900):
        super().__init__()
        self._mem = OrderedDict()
        self._mem_max = mem_items
        self._failed = set()
        self._pending = set()
        self._stack = deque()
        self._cv = threading.Condition()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ONRIPTV"
        adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers * 2)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._arrived.connect(self._on_arrived)
        self._notify = QTimer(self)
        self._notify.setSingleShot(True)
        self._notify.setInterval(60)
        self._notify.timeout.connect(self.loaded.emit)
        self._generation = 0
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    @staticmethod
    def _key(url, w, h):
        return f"{w}x{h}|{url}"

    def get(self, url, w, h):
        """Hazırsa QPixmap döner; değilse None döner ve yüklemeyi sıraya koyar."""
        if not url:
            return None
        k = self._key(url, w, h)
        pm = self._mem.get(k)
        if pm is not None:
            self._mem.move_to_end(k)
            return pm
        if k in self._failed or k in self._pending:
            return None
        self._pending.add(k)
        with self._cv:
            self._stack.append((k, url, w, h, self._generation))
            # Çok eski istekleri at; en son görünenler önceliklidir (LIFO)
            while len(self._stack) > 400:
                old = self._stack.popleft()
                self._pending.discard(old[0])
            self._cv.notify()
        return None

    def cancel_pending(self):
        """Sayfa değişince sırada bekleyenleri iptal eder."""
        with self._cv:
            for it in self._stack:
                self._pending.discard(it[0])
            self._stack.clear()
            self._generation += 1

    def _worker(self):
        while True:
            with self._cv:
                while not self._stack:
                    self._cv.wait()
                k, url, w, h, _gen = self._stack.pop()
            img = self._load(url, w, h)
            self._arrived.emit(k, img)

    def _load(self, url, w, h):
        fn = os.path.join(IMAGE_CACHE_DIR, hashlib.md5(url.encode("utf-8", "ignore")).hexdigest())
        data = None
        try:
            if os.path.exists(fn):
                with open(fn, "rb") as f:
                    data = f.read()
            elif url.startswith(("http://", "https://")):
                r = self._session.get(url, timeout=12)
                if r.status_code == 200 and r.content:
                    data = r.content
                    try:
                        with open(fn, "wb") as f:
                            f.write(data)
                    except OSError:
                        pass
            elif os.path.isfile(url):
                with open(url, "rb") as f:
                    data = f.read()
        except Exception:  # noqa: BLE001
            data = None
        if not data:
            return None
        img = QImage()
        if not img.loadFromData(data) or img.isNull():
            return None
        return img.scaled(QSize(w, h), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)

    def _on_arrived(self, k, img):
        self._pending.discard(k)
        if img is None:
            self._failed.add(k)
            return
        self._mem[k] = QPixmap.fromImage(img)
        while len(self._mem) > self._mem_max:
            self._mem.popitem(last=False)
        if not self._notify.isActive():
            self._notify.start()


_instance = None


def loader():
    global _instance
    if _instance is None:
        _instance = ImageLoader()
    return _instance
