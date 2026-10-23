"""Aktif profilin içerik kütüphanesi: yükleme, disk önbelleği, filtreleme ve sıralama."""
import json
import os
import re
import time
import unicodedata

from .config import LIST_CACHE_DIR, atomic_write_json
from .i18n import _
from .providers import LIVE, MOVIE, SECTIONS, SERIES, Category, Item, ProviderError, create_provider
from .qt import QObject, QTimer, Signal
from .tasks import run_async

FAV_CAT = "__fav__"
RECENT_CAT = "__recent__"
ALL_CAT = "__all__"

ADULT_RE = re.compile(r"(xxx|adult|\+18|18\+|yetişkin|porn|erotik|for adults)", re.I)

# İçerik dili: ad ya da kategori başındaki "TR:", "|DE|", "[EN]", "FR -", "AR ▎" gibi etiketler
_LANG_TAG_RE = re.compile(r"^\s*[\[\(|]?\s*([A-Za-z]{2,3})\s*(?:[\]\)|:▎┃•\-–]|\s\|)")
_LANG_CODES = {"TR", "EN", "UK", "US", "GB", "DE", "FR", "IT", "ES", "NL", "AR", "PT", "PL", "RU", "AL", "GR",
               "RO", "BG", "SE", "NO", "DK", "FI", "IN", "PK", "IR", "KU", "AZ", "BE", "CH", "AT", "HU", "CZ",
               "SK", "HR", "RS", "BA", "MK", "SI", "UA", "IL", "JP", "KR", "CN", "BR", "MX", "LAT", "CA", "AU",
               "IE", "AF", "EX", "KZ", "GE", "AM", "LB", "SY", "IQ", "EG", "MA", "DZ", "TN", "SA", "AE", "QA"}
_LANG_ALIAS = {"UK": "EN", "US": "EN", "GB": "EN", "AU": "EN", "IE": "EN", "CA": "EN", "AT": "DE", "CH": "DE",
               "BE": "FR", "BR": "PT", "MX": "ES", "LAT": "ES"}
_LANG_WORDS = [(re.compile(r"\b(t[uü]rk|turkish|turkiye|türkiye)", re.I), "TR"),
               (re.compile(r"\b(english|ingilizce)\b", re.I), "EN"),
               (re.compile(r"\b(german|deutsch|almanca)\b", re.I), "DE"),
               (re.compile(r"\b(french|fran[cç]ais|frans[ıi]zca)\b", re.I), "FR"),
               (re.compile(r"\b(arabic|arap[cç]a)\b", re.I), "AR"),
               (re.compile(r"\b(spanish|espa[nñ]ol)\b", re.I), "ES"),
               (re.compile(r"\b(italian|italiano)\b", re.I), "IT")]


def lang_tag(name):
    """Addan içerik dili kodu (ör. 'TR'); bulunamazsa ''."""
    if not name:
        return ""
    m = _LANG_TAG_RE.match(name)
    if m:
        code = m.group(1).upper()
        if code in _LANG_CODES:
            return _LANG_ALIAS.get(code, code)
    for rx, code in _LANG_WORDS:
        if rx.search(name):
            return code
    return ""


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
        self.cat_by_id = {s: {} for s in SECTIONS}
        self._lang = {s: {} for s in SECTIONS}   # öğe id -> dil kodu
        self._locks = {}                          # bölüm -> (kilitli kategoriler, kilitli öğeler)
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
            self.section_loading.emit(s, _("Liste yükleniyor…"))
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
            msg = str(e) if isinstance(e, ProviderError) else _("Bağlantı hatası: {err}", err=e)
            for s in SECTIONS:
                if self.state[s] != "ready":
                    self.state[s] = "error"
                    self.errors[s] = msg
                    self.section_failed.emit(s, msg)

        for s in SECTIONS:
            if not silent or self.state[s] != "ready":
                self.state[s] = "loading"
                self.section_loading.emit(s, _("Sunucuya bağlanılıyor…"))
        run_async(work, on_done=done, on_error=fail)

    def load_section(self, section, silent=False):
        if not silent or self.state[section] != "ready":
            self.state[section] = "loading"
            self.section_loading.emit(section, _("Liste yükleniyor…"))
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
        self.cat_by_id[section] = {c.id: c for c in cats}
        self._lang[section] = {}
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

    # --- Ebeveyn kilidi ---------------------------------------------
    def pin_set(self):
        return bool(self.settings.get("parental_pin"))

    def lock_sets(self, section):
        ls = self._locks.get(section)
        if ls is None:
            ls = self._locks[section] = (self.settings.locked(self.pid, section, "cats"),
                                         self.settings.locked(self.pid, section, "items"))
        return ls

    def locks_changed(self):
        self._locks.clear()

    def set_locked(self, section, what, ids):
        self.settings.set_locked(self.pid, section, what, ids)
        self.locks_changed()

    def toggle_item_lock(self, section, item_id):
        cats, items = self.lock_sets(section)
        items = set(items)
        locked = item_id not in items
        (items.add if locked else items.discard)(item_id)
        self.set_locked(section, "items", items)
        return locked

    def is_locked(self, section, cat):
        """Kategori PIN korumalı mı (yetişkin kilidi ya da elle kilitlenmiş)."""
        if not self.pin_set():
            return False
        if cat.id in self.lock_sets(section)[0]:
            return True
        return bool(self.settings.get("lock_adult") and ADULT_RE.search(cat.name or ""))

    def item_locked(self, section, item):
        """Öğe kendisi ya da kategorisi kilitli mi."""
        if item is None or not self.pin_set():
            return False
        cats, items = self.lock_sets(section)
        if item.id in items or item.category_id in cats:
            return True
        cat = self.cat_by_id[section].get(item.category_id)
        return bool(cat and self.settings.get("lock_adult") and ADULT_RE.search(cat.name or ""))

    # --- İçerik dili --------------------------------------------------
    def lang_of(self, section, item):
        cache = self._lang[section]
        code = cache.get(item.id)
        if code is None:
            code = lang_tag(item.name)
            if not code:
                cat = self.cat_by_id[section].get(item.category_id)
                code = lang_tag(cat.name) if cat else ""
            cache[item.id] = code
        return code

    def languages(self, section, items=None):
        """[(kod, adet)] — en çok içeriği olan dil önce; tek dil varsa filtre anlamsızdır."""
        counts = {}
        for it in (self.items[section] if items is None else items):
            c = self.lang_of(section, it)
            if c:
                counts[c] = counts.get(c, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    def filter_lang(self, section, items, lang):
        return [i for i in items if self.lang_of(section, i) == lang] if lang else items

    def filtered(self, section, category_id, query="", sort="default", userdata=None, lang=""):
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
        if lang and category_id not in (FAV_CAT, RECENT_CAT):
            src = self.filter_lang(section, src, lang)
        if query:
            q = fold(query)
            src = [i for i in src if q in folded(i)]
        return sort_items(src, sort)

    def search(self, section, query, limit=60):
        """Genel arama: bölümdeki (sayfalı bölümlerde yüklenmiş) tüm öğeler, gizli/yetişkin kategoriler hariç."""
        q = fold(query)
        if not q:
            return []
        src = self.items[section] or list(self.by_id[section].values())
        hidden = self.settings.hidden(self.pid, section)
        out = []
        for i in src:
            if i.category_id in hidden or q not in folded(i):
                continue
            out.append(i)
        # Ada göre: başta eşleşenler önce
        out.sort(key=lambda i: (not folded(i).startswith(q), len(i.name)))
        return out[:limit]

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
