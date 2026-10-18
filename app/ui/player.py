"""mpv (libmpv render API) tabanlı video oynatıcı ve video üstü kontrol katmanı."""
import ctypes
import locale
import os
import time

import mpv

from .. import config
from ..qt import (QAbstractItemView, QByteArray, QColor, QCursor, QFrame, QHBoxLayout, QLabel, QListView,
                  QMenu, QObject, QOpenGLContext, QOpenGLWidget, QPainter, QPen, QRectF, QSize, QSlider, Qt,
                  QTimer, QToolButton, QVBoxLayout, QWidget, Signal)
from . import theme
from .icons import icon


def fmt_time(sec):
    if sec is None or sec < 0:
        return "--:--"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class _Bridge(QObject):
    """mpv iş parçacıklarından gelen olayları ana iş parçacığına taşır."""
    prop = Signal(str, object)
    ended = Signal(str, str)
    loaded = Signal()
    frame = Signal()


class MpvSurface(QOpenGLWidget):
    ready = Signal()

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.ctx = None
        self._install_fence_hooks()
        self._proc_fn = mpv.MpvGlGetProcAddressFn(self._get_proc)
        player.bridge.frame.connect(self.update, Qt.ConnectionType.QueuedConnection)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    # mpv'nin render API'si her karede glFenceSync ile bir GPU çiti oluşturuyor ama hiç silmiyor
    # (libmpv_gl.c: done_frame -> ra_gl_ctx_submit_frame; silme sadece render API'de çağrılmayan
    # swap_buffers'ta). Pi'deki Mesa v3d'de her çit bir dosya tanımlayıcısı olduğundan ~40 sn'de
    # "Too many open files" ile görüntü donuyor; Windows'ta da sürücü nesneleri birikiyor.
    # Çözüm: glFenceSync/glDeleteSync'i sarmalayıp mpv'nin bıraktığı eski çitleri her karede biz siliyoruz.
    _FENCE_T = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)
    _DELETE_T = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
    _KEEP_FENCES = 3

    def _install_fence_hooks(self):
        self._real_fence = None
        self._real_delete = None
        self._fences = []          # mpv'nin oluşturduğu, henüz silinmemiş çitler (eskiden yeniye)
        self._reaped = set()       # bizim sildiklerimiz; mpv kapanışta tekrar silmeye kalkarsa atlanır
        self._fence_hook = self._FENCE_T(self._on_fence)
        self._delete_hook = self._DELETE_T(self._on_delete)

    def _on_fence(self, condition, flags):
        sync = self._real_fence(condition, flags)
        if sync:
            self._fences.append(sync)
            self._reaped.discard(sync)
        return sync

    def _on_delete(self, sync):
        if not sync or sync in self._reaped:
            self._reaped.discard(sync)
            return
        try:
            self._fences.remove(sync)
        except ValueError:
            pass
        self._real_delete(sync)

    def _reap_fences(self):
        while len(self._fences) > self._KEEP_FENCES and self._real_delete is not None:
            sync = self._fences.pop(0)
            self._real_delete(sync)
            self._reaped.add(sync)
        if len(self._reaped) > 64:
            self._reaped.clear()

    def _get_proc(self, _ctx, name):
        glctx = QOpenGLContext.currentContext()
        if glctx is None:
            return 0
        addr = glctx.getProcAddress(QByteArray(name))
        try:
            addr = int(addr) if addr else 0
        except TypeError:
            return 0
        if addr and name == b"glFenceSync":
            self._real_fence = self._FENCE_T(addr)
            return ctypes.cast(self._fence_hook, ctypes.c_void_p).value
        if addr and name == b"glDeleteSync":
            self._real_delete = self._DELETE_T(addr)
            return ctypes.cast(self._delete_hook, ctypes.c_void_p).value
        return addr

    def initializeGL(self):
        self.ctx = mpv.MpvRenderContext(self.player.mpv, "opengl",
                                        opengl_init_params={"get_proc_address": self._proc_fn})
        self.ctx.update_cb = self.player.bridge.frame.emit
        self.context().aboutToBeDestroyed.connect(self._free)
        self.ready.emit()

    def _free(self):
        if self.ctx is not None:
            self.makeCurrent()
            self.ctx.update_cb = None
            self.ctx.free()
            self.ctx = None
            self.doneCurrent()

    def paintGL(self):
        if self.ctx is None:
            return
        r = self.devicePixelRatioF()
        self.ctx.render(flip_y=True, opengl_fbo={"w": int(self.width() * r), "h": int(self.height() * r),
                                                  "fbo": self.defaultFramebufferObject()})
        self._reap_fences()


