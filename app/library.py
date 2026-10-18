"""Aktif profilin içerik kütüphanesi: yükleme, disk önbelleği, filtreleme ve sıralama."""
import json
import os
import re
import time
import unicodedata

from .config import LIST_CACHE_DIR, atomic_write_json
from .providers import LIVE, MOVIE, SECTIONS, SERIES, Category, Item, ProviderError, create_provider
from .qt import QObject, QTimer, Signal
from .tasks import run_async

FAV_CAT = "__fav__"
RECENT_CAT = "__recent__"
ALL_CAT = "__all__"

ADULT_RE = re.compile(r"(xxx|adult|\+18|18\+|yetişkin|porn|erotik|for adults)", re.I)

_TR_MAP = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                         "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def fold(s):
    """Arama için Türkçe karakter ve büyük/küçük harf duyarsız metin."""
    s = s.translate(_TR_MAP).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def folded(item):
    f = item._fold
    if f is None:
        f = item._fold = fold(item.name)
    return f


def item_from_brief(kind, b):
    return Item(kind, b.get("id"), b.get("name"), b.get("logo"), b.get("category_id"),
                url=b.get("url", ""), ext=b.get("ext", ""), extra=dict(b.get("extra") or {}))


def sort_items(items, mode):
    if mode == "az":
        return sorted(items, key=lambda i: i.sort_key)
    if mode == "za":
        return sorted(items, key=lambda i: i.sort_key, reverse=True)
    if mode == "new":
        return sorted(items, key=lambda i: i.added, reverse=True)
    if mode == "rating":
        return sorted(items, key=lambda i: i.rating, reverse=True)
    if mode == "year":
        return sorted(items, key=lambda i: i.year or "0", reverse=True)
    if mode == "num":
        return sorted(items, key=lambda i: (i.num or 10 ** 9))
    return list(items)


