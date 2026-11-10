"""Test için sahte Xtream Codes sunucusu (gerçek hesap gerekmez).

    python scripts/fake_xtream.py [port]     (varsayılan 8765, kullanıcı/şifre: test/test)

Kanallar uydurmadır; logolar SVG olarak üretilir, yayınlar herkese açık örnek
videolara yönlendirilir (test-videos.co.uk, Blender Vakfı açık filmleri). Samsung mağaza incelemesi
için de bu tür bir demo hesabı gerekir.
"""
import base64
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
USER, PASS = "test", "test"

VIDEOS = [
    "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_5MB.mp4",
    "https://test-videos.co.uk/vids/jellyfish/mp4/h264/720/Jellyfish_720_10s_5MB.mp4",
    "https://test-videos.co.uk/vids/sintel/mp4/h264/720/Sintel_720_10s_5MB.mp4",
]

CATEGORIES = [("1", "Ulusal"), ("2", "Spor"), ("3", "Haber"), ("4", "Belgesel"), ("5", "Çocuk"), ("6", "Müzik")]
NAMES = {
    "1": ["Demo 1 HD", "Demo 2 HD", "Anadolu TV", "Ege Kanal", "Karadeniz TV", "Marmara HD", "Akdeniz TV", "Trakya Kanal"],
    "2": ["Spor Bir", "Spor İki", "Futbol Plus", "Basket TV", "Tenis Kanalı", "Motor Sport"],
    "3": ["Haber Merkezi", "Ekonomi TV", "Dünya Haber", "Gündem 24"],
    "4": ["Doğa Belgesel", "Tarih Kanalı", "Bilim TV", "Uzay HD", "Okyanus"],
    "5": ["Çizgi Dünya", "Minik TV", "Masal Kanalı"],
    "6": ["Pop Müzik", "Türkü TV", "Rock FM TV", "Klasik HD"],
}
COLORS = ["#e5484d", "#30a46c", "#3e63dd", "#f76b15", "#8e4ec6", "#12a594", "#d6409f", "#ffc53d"]

CHANNELS = []
_n = 1
for cid, _ in CATEGORIES:
    for name in NAMES[cid]:
        CHANNELS.append({"num": _n, "stream_id": 1000 + _n, "name": name, "category_id": cid})
        _n += 1

PROGRAMS = ["Sabah Haberleri", "Belgesel Kuşağı", "Canlı Maç", "Akşam Haberleri", "Film Saati", "Müzik Listesi",
            "Yemek Programı", "Gezi Rehberi", "Tartışma Masası", "Çizgi Film", "Gece Sineması", "Spor Özeti"]


# ---- Filmler ve diziler (uydurma adlar)
VOD_CATS = [("11", "Aksiyon"), ("12", "Komedi"), ("13", "Dram"), ("14", "Bilim Kurgu")]
SER_CATS = [("21", "Yerli Diziler"), ("22", "Yabancı Diziler"), ("23", "Belgesel Serileri")]
W1 = ["Gece", "Kayıp", "Son", "Mavi", "Sessiz", "Kırık", "Uzak", "Gizli", "Altın", "Demir", "Kızıl", "Eski"]
W2 = ["Şehir", "Yolculuk", "Liman", "Ada", "Vadi", "Saat", "Rüzgar", "Köprü", "Orman", "Yıldız", "Sokak", "Deniz"]
PLOT = ("Küçük bir kasabada yaşayan bir grup arkadaş, geçmişte kalan bir sırrın peşine düşer. "
        "Test sunucusu için üretilmiş demo açıklamasıdır; gerçek bir yapımla ilgisi yoktur.")

MOVIES = []
for i in range(60):
    cid = VOD_CATS[i % len(VOD_CATS)][0]
    MOVIES.append({"id": 5000 + i, "name": f"{W1[i % 12]} {W2[(i * 5) % 12]}", "cid": cid,
                   "year": 1995 + (i * 7) % 30, "rating": round(5 + (i * 37 % 50) / 10, 1)})
SERIES = []
for i in range(24):
    cid = SER_CATS[i % len(SER_CATS)][0]
    SERIES.append({"id": 7000 + i, "name": f"{W2[(i * 7) % 12]} {W1[(i * 3) % 12]}", "cid": cid,
                   "year": 2008 + i % 16, "rating": round(6 + (i * 13 % 40) / 10, 1), "seasons": 1 + i % 3})


