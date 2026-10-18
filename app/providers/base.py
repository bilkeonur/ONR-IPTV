"""Ortak veri yapıları ve sağlayıcı arayüzü."""
import hashlib
import re

import requests

LIVE, MOVIE, SERIES, EPISODE = "live", "movie", "series", "episode"


class ProviderError(Exception):
    pass


class Category:
    __slots__ = ("id", "name")

    def __init__(self, id, name):
        self.id = str(id)
        self.name = name or "?"

    def to_list(self):
        return [self.id, self.name]

    @classmethod
    def from_list(cls, d):
        return cls(d[0], d[1])


class Item:
    """Kanal, film, dizi ya da bölüm."""

    __slots__ = ("kind", "id", "name", "logo", "category_id", "num", "url", "ext",
                 "added", "rating", "year", "epg_id", "archive", "extra", "_key", "_fold")
    FIELDS = ("kind", "id", "name", "logo", "category_id", "num", "url", "ext",
              "added", "rating", "year", "epg_id", "archive", "extra")

    def __init__(self, kind, id, name, logo="", category_id="", num=0, url="", ext="",
                 added=0, rating=0.0, year="", epg_id="", archive=0, extra=None):
        self.kind = kind
        self.id = str(id)
        self.name = (name or "").strip() or "?"
        self.logo = logo or ""
        self.category_id = str(category_id) if category_id is not None else ""
        self.num = num or 0
        self.url = url or ""
        self.ext = ext or ""
        self.added = added or 0
        self.rating = rating or 0.0
        self.year = str(year or "")
        self.epg_id = epg_id or ""
        self.archive = archive or 0
        self.extra = extra or {}
        self._key = None
        self._fold = None

    @property
    def sort_key(self):
        if self._key is None:
            self._key = self.name.casefold()
        return self._key

    def to_list(self):
        return [getattr(self, f) for f in self.FIELDS]

    @classmethod
    def from_list(cls, d):
        return cls(*d)

    def brief(self):
        """Geçmiş listesine kaydedilecek özet."""
        return {"id": self.id, "name": self.name, "logo": self.logo,
                "category_id": self.category_id, "ext": self.ext, "url": self.url,
                "extra": {k: v for k, v in self.extra.items() if k in ("series_id", "season", "episode", "series_name", "cmd")}}


def stable_id(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8", "ignore")).hexdigest()
    return h[:16]


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def year_from(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return m.group(0) if m else ""


def make_session(user_agent):
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept": "*/*", "Connection": "keep-alive"})
    adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=1)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def normalize_url(url):
    url = (url or "").strip()
    if url and not re.match(r"^[a-zA-Z]+://", url):
        url = "http://" + url
    return url


class Provider:
    """Tüm sağlayıcıların uyguladığı arayüz.

    paged[bolum] True ise o bölümün içerikleri kategori kategori, sayfa sayfa yüklenir
    (Stalker portalları). Aksi halde bölümün tamamı tek seferde gelir.
    """

    kind = "base"
    paged = {LIVE: False, MOVIE: False, SERIES: False}

    def __init__(self, profile, session):
        self.profile = profile
        self.session = session

    # Zorunlu
    def authenticate(self):
        """Hesap bilgisi sözlüğü döner, başarısızsa ProviderError."""
        raise NotImplementedError

    def categories(self, section):
        return []

    def items(self, section, category_id=None, page=1):
        """(liste, toplam_sayfa) döner."""
        return [], 1

    def stream_url(self, item):
        return item.url

    # İsteğe bağlı
    def series_info(self, item):
        """{'info': {...}, 'seasons': {sezon_no: [Item(EPISODE)]}}"""
        return {"info": {}, "seasons": {}}

    def vod_info(self, item):
        return {}

    def short_epg(self, item):
        """[{'title','desc','start','end'}] (epoch saniye)"""
        return []

    def epg_table(self, item):
        """Günlük program listesi; catch-up için 'archive' alanı içerebilir."""
        return self.short_epg(item)

    def catchup_url(self, item, prog):
        return None

    def http_headers(self):
        """mpv'ye geçirilecek ek HTTP başlıkları."""
        return {}