class MpvPlayer(QObject):
    """mpv örneğini sarmalar; özellik değişimlerini Qt sinyallerine çevirir."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        locale.setlocale(locale.LC_NUMERIC, "C")
        buf = int(settings.get("buffer_seconds", 8))
        extra = {"profile": "fast"} if config.IS_ARM else {}  # Pi'de GPU'yu yormayan ölçekleme
        self.mpv = mpv.MPV(
            **extra,
            vo="libmpv", hwdec=settings.get("hwdec"), idle="yes", keep_open="no",
            input_default_bindings=False, input_vo_keyboard=False, ytdl=False,
            cache="yes", cache_secs=max(buf, 2), demuxer_readahead_secs=max(buf, 2),
            demuxer_max_bytes="48MiB" if config.IS_ARM else "150MiB", demuxer_max_back_bytes="16MiB",
            network_timeout=20, user_agent=settings.get("user_agent"),
            volume=settings.get("volume", 100), sub_auto="fuzzy", audio_display="no",
            hr_seek="yes", keepaspect="yes", msg_level="all=warn",
            hls_bitrate=str(settings.get("hls_bitrate", "max")),
        )
        try:
            self.mpv["stream-lavf-o"] = "reconnect=1,reconnect_streamed=1,reconnect_delay_max=4"
        except Exception:  # noqa: BLE001
            pass
        self.bridge = _Bridge()
        for name in ("time-pos", "duration", "pause", "paused-for-cache", "cache-buffering-state",
                     "idle-active", "track-list", "volume", "mute", "video-params"):
            self.mpv.observe_property(name, self._make_obs(name))

        @self.mpv.event_callback("end-file")
        def _end(ev):
            d = ev.as_dict()
            reason = d.get("reason", b"")
            err = d.get("file_error", b"")
            self.bridge.ended.emit(reason.decode() if isinstance(reason, bytes) else str(reason),
                                   err.decode() if isinstance(err, bytes) else str(err or ""))

        @self.mpv.event_callback("file-loaded")
        def _loaded(_ev):
            self.bridge.loaded.emit()

    def _make_obs(self, name):
        def cb(_name, value):
            self.bridge.prop.emit(name, value)
        return cb

    def set_headers(self, headers):
        ua = headers.get("User-Agent") or self.settings.get("user_agent")
        self.mpv["user-agent"] = ua
        fields = [f"{k}: {v}" for k, v in headers.items() if k.lower() != "user-agent"]
        self.mpv["http-header-fields"] = fields
        self.mpv["referrer"] = headers.get("Referer", "")

    def load(self, url, start=0):
        if start and start > 5:
            self.mpv["start"] = str(int(start))
        else:
            self.mpv["start"] = "none"
        self.mpv.loadfile(url, "replace")
        self.mpv.pause = False

    def stop(self):
        try:
            self.mpv.command("stop")
        except Exception:  # noqa: BLE001
            pass

    def terminate(self):
        try:
            self.mpv.terminate()
        except Exception:  # noqa: BLE001
            pass


class Spinner(QWidget):
    def __init__(self, parent=None, size=54):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""

    def _tick(self):
        self.angle = (self.angle + 7) % 360
        self.update()

    def showEvent(self, e):
        self.timer.start()

    def hideEvent(self, e):
        self.timer.stop()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(5, 5, self.width() - 10, self.height() - 10)
        pen = QPen(QColor(255, 255, 255, 40), 4)
        p.setPen(pen)
        p.drawEllipse(r)
        pen.setColor(QColor(theme.ACCENT))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self.angle * 16, 100 * 16)
        if self.text:
            p.setPen(QColor(theme.TEXT))
            f = p.font()
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)


def _tbtn(name, tip, size=26, checkable=False):
    b = QToolButton()
    b.setIcon(icon(name, "#ffffff"))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setMinimumSize(size + 16, size + 16)
    return b


class SeekSlider(QSlider):
    """Tıklanan noktaya atlayan kaydırıcı."""

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            x = e.position().x() if hasattr(e, "position") else e.x()
            v = self.minimum() + (self.maximum() - self.minimum()) * x / max(1, self.width())
            self.setValue(int(v))
            self.sliderMoved.emit(int(v))
        super().mousePressEvent(e)


class PlayerWidget(QWidget):
    """Video yüzeyi + kontrol katmanı. 'preview' ve 'full' olmak üzere iki modu vardır."""

    exitRequested = Signal()
    fullRequested = Signal()
    channelStep = Signal(int)
    channelPicked = Signal(object)
    favoriteToggled = Signal()
    progress = Signal(float, float)      # konum, süre
    playbackEnded = Signal()
    recordToggled = Signal(bool)
    windowFullscreenToggled = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("Player")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#000000"))
        self.setPalette(pal)

        self.core = MpvPlayer(settings)
        self.surface = MpvSurface(self.core, self)
        self.surface.ready.connect(self._on_surface_ready)
        self._surface_ready = False
        self._pending = None

        self.mode = "hidden"
        self.is_live = False
        self.item = None
        self.url = ""
        self.duration = 0.0
        self.position = 0.0
        self.paused = False
        self.recording = False
        self._retries = 0
        self._last_progress = 0
        self._started_at = 0
        self._seeking = False
        self._stopped_by_user = False
        self.epg_now = None
        self.tracks = []

        self._build_overlay()
        self.core.bridge.prop.connect(self._on_prop)
        self.core.bridge.ended.connect(self._on_ended)
        self.core.bridge.loaded.connect(self._on_loaded)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(3500)
        self.hide_timer.timeout.connect(self._auto_hide)

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start()

        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._retry)

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)
        self._click_timer.timeout.connect(self._single_click)
        self.hide()

    # ------------------------------------------------------------------ UI
    def _build_overlay(self):
        # Üst bar
        self.top = QFrame(self)
        self.top.setObjectName("OsdTop")
        tl = QHBoxLayout(self.top)
        tl.setContentsMargins(14, 10, 18, 26)
        self.btn_back = _tbtn("back", "Geri (Esc)", 28)
        self.btn_back.clicked.connect(self.exitRequested.emit)
        tl.addWidget(self.btn_back)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("OsdTitle")
        self.lbl_sub = QLabel()
        self.lbl_sub.setObjectName("OsdText")
        tcol.addWidget(self.lbl_title)
        tcol.addWidget(self.lbl_sub)
        tl.addLayout(tcol, 1)
        self.lbl_rec = QLabel("● KAYIT")
        self.lbl_rec.setObjectName("RecBadge")
        self.lbl_rec.hide()
        tl.addWidget(self.lbl_rec)
        self.lbl_clock = QLabel()
        self.lbl_clock.setObjectName("OsdTitle")
        tl.addWidget(self.lbl_clock)

        # Alt bar
        self.bottom = QFrame(self)
        self.bottom.setObjectName("OsdBottom")
        bl = QVBoxLayout(self.bottom)
        bl.setContentsMargins(18, 30, 18, 12)
        bl.setSpacing(4)
        srow = QHBoxLayout()
        self.lbl_pos = QLabel("00:00")
        self.lbl_pos.setObjectName("OsdText")
        self.lbl_dur = QLabel("00:00")
        self.lbl_dur.setObjectName("OsdText")
        self.slider = SeekSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._seek_release)
        self.slider.sliderMoved.connect(lambda v: self.lbl_pos.setText(fmt_time(v)))
        srow.addWidget(self.lbl_pos)
        srow.addWidget(self.slider, 1)
        srow.addWidget(self.lbl_dur)
        bl.addLayout(srow)

        brow = QHBoxLayout()
        brow.setSpacing(2)
        self.btn_prev = _tbtn("prev", "Önceki kanal (↑)")
        self.btn_prev.clicked.connect(lambda: self.channelStep.emit(-1))
        self.btn_rew = _tbtn("rewind", "10 sn geri (←)")
        self.btn_rew.clicked.connect(lambda: self.seek_rel(-10))
        self.btn_play = _tbtn("pause", "Oynat/Duraklat (Boşluk)", 34)
        self.btn_play.clicked.connect(self.toggle_pause)
        self.btn_fwd = _tbtn("forward", "10 sn ileri (→)")
        self.btn_fwd.clicked.connect(lambda: self.seek_rel(10))
        self.btn_next = _tbtn("next", "Sonraki kanal (↓)")
        self.btn_next.clicked.connect(lambda: self.channelStep.emit(1))
        for b in (self.btn_prev, self.btn_rew, self.btn_play, self.btn_fwd, self.btn_next):
            brow.addWidget(b)
        self.lbl_epg = QLabel()
        self.lbl_epg.setObjectName("OsdText")
        brow.addSpacing(10)
        brow.addWidget(self.lbl_epg, 1)

        self.btn_list = _tbtn("list", "Kanal listesi (L)")
        self.btn_list.clicked.connect(self.toggle_drawer)
        self.btn_fav = _tbtn("star_border", "Favori")
        self.btn_fav.clicked.connect(self.favoriteToggled.emit)
        self.btn_rec = _tbtn("record", "Kaydet (R)")
        self.btn_rec.clicked.connect(self.toggle_record)
        self.btn_audio = _tbtn("audio", "Ses dili (A)")
        self.btn_audio.clicked.connect(lambda: self._track_menu("audio", self.btn_audio))
        self.btn_sub = _tbtn("subtitles", "Altyazı (S)")
        self.btn_sub.clicked.connect(lambda: self._track_menu("sub", self.btn_sub))
        self.btn_aspect = _tbtn("aspect", "Görüntü oranı")
        self.btn_aspect.clicked.connect(self._aspect_menu)
        self.btn_speed = QToolButton()
        self.btn_speed.setText("1x")
        self.btn_speed.setToolTip("Oynatma hızı")
        self.btn_speed.setMinimumSize(42, 42)
        self.btn_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_speed.setStyleSheet("font-weight:800; font-size:13px;")
        self.btn_speed.clicked.connect(self._speed_menu)
        self.btn_mute = _tbtn("volume", "Ses (M)")
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 130)
        self.vol.setFixedWidth(90)
        self.vol.setValue(int(self.settings.get("volume", 100)))
        self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol.valueChanged.connect(self._set_volume)
        self.btn_fs = _tbtn("fullscreen", "Tam ekran (F)")
        self.btn_fs.clicked.connect(self.windowFullscreenToggled.emit)
        for b in (self.btn_list, self.btn_fav, self.btn_rec, self.btn_audio, self.btn_sub, self.btn_aspect,
                  self.btn_speed, self.btn_mute, self.vol, self.btn_fs):
            brow.addWidget(b)
        bl.addLayout(brow)

        # Orta: yükleniyor
        self.spinner = Spinner(self, 60)
        self.spinner.hide()
        self.center_play = QToolButton(self)
        self.center_play.setIcon(icon("play", "#ffffff"))
        self.center_play.setIconSize(QSize(46, 46))
        self.center_play.setStyleSheet("QToolButton{background:rgba(0,0,0,0.55);border-radius:38px;}"
                                       f"QToolButton:hover{{background:{theme.ACCENT_LO};}}")
        self.center_play.setFixedSize(76, 76)
        self.center_play.clicked.connect(self.toggle_pause)
        self.center_play.hide()

        # Bildirim
        self.toast = QLabel(self)
        self.toast.setObjectName("OsdToast")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)

        # Önizleme modu: büyütme ipucu
        self.expand_btn = QToolButton(self)
        self.expand_btn.setIcon(icon("fullscreen", "#ffffff"))
        self.expand_btn.setIconSize(QSize(22, 22))
        self.expand_btn.setStyleSheet("QToolButton{background:rgba(0,0,0,0.55);border-radius:8px;padding:6px;}"
                                      f"QToolButton:hover{{background:{theme.ACCENT_LO};}}")
        self.expand_btn.setToolTip("Tam ekran izle")
        self.expand_btn.clicked.connect(self.fullRequested.emit)
        self.expand_btn.hide()

        # Kanal çekmecesi
        self.drawer = QFrame(self)
        self.drawer.setObjectName("Drawer")
        dl = QVBoxLayout(self.drawer)
        dl.setContentsMargins(8, 12, 8, 8)
        self.drawer_title = QLabel("Kanallar")
        self.drawer_title.setObjectName("H2")
        dl.addWidget(self.drawer_title)
        self.drawer_list = QListView()
        self.drawer_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.drawer_list.setUniformItemSizes(True)
        self.drawer_list.clicked.connect(self._drawer_clicked)
        self.drawer_list.activated.connect(self._drawer_clicked)
        dl.addWidget(self.drawer_list)
        self.drawer.hide()

        self.overlay_widgets = [self.top, self.bottom]
        for w in self.overlay_widgets:
            w.hide()
        self.osd_visible = False

    def set_drawer_model(self, model, delegate):
        self.drawer_list.setModel(model)
        self.drawer_list.setItemDelegate(delegate)

    def resizeEvent(self, e):
        w, h = self.width(), self.height()
        self.surface.setGeometry(0, 0, w, h)
        self.top.setGeometry(0, 0, w, 84)
        bh = self.bottom.sizeHint().height()
        self.bottom.setGeometry(0, h - bh, w, bh)
        self.spinner.move((w - self.spinner.width()) // 2, (h - self.spinner.height()) // 2)
        self.center_play.move((w - 76) // 2, (h - 76) // 2)
        self.expand_btn.move(w - 46, h - 46)
        dw = min(340, int(w * 0.4))
        self.drawer.setGeometry(0, 0, dw, h)
        self._place_toast()

    def _place_toast(self):
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2, 96 if self.mode == "full" else 12)

    def show_toast(self, text, ms=2200):
        self.toast.setText(text)
        self._place_toast()
        self.toast.show()
        self.toast.raise_()
        self.toast_timer.start(ms)

    # ---------------------------------------------------------- Modlar
    def set_mode(self, mode):
        self.mode = mode
        if mode == "hidden":
            self.hide()
            self.unsetCursor()
            return
        self.show()
        self.raise_()
        if mode == "full":
            self.expand_btn.hide()
            self.show_osd()
            self.setFocus()
        else:
            self.hide_osd(force=True)
            self.drawer.hide()
            self.unsetCursor()
        self._place_toast()

    def show_osd(self):
        if self.mode != "full":
            return
        self.unsetCursor()
        for w in self.overlay_widgets:
            w.show()
            w.raise_()
        self.toast.raise_()
        self.osd_visible = True
        self.hide_timer.start()

    def hide_osd(self, force=False):
        if not force and (self.drawer.isVisible() or self.paused or self.slider.isSliderDown()):
            self.hide_timer.start()
            return
        for w in self.overlay_widgets:
            w.hide()
        self.osd_visible = False
        if self.mode == "full":
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

    def _auto_hide(self):
        if self.mode == "full":
            under = self.childAt(self.mapFromGlobal(QCursor.pos()))
            if under is not None and under is not self.surface and self.bottom.isAncestorOf(under):
                self.hide_timer.start()
                return
            self.hide_osd()

    def toggle_drawer(self):
        if self.drawer.isVisible():
            self.drawer.hide()
        else:
            self.drawer.show()
            self.drawer.raise_()
            idx = self.drawer_list.currentIndex()
            if idx.isValid():
                self.drawer_list.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.drawer_list.setFocus()
        self.hide_timer.start()

    def _drawer_clicked(self, idx):
        item = idx.data(Qt.ItemDataRole.UserRole)
        if item is not None:
            self.channelPicked.emit(item)

    # ---------------------------------------------------------- Olaylar
    def mouseMoveEvent(self, e):
        if self.mode == "full":
            if not self.osd_visible:
                self.show_osd()
            else:
                self.hide_timer.start()
        elif self.mode == "preview":
            self.expand_btn.show()
            self.expand_btn.raise_()
            self.hide_timer.start()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        if self.mode == "preview":
            self.expand_btn.hide()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._click_timer.start()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self._click_timer.stop()
        if self.mode == "preview":
            self.fullRequested.emit()
        else:
            self.windowFullscreenToggled.emit()

    def _single_click(self):
        if self.mode == "preview":
            self.fullRequested.emit()
        elif self.mode == "full":
            if self.drawer.isVisible():
                self.drawer.hide()
            elif self.osd_visible:
                self.hide_osd(force=True)
            else:
                self.show_osd()

    def wheelEvent(self, e):
        if self.mode == "full":
            d = 5 if e.angleDelta().y() > 0 else -5
            self.vol.setValue(self.vol.value() + d)
            self.show_toast(f"Ses: {self.vol.value()}%", 900)

    def keyPressEvent(self, e):
        k = e.key()
        K = Qt.Key
        if self.mode != "full":
            return super().keyPressEvent(e)
        self.show_osd()
        if k in (K.Key_Escape, K.Key_Backspace, K.Key_Back):
            if self.drawer.isVisible():
                self.drawer.hide()
            else:
                self.exitRequested.emit()
        elif k in (K.Key_Space, K.Key_K, K.Key_MediaPlay, K.Key_MediaPause, K.Key_MediaTogglePlayPause):
            self.toggle_pause()
        elif k in (K.Key_F, K.Key_F11):
            self.windowFullscreenToggled.emit()
        elif k == K.Key_M:
            self.toggle_mute()
        elif k in (K.Key_Plus, K.Key_VolumeUp):
            self.vol.setValue(self.vol.value() + 5)
        elif k in (K.Key_Minus, K.Key_VolumeDown):
            self.vol.setValue(self.vol.value() - 5)
        elif k == K.Key_L and self.is_live:
            self.toggle_drawer()
        elif k == K.Key_R and self.is_live:
            self.toggle_record()
        elif k == K.Key_A:
            self._track_menu("audio", self.btn_audio)
        elif k == K.Key_S:
            self._track_menu("sub", self.btn_sub)
        elif self.drawer.isVisible() and k in (K.Key_Up, K.Key_Down, K.Key_Return, K.Key_Enter):
            self.drawer_list.keyPressEvent(e)
            if k in (K.Key_Return, K.Key_Enter):
                self._drawer_clicked(self.drawer_list.currentIndex())
        elif k in (K.Key_Up, K.Key_PageUp, K.Key_ChannelUp) and self.is_live:
            self.channelStep.emit(-1)
        elif k in (K.Key_Down, K.Key_PageDown, K.Key_ChannelDown) and self.is_live:
            self.channelStep.emit(1)
        elif k == K.Key_Left and not self.is_live:
            self.seek_rel(-10)
        elif k == K.Key_Right and not self.is_live:
            self.seek_rel(10)
        elif k in (K.Key_Return, K.Key_Enter) and self.is_live:
            self.toggle_drawer()
        else:
            super().keyPressEvent(e)

    # ---------------------------------------------------------- Oynatma
    def _on_surface_ready(self):
        self._surface_ready = True
        if self._pending:
            url, start = self._pending
            self._pending = None
            self.core.load(url, start)

    def play(self, url, item=None, title="", subtitle="", live=False, start=0, headers=None):
        self.item = item
        self.url = url
        self.is_live = live
        self.duration = 0
        self.position = 0
        self._retries = 0
        self._started_at = time.time()
        self._stopped_by_user = False
        self.epg_now = None
        if self.recording:
            self.toggle_record()
        self.lbl_title.setText(title)
        self.lbl_sub.setText(subtitle)
        self.lbl_epg.setText("")
        self.slider.setRange(0, 0)
        self.lbl_pos.setText("CANLI" if live else "00:00")
        self.lbl_dur.setText("")
        for b in (self.btn_prev, self.btn_next, self.btn_list, self.btn_rec):
            b.setVisible(live)
        for b in (self.btn_rew, self.btn_fwd, self.btn_speed):
            b.setVisible(not live)
        self.slider.setEnabled(not live)
        self.btn_speed.setText("1x")
        self.core.mpv.speed = 1.0
        self.spinner.text = ""
        self.spinner.show()
        self.spinner.raise_()
        self.center_play.hide()
        self.core.set_headers(headers or {})
        if self.mode == "hidden":
            self.set_mode("preview")
        if not self._surface_ready:
            self._pending = (url, start)
            self.surface.update()
        else:
            self.core.load(url, start)

    def stop(self):
        self._stopped_by_user = True
        self.retry_timer.stop()
        if self.recording:
            self.toggle_record()
        self.core.stop()
        self.spinner.hide()
        self.center_play.hide()
        self.item = None
        self.url = ""

    def set_favorite(self, fav):
        self.btn_fav.setIcon(icon("star" if fav else "star_border", theme.ACCENT if fav else "#ffffff"))

    def set_epg(self, cur, nxt):
        self.epg_now = cur
        if cur:
            t = f"{time.strftime('%H:%M', time.localtime(cur['start']))}–{time.strftime('%H:%M', time.localtime(cur['end']))}  {cur['title']}"
            if nxt:
                t += f"   ›  {time.strftime('%H:%M', time.localtime(nxt['start']))} {nxt['title']}"
            self.lbl_epg.setText(t)
            self.lbl_sub.setText(cur["title"])
        else:
            self.lbl_epg.setText("")
        self._update_live_bar()

    def _update_live_bar(self):
        if not self.is_live:
            return
        cur = self.epg_now
        if cur and cur["end"] > cur["start"]:
            now = time.time()
            self.slider.setRange(0, int(cur["end"] - cur["start"]))
            self.slider.setValue(int(now - cur["start"]))
            self.lbl_pos.setText(time.strftime("%H:%M", time.localtime(cur["start"])))
            self.lbl_dur.setText(time.strftime("%H:%M", time.localtime(cur["end"])))
        else:
            self.slider.setRange(0, 0)
            self.lbl_pos.setText("CANLI")
            self.lbl_dur.setText("")

    def toggle_pause(self):
        if not self.url:
            return
        self.core.mpv.pause = not self.core.mpv.pause

    def seek_rel(self, sec):
        if self.is_live or not self.url:
            return
        try:
            self.core.mpv.seek(sec, "relative")
            self.show_toast(("+" if sec > 0 else "") + f"{sec} sn", 700)
        except Exception:  # noqa: BLE001
            pass

    def _seek_release(self):
        self._seeking = False
        if not self.is_live and self.duration:
            try:
                self.core.mpv.seek(self.slider.value(), "absolute")
            except Exception:  # noqa: BLE001
                pass

    def toggle_mute(self):
        self.core.mpv.mute = not self.core.mpv.mute

    def _set_volume(self, v):
        self.core.mpv.volume = v
        self.settings.data["volume"] = v

    def _tick(self):
        self.lbl_clock.setText(time.strftime("%H:%M"))
        if self.is_live and self.mode != "hidden":
            self._update_live_bar()
            if self.epg_now and time.time() > self.epg_now["end"]:
                self.epg_now = None

    def _on_prop(self, name, value):
        if name == "time-pos":
            if value is None:
                return
            self.position = value
            if not self.is_live:
                if not self._seeking:
                    self.slider.setValue(int(value))
                    self.lbl_pos.setText(fmt_time(value))
                now = time.time()
                if now - self._last_progress > 5 and self.duration:
                    self._last_progress = now
                    self.progress.emit(self.position, self.duration)
            if value > 2:
                self._retries = 0
        elif name == "duration":
            self.duration = value or 0
            if not self.is_live and self.duration:
                self.slider.setRange(0, int(self.duration))
                self.lbl_dur.setText(fmt_time(self.duration))
        elif name == "pause":
            self.paused = bool(value)
            self.btn_play.setIcon(icon("play" if self.paused else "pause", "#ffffff"))
            self.center_play.setVisible(self.paused and self.mode == "full" and bool(self.url))
            if self.center_play.isVisible():
                self.center_play.raise_()
            if self.paused:
                self.show_osd()
        elif name == "paused-for-cache":
            if value and self.url:
                self.spinner.show()
                self.spinner.raise_()
            else:
                self.spinner.hide()
        elif name == "cache-buffering-state":
            if value is not None and self.spinner.isVisible():
                self.spinner.text = f"{int(value)}%"
        elif name == "video-params":
            if value:
                self.spinner.hide()
        elif name == "track-list":
            self.tracks = value or []
        elif name == "mute":
            self.btn_mute.setIcon(icon("volume_off" if value else "volume", "#ffffff"))

    def _on_loaded(self):
        self.spinner.hide()
        self._retries = 0

    def _on_ended(self, reason, err):
        if self._stopped_by_user or reason in ("stop", "quit", "redirect"):
            return
        if self.is_live and self.settings.get("auto_reconnect", True) and self.url and self._retries < 6:
            self._retries += 1
            self.show_toast(f"Yayın kesildi, yeniden bağlanılıyor… ({self._retries})", 2500)
            self.spinner.show()
            self.retry_timer.start(1200 * self._retries)
            return
        self.spinner.hide()
        if reason == "error":
            self.show_toast("Yayın açılamadı" + (f": {err}" if err else ""), 4000)
        elif reason == "eof" and not self.is_live:
            if self.duration:
                self.progress.emit(self.duration, self.duration)
            self.playbackEnded.emit()

    def _retry(self):
        if self.url and not self._stopped_by_user:
            self.core.load(self.url)

    # ---------------------------------------------------------- Menüler
    def _popup(self, menu, anchor):
        self.hide_timer.stop()
        pos = anchor.mapToGlobal(anchor.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height() - 6)
        menu.exec(pos)
        self.hide_timer.start()

    def _track_menu(self, kind, anchor):
        menu = QMenu(self)
        tracks = [t for t in self.tracks if t.get("type") == kind]
        if kind == "sub":
            a = menu.addAction("Kapalı")
            a.setCheckable(True)
            a.setChecked(not any(t.get("selected") for t in tracks))
            a.triggered.connect(lambda: setattr(self.core.mpv, "sid", "no"))
        if not tracks and kind == "audio":
            menu.addAction("Ses parçası yok").setEnabled(False)
        for t in tracks:
            name = t.get("title") or t.get("lang") or f"Parça {t.get('id')}"
            if t.get("lang") and t.get("title"):
                name = f"{t['title']} ({t['lang']})"
            if t.get("codec"):
                name += f"  · {t['codec']}"
            a = menu.addAction(name)
            a.setCheckable(True)
            a.setChecked(bool(t.get("selected")))
            tid = t.get("id")
            prop = "aid" if kind == "audio" else "sid"
            a.triggered.connect(lambda _=False, p=prop, i=tid: setattr(self.core.mpv, p, i))
        self._popup(menu, anchor)

    def _aspect_menu(self):
        menu = QMenu(self)
        opts = [("Otomatik", "-1", 0.0, True), ("16:9", "16:9", 0.0, True), ("4:3", "4:3", 0.0, True),
                ("21:9", "2.33", 0.0, True), ("Ekranı doldur (kırp)", "-1", 1.0, True),
                ("Uzat", "-1", 0.0, False)]
        for label, asp, pan, keep in opts:
            a = menu.addAction(label)
            a.triggered.connect(lambda _=False, x=asp, p=pan, k=keep: self._set_aspect(x, p, k))
        self._popup(menu, self.btn_aspect)

    def _set_aspect(self, asp, pan, keep):
        m = self.core.mpv
        m["video-aspect-override"] = asp
        m.panscan = pan
        m.keepaspect = keep

    def _speed_menu(self):
        menu = QMenu(self)
        for s in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            a = menu.addAction(f"{s:g}x")
            a.triggered.connect(lambda _=False, v=s: self._set_speed(v))
        self._popup(menu, self.btn_speed)

    def _set_speed(self, v):
        self.core.mpv.speed = v
        self.btn_speed.setText(f"{v:g}x")

    def toggle_record(self):
        if not self.is_live:
            return
        if not self.recording:
            from ..downloads import usable_dir  # noqa: PLC0415
            try:
                d = usable_dir(self.settings, "Kayitlar")
            except RuntimeError as e:
                self.show_toast(str(e), 4000)
                return
            name = "".join(c if c.isalnum() or c in " -_" else "_" for c in (self.lbl_title.text() or "kayit"))
            path = os.path.join(d, f"{name.strip()}_{time.strftime('%Y%m%d_%H%M%S')}.ts")
            try:
                self.core.mpv["stream-record"] = path
            except Exception as e:  # noqa: BLE001
                self.show_toast(f"Kayıt başlatılamadı: {e}")
                return
            self.recording = path
            self.lbl_rec.show()
            self.btn_rec.setIcon(icon("record", theme.DANGER))
            self.show_toast("Kayıt başladı")
            self.recordToggled.emit(True)
        else:
            try:
                self.core.mpv["stream-record"] = ""
            except Exception:  # noqa: BLE001
                pass
            path = self.recording
            self.recording = False
            self.lbl_rec.hide()
            self.btn_rec.setIcon(icon("record", "#ffffff"))
            self.show_toast("Kayıt kaydedildi → İndirilenler")
            self.last_record = path
            self.recordToggled.emit(False)

    def shutdown(self):
        self.stop()
        # libmpv, render bağlamı açıkken sonlandırılırsa abort eder; önce bağlamı serbest bırak
        self.surface._free()
        self.core.terminate()
