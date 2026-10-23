"""Chromecast'e yayın gönderme (pychromecast) ve yerel dosyalar için LAN üzerinden küçük bir HTTP sunucusu.

Chromecast URL'yi kendisi açar; bu yüzden sağlayıcıya özel User-Agent/Referer başlıkları gönderilemez ve
Xtream canlı yayınlarında MPEG-TS yerine HLS (.m3u8) adresi kullanılır (varsayılan alıcı ham TS oynatmaz).
"""
import mimetypes
import os
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .qt import QObject, Signal
from .tasks import run_async

try:
    import pychromecast
    from pychromecast import discovery as _discovery
except ImportError:  # pragma: no cover - isteğe bağlı bağımlılık
    pychromecast = None

CONTENT_TYPES = {".m3u8": "application/x-mpegURL", ".m3u": "application/x-mpegURL", ".mp4": "video/mp4",
                 ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm", ".ts": "video/mp2t",
                 ".avi": "video/x-msvideo", ".mov": "video/quicktime"}


def available():
    return pychromecast is not None


def content_type(url):
    ext = os.path.splitext(url.split("?")[0].lower())[1]
    return CONTENT_TYPES.get(ext) or mimetypes.guess_type(url)[0] or "video/mp4"


class _FileHandler(BaseHTTPRequestHandler):
    """Tek bir dosyayı Range (ileri/geri sarma) desteğiyle sunar."""

    server_version = "ONRIPTV-Cast"

    def log_message(self, *_args):
        pass

    def _target(self):
        path = self.server.files.get(self.path.split("?")[0])
        return path if path and os.path.exists(path) else None

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head):
        path = self._target()
        if not path:
            self.send_error(404)
            return
        size = os.path.getsize(path)
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if head:
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionError, OSError):
            pass  # Chromecast sararken bağlantıyı keser


class LocalServer:
    def __init__(self):
        self.httpd = None

    def url_for(self, path, device_host):
        if self.httpd is None:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", 0), _FileHandler)
            self.httpd.daemon_threads = True
            self.httpd.files = {}
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        token = "/media/" + secrets.token_urlsafe(8) + os.path.splitext(path)[1].lower()
        self.httpd.files = {token: path}  # her seferinde yalnızca son dosya paylaşılır
        return f"http://{_lan_ip(device_host)}:{self.httpd.server_address[1]}{token}"

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


def _lan_ip(peer):
    """Chromecast'e giden arayüzün yerel IP adresi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((peer, 8009))
        return s.getsockname()[0]
    finally:
        s.close()


class CastManager(QObject):
    devicesFound = Signal(list)       # [(ad, model)]
    started = Signal(str)             # cihaz adı
    failed = Signal(str)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self._infos = []
        self._browser = None
        self.device = None
        self.server = LocalServer()
        self._busy = False

    @property
    def active(self):
        return self.device is not None

    @property
    def device_name(self):
        return self.device.name if self.device is not None else ""

    def discover(self):
        if not available() or self._busy:
            return
        self._busy = True

        def work():
            self._stop_browser()
            infos, browser = _discovery.discover_chromecasts(timeout=5)
            self._browser = browser
            return infos

        def done(infos):
            self._busy = False
            self._infos = sorted(infos, key=lambda i: i.friendly_name or "")
            self.devicesFound.emit([(i.friendly_name, i.model_name) for i in self._infos])

        def fail(e):
            self._busy = False
            self.devicesFound.emit([])

        run_async(work, on_done=done, on_error=fail)

    def cast(self, index, url, title="", live=False, start=0):
        info = self._infos[index]
        local = os.path.exists(url)

        def work():
            zc = self._browser.zc if self._browser is not None else None
            dev = pychromecast.get_chromecast_from_cast_info(info, zc, tries=2, timeout=10)
            dev.wait(timeout=10)
            target = self.server.url_for(url, info.host) if local else url
            mc = dev.media_controller
            mc.play_media(target, content_type(target), title=title or None,
                          stream_type="LIVE" if live else "BUFFERED",
                          current_time=start if start and not live else None)
            mc.block_until_active(timeout=15)
            return dev

        def done(dev):
            self._disconnect()
            self.device = dev
            self.started.emit(dev.name)

        run_async(work, on_done=done, on_error=lambda e: self.failed.emit(str(e)))

    def stop(self):
        dev = self.device
        self.device = None
        if dev is not None:
            def work():
                try:
                    dev.quit_app()
                finally:
                    dev.disconnect(timeout=3)
            run_async(work, on_error=lambda e: None)
        self.server.stop()
        self.stopped.emit()

    def _disconnect(self):
        if self.device is not None:
            try:
                self.device.disconnect(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self.device = None

    def _stop_browser(self):
        if self._browser is not None:
            try:
                self._browser.stop_discovery()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None

    def shutdown(self):
        self._disconnect()
        self.server.stop()
        self._stop_browser()
