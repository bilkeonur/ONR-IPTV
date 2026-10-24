"""Film/bölüm indirme yöneticisi: duraklat/devam (HTTP Range), eşzamanlı sınır, disk alanı kontrolü."""
import os
import re
import shutil
import threading
import time
import uuid

import requests

from .config import DATA_DIR, atomic_write_json, read_json
from .i18n import N_, _
from .qt import QObject, Signal

QUEUED, RUNNING, PAUSED, DONE, FAILED, RESOLVING = "queued", "running", "paused", "done", "failed", "resolving"
# Çeviri gösterim anında yapılır: _(STATUS_TEXT[durum])
STATUS_TEXT = {QUEUED: N_("Sırada"), RUNNING: N_("İndiriliyor"), PAUSED: N_("Duraklatıldı"), DONE: N_("Tamamlandı"),
               FAILED: N_("Hata"), RESOLVING: N_("Hazırlanıyor")}


def usable_dir(settings, sub=""):
    """İndirme klasörünü oluşturur; yazılamıyorsa kullanıcı klasöründe bir yedek kullanır."""
    candidates = [settings.get("download_dir"),
                  os.path.join(os.path.expanduser("~"), "Downloads", "ONRIPTV"),
                  os.path.join(DATA_DIR, "downloads")]
    for base in candidates:
        if not base:
            continue
        d = os.path.join(base, sub) if sub else base
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".yazma_testi")
            with open(probe, "w") as f:
                f.write("1")
            os.remove(probe)
            return d
        except OSError:
            continue
    raise RuntimeError(_("İndirme klasörü oluşturulamadı. Menü → İndirme bölümünden başka bir klasör seçin."))


def _is_network_error(e):
    if isinstance(e, requests.exceptions.RequestException):
        return True
    msg = str(e).lower()
    return any(k in msg for k in ("connection broken", "connection reset", "connection aborted", "timed out",
                                  "incompleteread", _("Bağlantı kesildi, devam ettirmek için tekrar başlatın.").lower()))


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:150] or "video"