class Library(QObject):
    section_loading = Signal(str, str)     # bölüm, mesaj
    section_ready = Signal(str)            # bölüm
    section_failed = Signal(str, str)      # bölüm, hata
    page_ready = Signal(str, str, int, object, int, int)  # bölüm, kategori, sayfa, öğeler, toplam_sayfa, istek_no
    account_ready = Signal(object)

    def __init__(self, profile, settings):
        super().__init__()
        self.profile = profile
        self.settings = settings
        self.provider = create_provider(profile, settings.get("user_agent"))
        if profile.get("type") == "xtream":
            self.provider.live_ext = settings.get("live_format", "ts")
        self.cats = {s: [] for s in SECTIONS}
        self.items = {s: [] for s in SECTIONS}
        self.by_id = {s: {} for s in SECTIONS}
        self.state = {s: "idle" for s in SECTIONS}  # idle | loading | ready | error
        self.errors = {}
        self.account = None
        self._page_cache = {}  # (bölüm, kategori) -> {"items": [], "pages": n, "loaded": k}
        self._req_no = 0
        self.cache_path = os.path.join(LIST_CACHE_DIR, f"{profile['id']}.json")
        self._cache_timer = QTimer(self)
        self._cache_timer.setSingleShot(True)
        self._cache_timer.setInterval(1500)
        self._cache_timer.timeout.connect(self._do_write_cache)

    @property
    def pid(self):
        return self.profile["id"]

    def is_paged(self, section):
        return self.provider.paged.get(section, False)

    # --- Yükleme -------------------------------------------------------
    def start(self, force=False):
        """Önbelleği arka planda okur (arayüz donmaz), eskiyse sunucudan yeniler."""
        for s in SECTIONS:
            self.state[s] = "loading"
            self.section_loading.emit(s, "Liste yükleniyor…")
        if force:
            self._after_cache(None)
            return

        def read():
            cache = self._read_cache()
            if not cache:
                return None
            out = {"ts": cache.get("ts", 0), "account": cache.get("account"), "sections": {}}
            for s, sec in cache.get("sections", {}).items():
                items = [Item.from_list(i) for i in sec["items"]]
                for i in items:
                    folded(i)
                out["sections"][s] = ([Category.from_list(c) for c in sec["cats"]], items)
            return out

        run_async(read, on_done=self._after_cache, on_error=lambda e: self._after_cache(None))

    def _after_cache(self, cache):
        if cache:
            for s, (cats, items) in cache["sections"].items():
                if s in self.state:
                    self._apply(s, cats, items)
            self.account = cache.get("account")
            if self.account:
                self.account_ready.emit(self.account)
        max_age = self.settings.get("cache_hours", 12) * 3600
        stale = not cache or (time.time() - cache.get("ts", 0) > max_age)
        if stale:
            self.refresh(silent=bool(cache))
        else:
            # Önbellekte olmayan bölümler (ör. sayfalı Stalker kategorileri) yine yüklenir
            for s in SECTIONS:
                if self.state[s] != "ready":
                    self.load_section(s)
            run_async(self._auth_only, on_done=self._on_account, on_error=lambda e: None)

    def _auth_only(self):
        return self.provider.authenticate()

    def _on_account(self, acc):
        self.account = acc
        self.account_ready.emit(acc)

    def refresh(self, silent=False):
        self._page_cache.clear()

        def work():
            acc = self.provider.authenticate()
            return acc

        def done(acc):
            self._on_account(acc)
            for s in SECTIONS:
                self.load_section(s, silent=silent)

        def fail(e):
            msg = str(e) if isinstance(e, ProviderError) else f"Bağlantı hatası: {e}"
            for s in SECTIONS:
                if self.state[s] != "ready":
                    self.state[s] = "error"
                    self.errors[s] = msg
                    self.section_failed.emit(s, msg)

        for s in SECTIONS:
            if not silent or self.state[s] != "ready":
                self.state[s] = "loading"
                self.section_loading.emit(s, "Sunucuya bağlanılıyor…")
        run_async(work, on_done=done, on_error=fail)

    def load_section(self, section, silent=False):
        if not silent or self.state[section] != "ready":
            self.state[section] = "loading"
            self.section_loading.emit(section, "Liste yükleniyor…")
        paged = self.is_paged(section)

        def work():
            cats = self.provider.categories(section)
            items = [] if paged else self.provider.items(section)[0]
            for i in items:
                folded(i)
            return cats, items

        def done(res):
            cats, items = res
            self._apply(section, cats, items)
            self._write_cache()

        def fail(e):
            if self.state[section] == "ready":
                return  # önbellekteki veri kullanılmaya devam eder
            self.state[section] = "error"
            self.errors[section] = str(e)
            self.section_failed.emit(section, str(e))

        run_async(work, on_done=done, on_error=fail)

    def _apply(self, section, cats, items):
        self.cats[section] = cats
        self.items[section] = items
        self.by_id[section] = {i.id: i for i in items}
        self.state[section] = "ready"
        self.section_ready.emit(section)

    # --- Önbellek ------------------------------------------------------
    def _read_cache(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _write_cache(self):
        self._cache_timer.start()

    def _do_write_cache(self):
        snap = {"ts": time.time(), "account": self.account, "sections": {}}
        for s in SECTIONS:
            if self.state[s] == "ready" and (self.items[s] or self.cats[s]) and not self.is_paged(s):
                snap["sections"][s] = {"cats": [c.to_list() for c in self.cats[s]],
                                       "items": [i.to_list() for i in self.items[s]]}
        run_async(atomic_write_json, self.cache_path, snap)

    def clear_cache(self):
        try:
            os.remove(self.cache_path)
        except OSError:
            pass

    # --- Sorgular ------------------------------------------------------
    def visible_categories(self, section):
        hidden = self.settings.hidden(self.pid, section)
        return [c for c in self.cats[section] if c.id not in hidden]

    def is_locked(self, section, cat):
        return bool(self.settings.get("lock_adult") and self.settings.get("parental_pin")
                    and ADULT_RE.search(cat.name or ""))

    def filtered(self, section, category_id, query="", sort="default", userdata=None):
        """Bellekteki tam listeden filtreleme (sayfalı olmayan bölümler)."""
        src = self.items[section]
        if category_id == FAV_CAT and userdata:
            by = self.by_id[section]
            meta = userdata.fav_meta.get(section, {})
            src = []
            for i in userdata.favorite_ids(section):
                it = by.get(i) or (item_from_brief(section, meta[i]) if i in meta else None)
                if it:
                    src.append(it)
        elif category_id == RECENT_CAT and userdata:
            by = self.by_id[section]
            src = [by.get(h["id"]) or item_from_brief(section, h) for h in userdata.history_entries(section)]
            sort = "default"
        elif category_id and category_id != ALL_CAT:
            src = [i for i in src if i.category_id == category_id]
        else:
            hidden = self.settings.hidden(self.pid, section)
            locked = set()
            if self.settings.get("lock_adult") and self.settings.get("parental_pin"):
                locked = {c.id for c in self.cats[section] if ADULT_RE.search(c.name or "")}
            excl = hidden | locked
            if excl:
                src = [i for i in src if i.category_id not in excl]
        if query:
            q = fold(query)
            src = [i for i in src if q in folded(i)]
        return sort_items(src, sort)

    def request_page(self, section, category_id, page=1):
        """Sayfalı bölümler için kategori sayfası ister; sonuç page_ready ile gelir."""
        self._req_no += 1
        req = self._req_no
        key = (section, category_id)

        def work():
            return self.provider.items(section, None if category_id == ALL_CAT else category_id, page)

        def done(res):
            items, pages = res
            for i in items:
                self.by_id[section][i.id] = i
            c = self._page_cache.setdefault(key, {"items": [], "pages": pages, "loaded": 0})
            if page > c["loaded"]:
                c["items"].extend(items)
                c["loaded"] = page
                c["pages"] = pages
            self.page_ready.emit(section, category_id, page, items, pages, req)

        def fail(e):
            self.page_ready.emit(section, category_id, page, [], 0, req)

        run_async(work, on_done=done, on_error=fail)
        return req

    def cached_pages(self, section, category_id):
        return self._page_cache.get((section, category_id))

    def find(self, section, item_id):
        return self.by_id[section].get(item_id)


__all__ = ["Library", "FAV_CAT", "RECENT_CAT", "ALL_CAT", "fold", "sort_items", "LIVE", "MOVIE", "SERIES"]