def poster_svg(title, seed, w=300, h=450):
    c1, c2 = COLORS[seed % len(COLORS)], COLORS[(seed + 3) % len(COLORS)]
    fs = 34 if w < 600 else 72
    words = title.split()
    lines = "".join(f'<tspan x="{w // 2}" dy="{fs * 1.2:.0f}">{x}</tspan>' for x in words)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/>'
            f'<stop offset="1" stop-color="{c2}" stop-opacity="0.55"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="#111"/><rect width="{w}" height="{h}" fill="url(#g)"/>'
            f'<circle cx="{w * 0.7:.0f}" cy="{h * 0.3:.0f}" r="{w * 0.25:.0f}" fill="#fff" fill-opacity="0.12"/>'
            f'<text y="{h * 0.62:.0f}" font-family="Arial" font-size="{fs}" font-weight="700" fill="#fff" '
            f'text-anchor="middle">{lines}</text></svg>').encode()


def logo_svg(ch):
    color = COLORS[ch["num"] % len(COLORS)]
    initials = "".join(w[0] for w in ch["name"].split()[:2]).upper()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">'
            f'<rect width="240" height="160" rx="24" fill="{color}"/>'
            f'<text x="120" y="102" font-family="Arial" font-size="64" font-weight="700" fill="#fff" '
            f'text-anchor="middle">{initials}</text></svg>').encode()


