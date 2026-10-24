"""Stalker / Ministra (MAG) portal sağlayıcısı."""
import hashlib
import random
import re
import threading
import time
from urllib.parse import urlparse

from ..i18n import _
from .base import (EPISODE, LIVE, MOVIE, SERIES, Category, Item, Provider, ProviderError,
                   normalize_url, to_float, to_int, year_from)

MAG_UA = ("Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) "
          "MAG200 stbapp ver: 2 rev: 250 Safari/533.3")

_TYPES = {LIVE: "itv", MOVIE: "vod", SERIES: "series"}


def random_mac():
    return "00:1A:79:" + ":".join(f"{random.randint(0, 255):02X}" for _ in range(3))


def _strip_cmd(cmd):
    cmd = (cmd or "").strip()
    for p in ("ffmpeg ", "ffrt ", "ffrt2 ", "ffrt3 ", "auto "):
        if cmd.startswith(p):
            return cmd[len(p):].strip()
    return cmd


def _ts(s):
    try:
        return int(time.mktime(time.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")))
    except (ValueError, OverflowError):
        return 0


class StalkerProvider(Provider):
    kind = "stalker"
    paged = {LIVE: False, MOVIE: True, SERIES: True}

    def __init__(self, profile, session):
        super().__init__(profile, session)
        self.portal_in = normalize_url(profile["url"]).rstrip("/")
        self.mac = (profile.get("mac") or "").upper().strip()
        u = urlparse(self.portal_in)
        self.root = f"{u.scheme}://{u.netloc}"
        self.endpoint = None
        self.token = ""
        self._lock = threading.Lock()
        sn = hashlib.md5(self.mac.encode()).hexdigest().upper()
        self.sn = sn[:13]
        self.device_id = hashlib.sha256(self.mac.encode()).hexdigest().upper()
        self.series_cats = None

    # --- HTTP ----------------------------------------------------------
    def _headers(self):
        h = {
            "User-Agent": MAG_UA,
            "X-User-Agent": "Model: MAG250; Link: WiFi",
            "Referer": (self.endpoint or self.root).rsplit("/", 1)[0] + "/c/",
            "Cookie": f"mac={self.mac}; stb_lang=en; timezone=Europe/Istanbul",
            "Accept": "*/*",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def http_headers(self):
        return {"User-Agent": MAG_UA, "Cookie": f"mac={self.mac}; stb_lang=en; timezone=Europe/Istanbul"}

    def _candidates(self):
        p = self.portal_in
        path = urlparse(p).path
        c = []
        if path.endswith(".php"):
            c.append(p)
        if "stalker_portal" in path:
            c.append(self.root + "/stalker_portal/server/load.php")
        c += [self.root + "/portal.php", self.root + "/server/load.php",
              self.root + "/stalker_portal/server/load.php", self.root + "/c/portal.php"]
        seen, out = set(), []
        for x in c:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def _req(self, params, timeout=20, retry=True):
        params = dict(params)
        params["JsHttpRequest"] = "1-xml"
        try:
            r = self.session.get(self.endpoint, params=params, headers=self._headers(), timeout=timeout)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(_("Portala bağlanılamadı: {err}", err=e)) from e
        text = r.text.strip()
        if r.status_code >= 400 or not text:
            if retry and r.status_code in (401, 403, 200):
                self._handshake()
                return self._req(params, timeout, retry=False)
            raise ProviderError(_("Portal hatası: HTTP {code}", code=r.status_code))
        try:
            js = r.json().get("js")
        except (ValueError, AttributeError):
            if retry:
                self._handshake()
                return self._req(params, timeout, retry=False)
            raise ProviderError(_("Portaldan geçersiz yanıt."))
        if js is None and retry and "Authorization failed" in text:
            self._handshake()
            return self._req(params, timeout, retry=False)
        return js

    def _handshake(self):
        with self._lock:
            self.token = ""
            js = None
            for _attempt in range(2):
                try:
                    r = self.session.get(self.endpoint, params={"type": "stb", "action": "handshake",
                                                                "token": "", "JsHttpRequest": "1-xml"},
                                         headers=self._headers(), timeout=15)
                    js = r.json().get("js")
                except Exception:  # noqa: BLE001
                    js = None
                if js and js.get("token"):
                    break
            if not js or not js.get("token"):
                raise ProviderError(_("Portal el sıkışması başarısız (MAC adresi yetkili mi?)."))
            self.token = js["token"]
            params = {
                "type": "stb", "action": "get_profile", "hd": "1", "ver": "ImageDescription: 0.2.18-r23-250; "
                "ImageDate: Thu Sep 13 11:31:16 EEST 2018; PORTAL version: 5.6.2; API Version: JS API version: 343; "
                "STB API version: 146; Player Engine version: 0x58c", "num_banks": "2", "sn": self.sn,
                "stb_type": "MAG250", "client_type": "STB", "image_version": "218", "video_out": "hdmi",
                "device_id": self.device_id, "device_id2": self.device_id, "signature": "",
                "auth_second_step": "1", "hw_version": "1.7-BD-00", "not_valid_token": "0",
                "timestamp": str(int(time.time())), "api_signature": "262", "prehash": "", "JsHttpRequest": "1-xml",
            }
            try:
                r = self.session.get(self.endpoint, params=params, headers=self._headers(), timeout=15)
                self.profile_js = (r.json() or {}).get("js") or {}
            except Exception:  # noqa: BLE001
                self.profile_js = {}

    def authenticate(self):
        if not re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", self.mac):
            raise ProviderError(_("MAC adresi geçersiz. Örnek: 00:1A:79:12:34:56"))
        last = None
        for ep in self._candidates():
            self.endpoint = ep
            try:
                self._handshake()
                break
            except ProviderError as e:
                last = e
        else:
            raise last or ProviderError(_("Portal bulunamadı."))
        info = {"status": "Active", "expires": "-"}
        try:
            js = self._req({"type": "account_info", "action": "get_main_info"}, retry=False)
            if isinstance(js, dict):
                info["expires"] = js.get("end_date") or js.get("phone") or "-"
        except ProviderError:
            pass
        pj = getattr(self, "profile_js", {}) or {}
        if pj.get("status") not in (None, 0, "0"):
            if pj.get("block_msg"):
                raise ProviderError(_("Portal mesajı: {msg}", msg=pj.get("block_msg")))
        return info

    def _ensure_auth(self):
        if not self.endpoint:
            self.authenticate()

    # --- Listeler ------------------------------------------------------
    def categories(self, section):
        self._ensure_auth()
        action = "get_genres" if section == LIVE else "get_categories"
        js = self._req({"type": _TYPES[section], "action": action})
        out = []
        for c in js or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id", ""))
            if cid == "*":
                continue
            out.append(Category(cid, c.get("title") or c.get("name") or "?"))
        return out

    def _logo(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.root + url
        return f"{self.root}/stalker_portal/misc/logos/320/{url}"

    def items(self, section, category_id=None, page=1):
        self._ensure_auth()
        if section == LIVE:
            js = self._req({"type": "itv", "action": "get_all_channels"}, timeout=90)
            data = js.get("data", []) if isinstance(js, dict) else []
            out = []
            for d in data:
                if category_id and str(d.get("tv_genre_id")) != str(category_id):
                    continue
                out.append(Item(LIVE, d.get("id"), d.get("name"), self._logo(d.get("logo")),
                                d.get("tv_genre_id", ""), to_int(d.get("number")), "", "", 0, 0.0, "",
                                d.get("xmltv_id") or "", to_int(d.get("tv_archive")),
                                {"cmd": d.get("cmd", "")}))
            return out, 1
        params = {"type": _TYPES[section], "action": "get_ordered_list", "p": page,
                  "sortby": "added", "category": category_id or "*", "genre": category_id or "*"}
        js = self._req(params, timeout=30)
        if not isinstance(js, dict):
            return [], 1
        total = to_int(js.get("total_items"))
        per = to_int(js.get("max_page_items"), 14) or 14
        pages = max(1, (total + per - 1) // per)
        out = []
        for d in js.get("data", []) or []:
            name = d.get("name") or d.get("o_name") or "?"
            is_series = section == SERIES or str(d.get("is_series", "0")) == "1"
            kind = SERIES if is_series else MOVIE
            extra = {"cmd": d.get("cmd", ""), "plot": d.get("description", ""),
                     "genre": d.get("genres_str", ""), "cast": d.get("actors", ""),
                     "director": d.get("director", ""), "duration": d.get("time", "")}
            out.append(Item(kind, d.get("id"), name, self._logo(d.get("screenshot_uri") or d.get("logo")),
                            category_id or d.get("category_id", ""), 0, "", "mp4", _ts(d.get("added")),
                            to_float(d.get("rating_imdb") or d.get("rating_kinopoisk")),
                            d.get("year") or year_from(name), extra=extra))
        return out, pages

    def series_info(self, item):
        self._ensure_auth()
        stype = "series" if self.paged.get(SERIES) else "vod"
        seasons = {}
        js = self._req({"type": stype, "action": "get_ordered_list", "movie_id": item.id,
                        "season_id": "0", "episode_id": "0", "p": 1}, timeout=30)
        data = js.get("data", []) if isinstance(js, dict) else []
        if not data and stype == "series":
            js = self._req({"type": "vod", "action": "get_ordered_list", "movie_id": item.id,
                            "season_id": "0", "episode_id": "0", "p": 1}, timeout=30)
            data = js.get("data", []) if isinstance(js, dict) else []
        for idx, s in enumerate(data, 1):
            snum = to_int(re.sub(r"\D", "", str(s.get("season_number") or s.get("name") or "")), idx) or idx
            eps = s.get("series") or []
            out = []
            for e in eps:
                en = to_int(e)
                out.append(Item(EPISODE, f"{s.get('id')}:{en}", _("Bölüm {n}", n=en), item.logo, item.category_id,
                                en, "", "mp4", extra={"cmd": s.get("cmd", ""), "series_num": en,
                                                      "series_id": item.id, "series_name": item.name,
                                                      "season": snum, "episode": en}))
            if out:
                seasons[snum] = out
        return {"info": {"plot": item.extra.get("plot", ""), "cast": item.extra.get("cast", ""),
                         "genre": item.extra.get("genre", ""), "cover": item.logo},
                "seasons": dict(sorted(seasons.items()))}

    def vod_info(self, item):
        return {k: item.extra.get(k, "") for k in ("plot", "genre", "cast", "director", "duration")}

    def stream_url(self, item):
        self._ensure_auth()
        cmd = item.extra.get("cmd", "")
        if item.kind == LIVE:
            direct = _strip_cmd(cmd)
            js = self._req({"type": "itv", "action": "create_link", "cmd": cmd, "series": "",
                            "forced_storage": "undefined", "disable_ad": "0", "download": "0"})
            url = _strip_cmd(js.get("cmd", "")) if isinstance(js, dict) else ""
            return url or direct
        series = str(item.extra.get("series_num", "")) if item.kind == EPISODE else ""
        js = self._req({"type": "vod", "action": "create_link", "cmd": cmd, "series": series,
                        "forced_storage": "undefined", "disable_ad": "0", "download": "0"})
        url = _strip_cmd(js.get("cmd", "")) if isinstance(js, dict) else ""
        if not url:
            raise ProviderError(_("Yayın bağlantısı alınamadı."))
        return url

    def short_epg(self, item):
        try:
            js = self._req({"type": "itv", "action": "get_short_epg", "ch_id": item.id, "size": "4"}, timeout=10)
        except ProviderError:
            return []
        out = []
        for p in js or []:
            if not isinstance(p, dict):
                continue
            start = to_int(p.get("start_timestamp"))
            end = to_int(p.get("stop_timestamp"))
            if start:
                out.append({"title": p.get("name", ""), "desc": p.get("descr", ""),
                            "start": start, "end": end, "archive": False})
        return out