class DownloadManager(QObject):
    changed = Signal(str)   # görev id
    listChanged = Signal()
    _progress = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.path = os.path.join(DATA_DIR, "downloads.json")
        self.tasks = read_json(self.path, [])
        for t in self.tasks:
            if t["status"] in (RUNNING, RESOLVING):
                t["status"] = PAUSED
            t.setdefault("speed", 0)
        self.tasks = [t for t in self.tasks if not self._missing(t)]
        self._threads = {}
        self._stop = {}
        self._lock = threading.Lock()
        self._progress.connect(self.changed.emit)
        self._last_save = 0
        self.conn_limit = 0  # sağlayıcının bildirdiği eşzamanlı bağlantı sınırı (0 = bilinmiyor)

    MAX_RETRIES = 3

    def set_connection_limit(self, n):
        """Hesap bilgisi gelince çağrılır; indirmeler bu sınırı aşmaz (aşarsa sunucu ilk bağlantıyı keser)."""
        try:
            self.conn_limit = max(0, int(str(n or 0).strip() or 0))
        except ValueError:
            self.conn_limit = 0
        self._schedule()

    def limit(self):
        n = max(1, int(self.settings.get("max_downloads", 1)))
        return min(n, self.conn_limit) if self.conn_limit > 0 else n

    # --- Genel arayüz --------------------------------------------------
    def find(self, tid):
        for t in self.tasks:
            if t["id"] == tid:
                return t
        return None

    def find_by_item(self, key):
        for t in self.tasks:
            if t.get("key") == key:
                return t
        return None

    @staticmethod
    def _missing(t):
        return t["status"] == DONE and not os.path.exists(t["path"])

    def prune_missing(self):
        """Klasörden elle silinmiş tamamlanmış indirmeleri listeden kaldırır."""
        gone = [t for t in self.tasks if self._missing(t)]
        if not gone:
            return False
        for t in gone:
            self.tasks.remove(t)
        self._save(force=True)
        self.listChanged.emit()
        return True

    def add(self, title, key, resolver, ext="mp4", poster="", meta=None, folder=""):
        """resolver: arka planda çağrılıp indirme URL'sini döndüren fonksiyon."""
        existing = self.find_by_item(key)
        if existing and existing["status"] != FAILED:
            return existing
        if existing:
            self.tasks.remove(existing)
        try:
            base = usable_dir(self.settings, safe_filename(folder) if folder else "")
        except RuntimeError:
            base = os.path.join(self.settings.get("download_dir"), safe_filename(folder) if folder else "")
        fname = safe_filename(title) + "." + (ext or "mp4")
        t = {"id": uuid.uuid4().hex[:10], "key": key, "title": title, "poster": poster,
             "path": os.path.join(base, fname), "url": "", "total": 0, "done": 0,
             "status": QUEUED, "error": "", "created": int(time.time()), "speed": 0, "meta": meta or {}}
        t["_resolver"] = resolver
        self.tasks.insert(0, t)
        self._save(force=True)
        self.listChanged.emit()
        self._schedule()
        return t

    def add_local(self, title, path, meta=None):
        """Canlı yayın kaydı gibi tamamlanmış yerel dosyaları listeye ekler."""
        size = os.path.getsize(path) if os.path.exists(path) else 0
        t = {"id": uuid.uuid4().hex[:10], "key": "local:" + path, "title": title, "poster": "",
             "path": path, "url": "", "total": size, "done": size, "status": DONE, "error": "",
             "created": int(time.time()), "speed": 0, "meta": meta or {"record": True}}
        self.tasks.insert(0, t)
        self._save(force=True)
        self.listChanged.emit()

    def pause(self, tid):
        t = self.find(tid)
        if t and t["status"] in (RUNNING, QUEUED, RESOLVING):
            ev = self._stop.get(tid)
            if ev:
                ev.set()
            t["status"] = PAUSED
            t["speed"] = 0
            self._save(force=True)
            self.changed.emit(tid)
            self._schedule()

    def resume(self, tid):
        t = self.find(tid)
        if t and t["status"] in (PAUSED, FAILED):
            t["status"] = QUEUED
            t["error"] = ""
            self._save(force=True)
            self.changed.emit(tid)
            self._schedule()

    def remove(self, tid, delete_file=True):
        t = self.find(tid)
        if not t:
            return
        ev = self._stop.get(tid)
        if ev:
            ev.set()
        self.tasks.remove(t)
        if delete_file:
            for p in (t["path"], t["path"] + ".part"):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self._save(force=True)
        self.listChanged.emit()
        self._schedule()

    def stop_all(self):
        for ev in self._stop.values():
            ev.set()
        for t in self.tasks:
            if t["status"] in (RUNNING, RESOLVING, QUEUED):
                t["status"] = PAUSED  # açılışta kendiliğinden başlamasın
        self._save(force=True)

    # --- İç işleyiş ----------------------------------------------------
    def _save(self, force=False):
        now = time.time()
        if not force and now - self._last_save < 2:
            return
        self._last_save = now
        clean = [{k: v for k, v in t.items() if not k.startswith("_")} for t in self.tasks]
        try:
            atomic_write_json(self.path, clean)
        except OSError:
            pass

    def _schedule(self):
        with self._lock:
            # Yeniden denemeyi bekleyen görevin iş parçacığı da bağlantı sayılır
            running = len(self._threads)
            limit = self.limit()
            for t in reversed(self.tasks):
                if running >= limit:
                    break
                if t["status"] == QUEUED and t["id"] not in self._threads:
                    t["status"] = RESOLVING
                    ev = threading.Event()
                    self._stop[t["id"]] = ev
                    th = threading.Thread(target=self._run, args=(t, ev), daemon=True)
                    self._threads[t["id"]] = th
                    running += 1
                    th.start()

    def _finish_thread(self, t):
        self._threads.pop(t["id"], None)
        self._stop.pop(t["id"], None)
        self._save(force=True)
        self._progress.emit(t["id"])
        # _schedule ana iş parçacığında olmalı değil; kilitle korunuyor
        self._schedule()

    def _run(self, t, stop):
        try:
            self._download(t, stop)
            t.pop("_retries", None)
            t.pop("note", None)
        except Exception as e:  # noqa: BLE001
            if not stop.is_set():
                n = t.get("_retries", 0)
                if _is_network_error(e) and n < self.MAX_RETRIES:
                    # Kopan bağlantı: biraz bekleyip kaldığı yerden (HTTP Range) yeniden dene
                    t["_retries"] = n + 1
                    t["note"] = _("Bağlantı koptu, yeniden deneniyor ({n}/{max})", n=n + 1, max=self.MAX_RETRIES)
                    t["status"] = QUEUED
                    self._progress.emit(t["id"])
                    if stop.wait(4 * (n + 1)):
                        return
                else:
                    t["status"] = FAILED
                    t["error"] = str(e)[:200]
                    t.pop("note", None)
        finally:
            t["speed"] = 0
            self._finish_thread(t)

    def _download(self, t, stop):
        url = t.get("url")
        resolver = t.get("_resolver")
        if resolver and (not url or t["meta"].get("refresh_url")):
            url = resolver()
            t["url"] = url
        if not url:
            raise RuntimeError(_("İndirme bağlantısı alınamadı."))
        if url.lower().split("?")[0].endswith((".m3u8", ".m3u")):
            raise RuntimeError(_("Bu içerik akış (HLS) formatında, doğrudan indirilemiyor."))
        try:
            os.makedirs(os.path.dirname(t["path"]), exist_ok=True)
        except OSError as e:
            raise RuntimeError(_("Klasör oluşturulamadı ({path}). Menü → İndirme bölümünden başka bir klasör seçin.",
                                 path=os.path.dirname(t["path"]))) from e
        part = t["path"] + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"User-Agent": self.settings.get("user_agent")}
        if have:
            headers["Range"] = f"bytes={have}-"
        if stop.is_set():
            return
        t["status"] = RUNNING
        self._progress.emit(t["id"])
        with requests.get(url, headers=headers, stream=True, timeout=(15, 60), allow_redirects=True) as r:
            if r.status_code == 416:  # zaten tamam
                os.replace(part, t["path"])
                t["status"] = DONE
                return
            if r.status_code not in (200, 206):
                raise RuntimeError(_("Sunucu yanıtı HTTP {code} (bağlantı sınırı dolu olabilir)", code=r.status_code))
            if r.status_code == 200 and have:
                have = 0  # sunucu devam etmeyi desteklemiyor, baştan
            length = int(r.headers.get("Content-Length") or 0)
            total = have + length if length else 0
            t["total"] = total
            free = shutil.disk_usage(os.path.dirname(t["path"])).free
            if length and length > free - 200 * 1024 * 1024:
                raise RuntimeError(_("Yetersiz disk alanı (gereken {need} GB, boş {free} GB)",
                                     need=f"{length / 1e9:.1f}", free=f"{free / 1e9:.1f}"))
            mode = "ab" if have else "wb"
            done = have
            last_t, last_b = time.time(), done
            with open(part, mode) as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if stop.is_set():
                        t["done"] = done
                        return
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last_t >= 0.7:
                        t["speed"] = (done - last_b) / (now - last_t)
                        t["done"] = done
                        last_t, last_b = now, done
                        self._progress.emit(t["id"])
                        self._save()
            t["done"] = done
        if total and done < total:
            raise RuntimeError(_("Bağlantı kesildi, devam ettirmek için tekrar başlatın."))
        if os.path.exists(t["path"]):
            os.remove(t["path"])
        os.replace(part, t["path"])
        t["total"] = done
        t["status"] = DONE
