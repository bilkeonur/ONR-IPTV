"""Xtream Codes API sağlayıcısı."""
import base64
import re
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from .base import (EPISODE, LIVE, MOVIE, SERIES, Category, Item, Provider, ProviderError,
                   normalize_url, to_float, to_int, year_from)

_ACTIONS = {
    LIVE: ("get_live_categories", "get_live_streams"),
    MOVIE: ("get_vod_categories", "get_vod_streams"),
    SERIES: ("get_series_categories", "get_series"),
}


def parse_xtream_m3u_link(url):
    """get.php?username=..&password=.. biçimindeki M3U linkinden Xtream bilgilerini çıkarır."""
    try:
        u = urlparse(normalize_url(url))
        q = parse_qs(u.query)
        if "username" in q and "password" in q:
            return f"{u.scheme}://{u.netloc}", q["username"][0], q["password"][0]
    except ValueError:
        pass
    return None


def _b64(s):
    if not s:
        return ""
    try:
        return base64.b64decode(s).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return str(s)


class XtreamProvider(Provider):
    kind = "xtream"

    def __init__(self, profile, session):
        super().__init__(profile, session)
        url = normalize_url(profile["url"]).rstrip("/")
        url = re.sub(r"/(player_api|get|panel_api|xmltv)\.php.*$", "", url)
        self.base = url
        self.username = profile.get("username", "")
        self.password = profile.get("password", "")
        self.live_ext = "ts"
        self.server_tz = None

    def _api(self, timeout=30, **params):
        p = {"username": self.username, "password": self.password}
        p.update(params)
        try:
            r = self.session.get(f"{self.base}/player_api.php", params=p, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Sunucuya bağlanılamadı: {e}") from e
        if r.status_code in (401, 403):
            raise ProviderError("Kullanıcı adı veya şifre hatalı (yetkisiz erişim).")
        if r.status_code >= 400:
            raise ProviderError(f"Sunucu hatası: HTTP {r.status_code}")
        text = r.text.strip()
        if not text:
            return []
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError("Sunucudan geçersiz yanıt geldi (Xtream API değil mi?).") from e

    def authenticate(self):
        data = self._api(timeout=20)
        if not isinstance(data, dict) or "user_info" not in data:
            raise ProviderError("Geçersiz Xtream yanıtı. URL'yi kontrol edin.")
        ui = data.get("user_info") or {}
        if str(ui.get("auth", "1")) == "0":
            raise ProviderError("Kullanıcı adı veya şifre hatalı.")
        si = data.get("server_info") or {}
        self.server_tz = si.get("timezone")
        formats = ui.get("allowed_output_formats") or []
        exp = to_int(ui.get("exp_date"))
        return {
            "status": ui.get("status", ""),
            "expires": datetime.fromtimestamp(exp).strftime("%d.%m.%Y") if exp else "Sınırsız",
            "max_connections": ui.get("max_connections", ""),
            "active_connections": ui.get("active_cons", ""),
            "trial": str(ui.get("is_trial", "0")) == "1",
            "formats": formats,
            "server": si.get("url", ""),
            "timezone": si.get("timezone", ""),
        }

    def categories(self, section):
        data = self._api(action=_ACTIONS[section][0])
        out = []
        if isinstance(data, list):
            for c in data:
                if isinstance(c, dict):
                    out.append(Category(c.get("category_id", ""), c.get("category_name", "")))
        return out

    @staticmethod
    def _cat(d):
        cid = d.get("category_id")
        if cid in (None, "") and d.get("category_ids"):
            cid = d["category_ids"][0]
        return cid if cid is not None else ""

    def items(self, section, category_id=None, page=1):
        params = {"action": _ACTIONS[section][1]}
        if category_id:
            params["category_id"] = category_id
        data = self._api(timeout=120, **params)
        if isinstance(data, dict):
            data = list(data.values())
        out = []
        if not isinstance(data, list):
            return out, 1
        if section == LIVE:
            for d in data:
                if not isinstance(d, dict):
                    continue
                out.append(Item(LIVE, d.get("stream_id"), d.get("name"), d.get("stream_icon"),
                                self._cat(d), to_int(d.get("num")), "", "",
                                to_int(d.get("added")), 0.0, "", d.get("epg_channel_id") or "",
                                to_int(d.get("tv_archive")),
                                {"archive_days": to_int(d.get("tv_archive_duration"))} if d.get("tv_archive") else None))
        elif section == MOVIE:
            for d in data:
                if not isinstance(d, dict):
                    continue
                rating = to_float(d.get("rating"))
                if not rating and d.get("rating_5based"):
                    rating = to_float(d.get("rating_5based")) * 2
                name = d.get("name") or d.get("title")
                out.append(Item(MOVIE, d.get("stream_id"), name, d.get("stream_icon"),
                                self._cat(d), to_int(d.get("num")), "",
                                d.get("container_extension") or "mp4", to_int(d.get("added")),
                                rating, d.get("year") or year_from(name)))
        else:
            for d in data:
                if not isinstance(d, dict):
                    continue
                rating = to_float(d.get("rating"))
                if not rating and d.get("rating_5based"):
                    rating = to_float(d.get("rating_5based")) * 2
                extra = {k: d.get(k) for k in ("plot", "genre", "cast", "director", "releaseDate") if d.get(k)}
                bd = d.get("backdrop_path")
                if isinstance(bd, list) and bd:
                    extra["backdrop"] = bd[0]
                out.append(Item(SERIES, d.get("series_id"), d.get("name"), d.get("cover"),
                                self._cat(d), to_int(d.get("num")), "", "",
                                to_int(d.get("last_modified")), rating,
                                year_from(d.get("releaseDate") or d.get("release_date") or d.get("year")),
                                extra=extra))
        return out, 1

    def series_info(self, item):
        data = self._api(action="get_series_info", series_id=item.id)
        if not isinstance(data, dict):
            return {"info": {}, "seasons": {}}
        info = data.get("info") or {}
        eps = data.get("episodes") or {}
        if isinstance(eps, list):  # bazı paneller liste döndürür
            grouped = {}
            for e in eps:
                if isinstance(e, list):
                    for x in e:
                        grouped.setdefault(str(x.get("season", 1)), []).append(x)
                elif isinstance(e, dict):
                    grouped.setdefault(str(e.get("season", 1)), []).append(e)
            eps = grouped
        seasons = {}
        for snum, lst in eps.items():
            out = []
            for e in lst or []:
                ei = e.get("info") or {}
                if not isinstance(ei, dict):
                    ei = {}
                title = e.get("title") or f"Bölüm {e.get('episode_num')}"
                out.append(Item(EPISODE, e.get("id"), title, ei.get("movie_image") or item.logo,
                                item.category_id, to_int(e.get("episode_num")), "",
                                e.get("container_extension") or "mp4", 0, to_float(ei.get("rating")), "",
                                extra={"series_id": item.id, "series_name": item.name,
                                       "season": to_int(snum, 1), "episode": to_int(e.get("episode_num")),
                                       "plot": ei.get("plot", ""), "duration": ei.get("duration", "")}))
            out.sort(key=lambda x: x.num)
            seasons[to_int(snum, 1)] = out
        bd = info.get("backdrop_path")
        return {"info": {
            "plot": info.get("plot", ""), "cast": info.get("cast", ""), "director": info.get("director", ""),
            "genre": info.get("genre", ""), "release": info.get("releaseDate") or info.get("release_date", ""),
            "rating": info.get("rating", ""), "backdrop": bd[0] if isinstance(bd, list) and bd else "",
            "cover": info.get("cover", ""), "trailer": info.get("youtube_trailer", ""),
        }, "seasons": dict(sorted(seasons.items()))}

    def vod_info(self, item):
        data = self._api(action="get_vod_info", vod_id=item.id)
        if not isinstance(data, dict):
            return {}
        info = data.get("info") or {}
        if not isinstance(info, dict):
            return {}
        bd = info.get("backdrop_path")
        return {
            "plot": info.get("plot") or info.get("description", ""),
            "cast": info.get("cast") or info.get("actors", ""),
            "director": info.get("director", ""), "genre": info.get("genre", ""),
            "release": info.get("releasedate") or info.get("release_date", ""),
            "duration": info.get("duration", ""), "rating": info.get("rating", ""),
            "backdrop": bd[0] if isinstance(bd, list) and bd else (bd if isinstance(bd, str) else ""),
            "cover": info.get("movie_image") or info.get("cover_big", ""),
            "trailer": info.get("youtube_trailer", ""),
        }

    def stream_url(self, item):
        if item.url:
            return item.url
        if item.kind == LIVE:
            return f"{self.base}/live/{self.username}/{self.password}/{item.id}.{self.live_ext}"
        if item.kind == MOVIE:
            return f"{self.base}/movie/{self.username}/{self.password}/{item.id}.{item.ext or 'mp4'}"
        if item.kind == EPISODE:
            return f"{self.base}/series/{self.username}/{self.password}/{item.id}.{item.ext or 'mp4'}"
        return ""

    @staticmethod
    def _parse_listings(data):
        out = []
        listings = data.get("epg_listings", []) if isinstance(data, dict) else []
        now = time.time()
        for p in listings or []:
            start = to_int(p.get("start_timestamp"))
            end = to_int(p.get("stop_timestamp"))
            if not start:
                continue
            out.append({
                "title": _b64(p.get("title")), "desc": _b64(p.get("description")),
                "start": start, "end": end, "start_str": p.get("start", ""),
                "archive": str(p.get("has_archive", "0")) == "1" and end < now,
            })
        out.sort(key=lambda x: x["start"])
        return out

    def short_epg(self, item):
        try:
            data = self._api(timeout=10, action="get_short_epg", stream_id=item.id, limit=4)
        except ProviderError:
            return []
        return self._parse_listings(data)

    def epg_table(self, item):
        try:
            data = self._api(timeout=20, action="get_simple_data_table", stream_id=item.id)
        except ProviderError:
            return self.short_epg(item)
        progs = self._parse_listings(data)
        if not progs:
            return self.short_epg(item)
        # Dünden yarına kadar olanları göster
        now = time.time()
        return [p for p in progs if p["end"] > now - 86400 * 3 and p["start"] < now + 86400]

    def catchup_url(self, item, prog):
        if not item.archive or not prog.get("archive"):
            return None
        dur = max(1, (prog["end"] - prog["start"]) // 60)
        s = prog.get("start_str") or ""
        m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})", s)
        if m:
            start = f"{m.group(1)}:{m.group(2)}-{m.group(3)}"
        else:
            start = datetime.fromtimestamp(prog["start"]).strftime("%Y-%m-%d:%H-%M")
        return f"{self.base}/timeshift/{self.username}/{self.password}/{dur}/{start}/{item.id}.ts"
