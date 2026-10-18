"""Uygulama dizinleri, ayarlar ve profil başına kullanıcı verileri (favori, geçmiş, izleme konumu)."""
import json
import os
import sys
import threading
import time
import uuid

APP_NAME = "ONR IPTV"
APP_ID = "ONRIPTV"          # klasör ve dosya adlarında kullanılan boşluksuz ad
APP_VERSION = "1.0.0"
APP_AUTHOR = "Onur BiLKE"
_OLD_ID = "TurkuazTV"       # önceki sürümün klasör adı (otomatik taşınır)

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IS_ARM = IS_LINUX and os.uname().machine.lower().startswith(("arm", "aarch"))
# Pi 4: H.264 donanım çözücüsü v4l2m2m, HEVC drm. Önce kopyasız (dmabuf) modlar, sonra kopyalı yedekler.
# "auto-copy" bunları hiç denemiyor; yazılımsal çözme CPU'yu ~%55-80 kullanıyor.
PI_HWDEC = "v4l2m2m,drm,v4l2m2m-copy,drm-copy,auto-copy"


def _migrate(old, new):
    """Eski 'TurkuazTV' klasörü varsa profiller kaybolmasın diye yeni ada taşır."""
    if not os.path.exists(new) and os.path.isdir(old):
        try:
            os.rename(old, new)
        except OSError:
            return old
    return new


def _data_dir():
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return _migrate(os.path.join(base, _OLD_ID), os.path.join(base, APP_ID))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return _migrate(os.path.join(base, _OLD_ID.lower()), os.path.join(base, APP_ID.lower()))


def _cache_dir():
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(_migrate(os.path.join(base, _OLD_ID), os.path.join(base, APP_ID)), "cache")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return _migrate(os.path.join(base, _OLD_ID.lower()), os.path.join(base, APP_ID.lower()))


def _default_download_dir():
    for name in ("Videos", "Videolar", "Downloads", "İndirilenler"):
        p = os.path.join(os.path.expanduser("~"), name)
        if os.path.isdir(p):
            return os.path.join(p, APP_ID)
    return os.path.join(os.path.expanduser("~"), APP_ID)


_HOME = os.environ.get("ONRIPTV_HOME") or os.environ.get("TURKUAZTV_HOME")  # taşınabilir kullanım / test için
DATA_DIR = os.path.join(_HOME, "data") if _HOME else _data_dir()
CACHE_DIR = os.path.join(_HOME, "cache") if _HOME else _cache_dir()
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, "images")
LIST_CACHE_DIR = os.path.join(CACHE_DIR, "lists")
for _d in (DATA_DIR, CACHE_DIR, IMAGE_CACHE_DIR, LIST_CACHE_DIR):
    os.makedirs(_d, exist_ok=True)


_write_lock = threading.Lock()


def atomic_write_json(path, data):
    with _write_lock:
        _atomic_write_json(path, data)


def _atomic_write_json(path, data):
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


DEFAULTS = {
    "profiles": [],
    "active_profile": None,
    "hwdec": PI_HWDEC if IS_ARM else "auto-safe",
    "buffer_seconds": 8,
    "live_format": "ts",  # Xtream canlı yayın: ts | m3u8
    # HLS kalite sınırı (mpv hls-bitrate, bit/s). Pi'nin 1024x600 ekranında 1080p fark yaratmaz ama
    # zayıf Wi-Fi'de takılmaya yol açar; bu yüzden Pi'de 2 Mbit/s sınırı varsayılan.
    "hls_bitrate": "2000000" if IS_ARM else "max",
    "auto_reconnect": True,
    "volume": 100,
    "user_agent": "VLC/3.0.20 LibVLC/3.0.20",
    "download_dir": _default_download_dir(),
    "max_downloads": 2,
    "touch_scroll": True,
    "osk_enabled": IS_LINUX,  # ekran klavyesi (dokunmatik Pi ekranı için)
    "start_fullscreen": IS_ARM,
    "animations": True,
    "show_epg_in_list": True,
    "cache_hours": 12,
    "parental_pin": "",
    "lock_adult": False,
    "hidden_categories": {},  # profil_id -> {bölüm: [kategori_id]}
    "live_sort": "default",
    "vod_sort": "default",
    "series_sort": "default",
    "sidebar_compact": False,
}


