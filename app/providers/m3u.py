"""M3U / M3U8 çalma listesi sağlayıcısı (+ XMLTV EPG)."""
import gzip
import io
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from .base import (EPISODE, LIVE, MOVIE, SERIES, Category, Item, Provider, ProviderError,
                   normalize_url, stable_id, year_from)

_ATTR_RE = re.compile(r'([\w\-]+)="([^"]*)"')
_EP_RE = re.compile(r"^(?P<name>.*?)[\s._\-|]*S(?P<s>\d{1,2})[\s._\-]*E(?P<e>\d{1,4})", re.I)
_VOD_EXT = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".webm", ".mpg", ".mpeg")


def _classify(url, group):
    lu = url.lower().split("?")[0]
    g = (group or "").lower()
    if "/series/" in lu:
        return SERIES
    if "/movie/" in lu:
        return MOVIE
    if lu.endswith(_VOD_EXT):
        if any(w in g for w in ("dizi", "series", "sezon", "season")):
            return SERIES
        return MOVIE
    return LIVE


def parse_m3u(text):
    """(öğeler, başlık_özellikleri) döner. Öğeler: (bölüm, ad, url, özellikler, grup, seçenekler)."""
    entries = []
    header = {}
    info = None
    opts = {}
    group_override = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            header = dict(_ATTR_RE.findall(line))
        elif line.startswith("#EXTINF"):
            body = line[8:]
            # Ad, tırnak dışındaki son virgülden sonra gelir
            in_q = False
            split_at = -1
            for i, ch in enumerate(body):
                if ch == '"':
                    in_q = not in_q
                elif ch == "," and not in_q:
                    split_at = i
                    break
            attrs_part = body[:split_at] if split_at >= 0 else body
            name = body[split_at + 1:].strip() if split_at >= 0 else ""
            attrs = dict(_ATTR_RE.findall(attrs_part))
            info = (name or attrs.get("tvg-name", ""), attrs)
            group_override = None
        elif line.startswith("#EXTGRP:"):
            group_override = line[8:].strip()
        elif line.startswith("#EXTVLCOPT:"):
            kv = line[11:].split("=", 1)
            if len(kv) == 2:
                opts[kv[0].strip().lower()] = kv[1].strip()
        elif line.startswith("#KODIPROP:"):
            continue
        elif line.startswith("#"):
            continue
        else:
            if info is None:
                info = (os.path.basename(line.split("?")[0]) or line, {})
            name, attrs = info
            group = attrs.get("group-title") or group_override or "Diğer"
            entries.append((_classify(line, group), name, line, attrs, group, opts))
            info, opts, group_override = None, {}, None
    return entries, header