def epg(stream_id, limit):
    """Her kanal için 30-90 dakikalık, kanala göre kaydırılmış uydurma programlar."""
    sid = int(stream_id)
    now = int(time.time())
    slot = 1800 * (1 + sid % 3)
    start = now - (now % slot) - slot
    out = []
    for i in range(limit + 1):
        s = start + i * slot
        if s + slot < now:
            continue
        title = PROGRAMS[(sid + s // slot) % len(PROGRAMS)]
        desc = f"{title} — demo açıklaması. Bu program test sunucusu tarafından üretildi."
        out.append({
            "id": str(s), "epg_id": str(sid),
            "title": base64.b64encode(title.encode()).decode(),
            "description": base64.b64encode(desc.encode()).decode(),
            "start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s)),
            "end": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s + slot)),
            "start_timestamp": str(s), "stop_timestamp": str(s + slot),
        })
    return out[:limit]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def send(self, code, body=b"", ctype="application/json", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj):
        self.send(200, json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        host = self.headers.get("Host", f"localhost:{PORT}")
        base = f"http://{host}"

        if u.path.startswith("/poster/") or u.path.startswith("/backdrop/"):
            sid = int(u.path.split("/")[-1].split(".")[0])
            item = next((x for x in MOVIES + SERIES if x["id"] == sid), None)
            if not item:
                return self.send(404)
            big = u.path.startswith("/backdrop/")
            return self.send(200, poster_svg(item["name"], sid, 1280 if big else 300, 720 if big else 450), "image/svg+xml")

        if u.path.startswith("/logo/"):
            sid = int(u.path.split("/")[-1].split(".")[0])
            ch = next((c for c in CHANNELS if c["stream_id"] == sid), None)
            return self.send(200, logo_svg(ch), "image/svg+xml") if ch else self.send(404)

        parts = u.path.strip("/").split("/")
        if parts and parts[0] in ("live", "movie", "series") and len(parts) == 4:
            if parts[1] != USER or parts[2] != PASS:
                return self.send(401)
            sid = int(parts[3].split(".")[0])
            return self.send(302, headers={"Location": VIDEOS[sid % len(VIDEOS)]})

        if u.path == "/get.php":
            if q.get("username") != USER or q.get("password") != PASS:
                return self.send(401)
            lines = ["#EXTM3U"]
            cats = dict(CATEGORIES)
            for c in CHANNELS:
                lines.append(f'#EXTINF:-1 tvg-id="ch{c["stream_id"]}" tvg-name="{c["name"]}" '
                             f'tvg-logo="{base}/logo/{c["stream_id"]}.svg" group-title="{cats[c["category_id"]]}",{c["name"]}')
                lines.append(f'{base}/live/{USER}/{PASS}/{c["stream_id"]}.ts')
            return self.send(200, "\n".join(lines).encode(), "audio/x-mpegurl")

        if u.path != "/player_api.php":
            return self.send(404, b"not found", "text/plain")
        if q.get("username") != USER or q.get("password") != PASS:
            return self.json({"user_info": {"auth": 0}})

        action = q.get("action", "")
        if not action:
            return self.json({
                "user_info": {"username": USER, "auth": 1, "status": "Active",
                              "exp_date": str(int(time.time()) + 86400 * 180), "is_trial": "0",
                              "active_cons": "0", "max_connections": "2"},
                "server_info": {"url": host.split(":")[0], "port": str(PORT), "timezone": "Europe/Istanbul"},
            })
        if action == "get_live_categories":
            return self.json([{"category_id": i, "category_name": n, "parent_id": 0} for i, n in CATEGORIES])
        if action == "get_live_streams":
            cid = q.get("category_id")
            return self.json([{
                "num": c["num"], "name": c["name"], "stream_type": "live", "stream_id": c["stream_id"],
                "stream_icon": f"{base}/logo/{c['stream_id']}.svg", "epg_channel_id": f"ch{c['stream_id']}",
                "added": "1700000000", "category_id": c["category_id"], "tv_archive": 0,
            } for c in CHANNELS if not cid or c["category_id"] == cid])
        if action == "get_short_epg":
            time.sleep(0.2)
            return self.json({"epg_listings": epg(q.get("stream_id", "0"), int(q.get("limit", "4")))})
        if action == "get_vod_categories":
            return self.json([{"category_id": i, "category_name": n, "parent_id": 0} for i, n in VOD_CATS])
        if action == "get_series_categories":
            return self.json([{"category_id": i, "category_name": n, "parent_id": 0} for i, n in SER_CATS])
        if action == "get_vod_streams":
            cid = q.get("category_id")
            return self.json([{
                "num": n + 1, "name": m["name"], "stream_type": "movie", "stream_id": m["id"],
                "stream_icon": f"{base}/poster/{m['id']}.svg", "rating": str(m["rating"]), "year": str(m["year"]),
                "added": "1700000000", "category_id": m["cid"], "container_extension": "mp4",
            } for n, m in enumerate(MOVIES) if not cid or m["cid"] == cid])
        if action == "get_vod_info":
            m = next((x for x in MOVIES if str(x["id"]) == q.get("vod_id")), None)
            if not m:
                return self.json({})
            return self.json({"info": {
                "plot": PLOT, "cast": "Demo Oyuncu 1, Demo Oyuncu 2, Demo Oyuncu 3", "director": "Demo Yönetmen",
                "genre": dict(VOD_CATS)[m["cid"]], "releasedate": f"{m['year']}-05-01", "duration": "01:42:00",
                "rating": str(m["rating"]), "backdrop_path": [f"{base}/backdrop/{m['id']}.svg"],
                "movie_image": f"{base}/poster/{m['id']}.svg"},
                "movie_data": {"stream_id": m["id"], "name": m["name"], "container_extension": "mp4"}})
        if action == "get_series":
            cid = q.get("category_id")
            return self.json([{
                "num": n + 1, "name": x["name"], "series_id": x["id"], "cover": f"{base}/poster/{x['id']}.svg",
                "plot": PLOT, "rating": str(x["rating"]), "releaseDate": f"{x['year']}-09-01",
                "backdrop_path": [f"{base}/backdrop/{x['id']}.svg"], "category_id": x["cid"], "last_modified": "1700000000",
            } for n, x in enumerate(SERIES) if not cid or x["cid"] == cid])
        if action == "get_series_info":
            x = next((y for y in SERIES if str(y["id"]) == q.get("series_id")), None)
            if not x:
                return self.json({})
            episodes = {}
            for sn in range(1, x["seasons"] + 1):
                episodes[str(sn)] = [{
                    "id": str(x["id"] * 100 + sn * 10 + e), "episode_num": e, "title": f"{x['name']} S{sn:02d}E{e:02d}",
                    "container_extension": "mp4", "season": sn,
                    "info": {"plot": PLOT, "duration": "00:45:00", "movie_image": f"{base}/backdrop/{x['id']}.svg"},
                } for e in range(1, 9)]
            return self.json({"info": {
                "name": x["name"], "plot": PLOT, "cast": "Demo Oyuncu 1, Demo Oyuncu 2", "director": "Demo Yönetmen",
                "genre": dict(SER_CATS)[x["cid"]], "releaseDate": f"{x['year']}-09-01", "rating": str(x["rating"]),
                "backdrop_path": [f"{base}/backdrop/{x['id']}.svg"], "cover": f"{base}/poster/{x['id']}.svg"},
                "episodes": episodes})
        return self.json({})


if __name__ == "__main__":
    print(f"Sahte Xtream sunucusu: http://localhost:{PORT}  (kullanıcı/şifre: {USER}/{PASS})")
    # Windows'ta aynı port iki kez açılabiliyor; ikinci kopya hata versin
    ThreadingHTTPServer.allow_reuse_address = False
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