class Settings:
    def __init__(self):
        self.path = os.path.join(DATA_DIR, "settings.json")
        data = read_json(self.path, {})
        self.data = dict(DEFAULTS)
        self.data.update(data)
        if IS_ARM and self.data.get("hwdec") in ("auto-copy", "auto-copy-safe", "v4l2m2m-copy,drm-copy,auto-copy"):
            self.data["hwdec"] = PI_HWDEC  # eski varsayılanı Pi donanım çözücüsüne geçir
        self._lock = threading.Lock()

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        with self._lock:
            atomic_write_json(self.path, self.data)

    # --- Profiller -----------------------------------------------------
    @property
    def profiles(self):
        return self.data["profiles"]

    def active_profile(self):
        pid = self.data.get("active_profile")
        for p in self.profiles:
            if p["id"] == pid:
                return p
        return self.profiles[0] if self.profiles else None

    def upsert_profile(self, profile):
        if not profile.get("id"):
            profile["id"] = uuid.uuid4().hex[:12]
        for i, p in enumerate(self.profiles):
            if p["id"] == profile["id"]:
                self.profiles[i] = profile
                break
        else:
            self.profiles.append(profile)
        self.save()
        return profile

    def remove_profile(self, pid):
        self.data["profiles"] = [p for p in self.profiles if p["id"] != pid]
        if self.data.get("active_profile") == pid:
            self.data["active_profile"] = self.profiles[0]["id"] if self.profiles else None
        self.save()

    def set_active(self, pid):
        self.data["active_profile"] = pid
        self.save()

    # --- Gizli kategoriler --------------------------------------------
    def hidden(self, pid, section):
        return set(self.data.setdefault("hidden_categories", {}).get(pid, {}).get(section, []))

    def set_hidden(self, pid, section, ids):
        hc = self.data.setdefault("hidden_categories", {})
        hc.setdefault(pid, {})[section] = sorted(ids)
        self.save()


class UserData:
    """Profil başına favoriler, son izlenenler ve kaldığı yer bilgisi."""

    MAX_HISTORY = 60

    def __init__(self, profile_id):
        self.path = os.path.join(DATA_DIR, f"user_{profile_id}.json")
        d = read_json(self.path, {})
        self.favorites = {k: list(v) for k, v in d.get("favorites", {}).items()}
        self.history = d.get("history", [])
        self.progress = d.get("progress", {})
        self.fav_meta = d.get("fav_meta", {})
        self._fav_sets = {k: set(v) for k, v in self.favorites.items()}
        self._dirty = False
        self._last_save = 0

    # Favoriler
    def is_favorite(self, kind, item_id):
        return item_id in self._fav_sets.get(kind, ())

    def toggle_favorite(self, kind, item_id, brief=None):
        lst = self.favorites.setdefault(kind, [])
        s = self._fav_sets.setdefault(kind, set())
        if item_id in s:
            s.discard(item_id)
            lst.remove(item_id)
            self.fav_meta.get(kind, {}).pop(item_id, None)
            result = False
        else:
            s.add(item_id)
            lst.append(item_id)
            if brief:
                self.fav_meta.setdefault(kind, {})[item_id] = brief
            result = True
        self.save()
        return result

    def favorite_ids(self, kind):
        return list(self.favorites.get(kind, []))

    # Geçmiş
    def add_history(self, kind, item_dict):
        iid = item_dict.get("id")
        self.history = [h for h in self.history if not (h.get("kind") == kind and h.get("id") == iid)]
        entry = dict(item_dict)
        entry["kind"] = kind
        entry["ts"] = int(time.time())
        self.history.insert(0, entry)
        del self.history[self.MAX_HISTORY:]
        self.save()

    def history_ids(self, kind):
        return [h["id"] for h in self.history if h.get("kind") == kind]

    def history_entries(self, kind=None):
        return [h for h in self.history if kind is None or h.get("kind") == kind]

    # İzleme konumu
    def get_progress(self, key):
        return self.progress.get(key)

    def set_progress(self, key, pos, dur, flush=False):
        if dur and pos / dur > 0.95:
            self.progress.pop(key, None)
        else:
            self.progress[key] = {"pos": int(pos), "dur": int(dur or 0), "ts": int(time.time())}
        self._dirty = True
        now = time.time()
        if flush or now - self._last_save > 15:
            self.save()

    def save(self):
        self._last_save = time.time()
        self._dirty = False
        atomic_write_json(self.path, {
            "favorites": self.favorites,
            "fav_meta": self.fav_meta,
            "history": self.history,
            "progress": self.progress,
        })