class M3UProvider(Provider):
    kind = "m3u"

    def __init__(self, profile, session):
        super().__init__(profile, session)
        self.source = (profile.get("url") or "").strip()
        self.epg_url = (profile.get("epg_url") or "").strip()
        self._data = None
        self._series_eps = {}
        self._epg = None
        self._epg_lock = threading.Lock()
        self._headers = {}

    def _load_text(self):
        src = self.source
        if os.path.isfile(src):
            with open(src, "rb") as f:
                raw = f.read()
        else:
            try:
                r = self.session.get(normalize_url(src), timeout=90)
            except Exception as e:  # noqa: BLE001
                raise ProviderError(f"Liste indirilemedi: {e}") from e
            if r.status_code >= 400:
                raise ProviderError(f"Liste indirilemedi: HTTP {r.status_code}")
            raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        for enc in ("utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")

    def _ensure(self):
        if self._data is not None:
            return self._data
        text = self._load_text()
        if "#EXTINF" not in text and "://" not in text:
            raise ProviderError("Geçerli bir M3U listesi bulunamadı.")
        entries, header = parse_m3u(text)
        if not entries:
            raise ProviderError("Listede hiç yayın bulunamadı.")
        if not self.epg_url:
            self.epg_url = (header.get("url-tvg") or header.get("x-tvg-url") or "").split(",")[0].strip()

        data = {LIVE: ([], {}), MOVIE: ([], {}), SERIES: ([], {})}
        series_map = {}
        num = 0
        for section, name, url, attrs, group, opts in entries:
            cats = data[section][1]
            cid = group
            if cid not in cats:
                cats[cid] = Category(cid, group)
            logo = attrs.get("tvg-logo", "")
            extra = {}
            if opts.get("http-user-agent"):
                extra["ua"] = opts["http-user-agent"]
            if opts.get("http-referrer"):
                extra["referrer"] = opts["http-referrer"]
            if section == LIVE:
                num += 1
                iid = stable_id(attrs.get("tvg-id", ""), name, group)
                data[LIVE][0].append(Item(LIVE, iid, name, logo, cid, num, url, "", 0, 0.0, "",
                                          attrs.get("tvg-id") or attrs.get("tvg-name") or name,
                                          1 if attrs.get("catchup") or attrs.get("timeshift") else 0, extra))
            elif section == MOVIE:
                ext = os.path.splitext(url.split("?")[0])[1].lstrip(".") or "mp4"
                data[MOVIE][0].append(Item(MOVIE, stable_id(url), name, logo, cid, 0, url, ext, 0, 0.0,
                                           year_from(name), extra=extra))
            else:
                m = _EP_RE.match(name)
                if m and m.group("name").strip():
                    sname, s, e = m.group("name").strip(" -|."), int(m.group("s")), int(m.group("e"))
                else:
                    sname, s, e = name, 1, len(series_map.get((group, name), {}).get("eps", [])) + 1
                key = (group, sname)
                ser = series_map.get(key)
                if ser is None:
                    sid = stable_id("series", group, sname)
                    ser = {"item": Item(SERIES, sid, sname, logo, cid, 0, "", "", 0, 0.0, year_from(sname)),
                           "eps": []}
                    series_map[key] = ser
                ext = os.path.splitext(url.split("?")[0])[1].lstrip(".") or "mp4"
                ser["eps"].append(Item(EPISODE, stable_id(url), name, logo, cid, e, url, ext,
                                       extra={**extra, "series_id": ser["item"].id, "series_name": sname,
                                              "season": s, "episode": e}))
        for ser in series_map.values():
            data[SERIES][0].append(ser["item"])
            self._series_eps[ser["item"].id] = ser["eps"]
        self._data = data
        return data

    def authenticate(self):
        d = self._ensure()
        return {"status": "Active", "expires": "-", "channels": len(d[LIVE][0]),
                "movies": len(d[MOVIE][0]), "series": len(d[SERIES][0])}

    def categories(self, section):
        return list(self._ensure()[section][1].values())

    def items(self, section, category_id=None, page=1):
        lst = self._ensure()[section][0]
        if category_id:
            lst = [i for i in lst if i.category_id == category_id]
        return list(lst), 1

    def series_info(self, item):
        self._ensure()
        seasons = {}
        for ep in self._series_eps.get(item.id, []):
            seasons.setdefault(ep.extra.get("season", 1), []).append(ep)
        for v in seasons.values():
            v.sort(key=lambda x: x.num)
        return {"info": {"cover": item.logo}, "seasons": dict(sorted(seasons.items()))}

    # --- EPG (XMLTV) ---------------------------------------------------
    def _load_epg(self):
        with self._epg_lock:
            if self._epg is not None:
                return self._epg
            self._epg = {}
            if not self.epg_url:
                return self._epg
            try:
                self._epg = load_xmltv(self.session, self.epg_url)
            except Exception:  # noqa: BLE001
                self._epg = {}
            return self._epg

    def short_epg(self, item):
        if not self.epg_url:
            return []
        epg = self._load_epg()
        progs = epg.get(item.epg_id) or epg.get(item.epg_id.lower()) or epg.get(item.name.lower()) or []
        now = time.time()
        return [p for p in progs if p["end"] > now][:4]

    def epg_table(self, item):
        if not self.epg_url:
            return []
        epg = self._load_epg()
        progs = epg.get(item.epg_id) or epg.get(item.epg_id.lower()) or epg.get(item.name.lower()) or []
        now = time.time()
        return [p for p in progs if p["end"] > now - 3 * 3600 and p["start"] < now + 86400]


def _parse_xmltv_time(s):
    s = s.strip()
    try:
        dt = datetime.strptime(s[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return 0
    tz = s[14:].strip()
    if re.match(r"^[+-]\d{4}$", tz):
        sign = 1 if tz[0] == "+" else -1
        off = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
        dt = dt.replace(tzinfo=timezone(off))
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_xmltv(session, url):
    """XMLTV dosyasını akış halinde ayrıştırır; sadece yakın zamandaki programları tutar."""
    import xml.etree.ElementTree as ET

    if os.path.isfile(url):
        fobj = open(url, "rb")
    else:
        r = session.get(normalize_url(url), timeout=120)
        r.raise_for_status()
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        fobj = io.BytesIO(raw)
    now = time.time()
    lo, hi = now - 6 * 3600, now + 36 * 3600
    names = {}
    progs = {}
    with fobj:
        for _ev, el in ET.iterparse(fobj, events=("end",)):
            tag = el.tag
            if tag == "channel":
                cid = el.get("id", "")
                dn = el.find("display-name")
                if dn is not None and dn.text:
                    names[dn.text.strip().lower()] = cid
                el.clear()
            elif tag == "programme":
                start = _parse_xmltv_time(el.get("start", ""))
                end = _parse_xmltv_time(el.get("stop", ""))
                if end > lo and start < hi:
                    t = el.find("title")
                    d = el.find("desc")
                    progs.setdefault(el.get("channel", ""), []).append({
                        "title": (t.text or "") if t is not None else "",
                        "desc": (d.text or "") if d is not None else "",
                        "start": start, "end": end, "archive": False})
                el.clear()
    out = {}
    for cid, lst in progs.items():
        lst.sort(key=lambda p: p["start"])
        out[cid] = lst
        out[cid.lower()] = lst
    for nm, cid in names.items():
        if cid in progs:
            out.setdefault(nm, progs[cid])
    return out
