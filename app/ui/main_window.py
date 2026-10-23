"""Ana pencere: kenar çubuğu, sayfalar, yüzen oynatıcı ve uygulama bağlamı."""
import os
import time

from .. import cast
from ..config import APP_NAME, IS_WINDOWS, UserData
from ..downloads import DONE, FAILED, PAUSED, RESOLVING, RUNNING, DownloadManager
from ..epg import EpgService
from ..i18n import N_, _, day_name, month_name
from ..library import FAV_CAT, Library
from ..providers import EPISODE, LIVE, MOVIE, SERIES
from ..qt import (QApplication, QButtonGroup, QDialog, QEasingCurve, QFrame, QGraphicsOpacityEffect, QGridLayout,
                  QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPropertyAnimation, QPushButton,
                  QSize, QStackedWidget, Qt, QTimer, QVBoxLayout, QWidget)
from ..tasks import run_async
from . import theme
from .downloads_page import DownloadsPage
from .guide_page import GuidePage
from .icons import icon
from .live_page import LivePage
from .login import ProfileForm, WelcomePage
from .player import PlayerWidget
from .search_page import SearchPage
from .settings_page import SettingsPage
from .vod_page import VodPage
from .widgets import ChannelDelegate, OnScreenKeyboard

NAV = [("live", N_("Canlı TV")), ("series", N_("Diziler")), ("movie", N_("Filmler")), ("search", N_("Ara")),
       ("download", N_("İndirilenler")), ("menu", N_("Menü"))]
# Kenar çubuğu sırasıyla aynı sayfa sıraları; rehber kenar çubuğunda yok (Canlı TV'den açılır)
PAGE_LIVE, PAGE_SERIES, PAGE_MOVIES, PAGE_SEARCH, PAGE_DOWNLOADS, PAGE_MENU, PAGE_GUIDE = range(7)


class PinDialog(QDialog):
    """Dokunmatik ekrana uygun PIN tuş takımı."""

    def __init__(self, parent=None, title=None):
        super().__init__(parent)
        title = title or _("PIN girin")
        self.setWindowTitle(title)
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        t = QLabel(title)
        t.setObjectName("H2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setStyleSheet(theme.scaled("font-size:22px; letter-spacing:8px;"))
        self.edit.returnPressed.connect(self.accept)
        lay.addWidget(self.edit)
        g = QGridLayout()
        g.setSpacing(6)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓"]
        for i, k in enumerate(keys):
            b = QPushButton(k)
            b.setObjectName("Primary" if k == "✓" else "Key")
            b.setMinimumSize(64, 48)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if k == "⌫":
                b.clicked.connect(self.edit.backspace)
            elif k == "✓":
                b.clicked.connect(self.accept)
            else:
                b.clicked.connect(lambda _=False, x=k: self.edit.insert(x))
            g.addWidget(b, i // 3, i % 3)
        lay.addLayout(g)
        self.edit.setFocus()

    def value(self):
        return self.edit.text().strip()


class Sidebar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(10, 14, 10, 12)
        self.v.setSpacing(4)
        self.brand = QLabel("ONR<span style='color:#e6e9ec;font-weight:300'> IPTV</span>")
        self.brand.setObjectName("Brand")
        self.brand_small = QLabel("ONR")
        self.brand_small.setObjectName("Brand")
        self.brand_small.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.v.addWidget(self.brand)
        self.v.addWidget(self.brand_small)
        self.v.addSpacing(14)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for i, (ic, label) in enumerate(NAV):
            label = _(label)
            b = QPushButton("  " + label)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setIcon(icon(ic, theme.MUTED, theme.ACCENT, 22))
            b.setIconSize(QSize(22, 22))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(label)
            b._label = label
            self.group.addButton(b, i)
            self.buttons.append(b)
            self.v.addWidget(b)
        self.v.addStretch(1)
        self.clock = QLabel()
        self.clock.setObjectName("Clock")
        self.date = QLabel()
        self.date.setObjectName("SideInfo")
        self.profile = QLabel()
        self.profile.setObjectName("SideInfo")
        self.profile.setWordWrap(True)
        self.v.addWidget(self.clock)
        self.v.addWidget(self.date)
        self.v.addSpacing(4)
        self.v.addWidget(self.profile)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(10000)
        self._tick()
        self.set_compact(False)

    def _tick(self):
        lt = time.localtime()
        self.clock.setText(time.strftime("%H:%M", lt))
        self.date.setText(_("{day} {month} {weekday}", day=lt.tm_mday, month=month_name(lt), weekday=day_name(lt)))

    def set_compact(self, compact):
        self.compact = compact
        k = max(1.0, theme.SCALE)  # büyük yazıda kenar çubuğu da genişler
        self.setFixedWidth(round(68 * k) if compact else round(176 * (1 + (k - 1) * 0.7)))
        self.brand.setVisible(not compact)
        self.brand_small.setVisible(compact)
        for b in self.buttons:
            b.setText("" if compact else "  " + b._label)
            b.setStyleSheet("padding:0; text-align:center;" if compact else "")
        self.date.setVisible(not compact)
        self.profile.setVisible(not compact)
        self.clock.setStyleSheet(theme.scaled("font-size:16px;") if compact else "")


class AppContext:
    """Sayfaların paylaştığı durum ve servisler."""

    def __init__(self, win, settings):
        self.win = win
        self.settings = settings
        self.userdata = None
        self.library = None
        self.epg = EpgService()
        self.downloads = DownloadManager(settings)
        self.player = None
        self.playing_id = None
        self.show_epg = bool(settings.get("show_epg_in_list", True))
        self._unlocked_until = 0

    UNLOCK_SECS = 5 * 60  # doğru PIN'den sonra korumalı içerik bu süre boyunca açık kalır

    def ask_pin(self, parent=None, force=False):
        """force: PIN değiştirme gibi işlemlerde 5 dakikalık açık kalma süresini yok sayar."""
        pin = self.settings.get("parental_pin")
        if not pin:
            return True
        if not force and time.time() < self._unlocked_until:
            return True
        dlg = PinDialog(parent or self.win)
        if dlg.exec() and dlg.value() == pin:
            self._unlocked_until = time.time() + self.UNLOCK_SECS
            return True
        if dlg.result():
            self.win.toast(_("PIN hatalı"))
        return False

    def can_open(self, section, item, parent=None):
        """Kilitli içerik ise PIN ister."""
        lib = self.library
        if lib is not None and lib.item_locked(section, item):
            return self.ask_pin(parent)
        return True

    def animate_switch(self, stack, idx):
        if stack.currentIndex() == idx:
            return
        stack.setCurrentIndex(idx)
        if not self.settings.get("animations", True):
            return
        w = stack.currentWidget()
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(170)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def player_playing(self, item_id):
        return self.player is not None and self.playing_id == item_id and bool(self.player.url)

    def update_player_epg(self, item, cur, nxt):
        if self.player and self.player.is_live and self.playing_id == item.id:
            self.player.set_epg(cur, nxt)

    def favorites_changed(self):
        self.win.on_favorites_changed()

    def apply_setting(self, key):
        self.win.apply_setting(key)


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(800, 480)
        self.ctx = AppContext(self, settings)

        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        self.central = central
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.root_stack = QStackedWidget()
        cv.addWidget(self.root_stack, 1)
        self.osk = OnScreenKeyboard()
        cv.addWidget(self.osk)

        # 0: karşılama
        self.welcome = WelcomePage(settings)
        self.welcome.saved.connect(self._welcome_saved)
        self.root_stack.addWidget(self.welcome)

        # 1: ana arayüz
        main = QWidget()
        mh = QHBoxLayout(main)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.set_compact(bool(settings.get("sidebar_compact")))
        self.sidebar.group.idClicked.connect(self.navigate)
        mh.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        mh.addWidget(self.pages, 1)
        self.root_stack.addWidget(main)

        # 2: profil düzenleyici (dokunmatik klavye ile çalışabilmesi için pencere içinde)
        self.editor_host = QWidget()
        self.editor_host.setObjectName("Page")
        self.editor_lay = QVBoxLayout(self.editor_host)
        self.editor_lay.setContentsMargins(40, 20, 40, 20)
        self.root_stack.addWidget(self.editor_host)
        self.editor = None

        # 3: çoklu ekran (yalnızca Windows; ilk açılışta oluşturulur)
        self.multiview = None

        self.live = LivePage(self.ctx)
        self.series = VodPage(self.ctx, SERIES)
        self.movies = VodPage(self.ctx, MOVIE)
        self.search_page = SearchPage(self.ctx)
        self.dl_page = DownloadsPage(self.ctx)
        self.menu = SettingsPage(self.ctx)
        self.guide = GuidePage(self.ctx)
        for p in (self.live, self.series, self.movies, self.search_page, self.dl_page, self.menu, self.guide):
            self.pages.addWidget(p)

        # Yüzen oynatıcı
        self.player = PlayerWidget(settings, central)
        self.ctx.player = self.player
        self.drawer_delegate = ChannelDelegate(self.ctx, compact=True)
        self.player.set_drawer_model(self.live.model, self.drawer_delegate)
        self.player.exitRequested.connect(self.exit_player)
        self.player.fullRequested.connect(lambda: self.set_player_mode("full"))
        self.player.channelStep.connect(self._channel_step)
        self.player.channelPicked.connect(lambda it: (self.live.select(it, play=False), self.play_live(it, True)))
        self.restart_requested = False
        self.player.favoriteToggled.connect(self._player_fav)
        self.player.progress.connect(self._on_progress)
        self.player.playbackEnded.connect(self._on_ended)
        self.player.recordToggled.connect(self._on_record)
        self.player.windowFullscreenToggled.connect(self.toggle_fullscreen)
        self.player.castRequested.connect(self.cast_menu)
        self.caster = cast.CastManager()
        self.caster.devicesFound.connect(self._cast_devices)
        self.caster.started.connect(self._cast_started)
        self.caster.failed.connect(lambda e: self.player.show_toast(_("Chromecast hatası: {err}", err=e), 4000))
        self.caster.stopped.connect(lambda: self.player.set_casting(""))
        self._cast_anchor = None
        self.live.guideRequested.connect(self.show_guide)
        self.live.multiviewRequested.connect(self.open_multiview)
        self.guide.back.connect(lambda: self.navigate(PAGE_LIVE))
        self.guide.playChannel.connect(self._guide_play)
        self.guide.catchup.connect(self.play_catchup)
        self.search_page.channelPicked.connect(self._search_channel)
        self.search_page.vodPicked.connect(self._search_vod)
        self.live.preview.geometryChanged.connect(self._place_player)
        self.live.playRequested.connect(self.play_live)
        self.live.catchupRequested.connect(self.play_catchup)
        for vp in (self.series, self.movies):
            vp.playRequested.connect(self.play_vod)
            vp.downloadRequested.connect(self.download)
        self.dl_page.playFile.connect(self.play_file)
        self.menu.profileSwitch.connect(self.switch_profile)
        self.menu.profileAdd.connect(lambda: self.open_editor(None))
        self.menu.profileEdit.connect(lambda pid: self.open_editor(next((p for p in settings.profiles if p["id"] == pid), None)))
        self.menu.profileDelete.connect(self.delete_profile)
        self.menu.refreshRequested.connect(self.refresh_library)
        self.menu.categoriesChanged.connect(self._categories_changed)
        self.menu.quitRequested.connect(self.close)

        self.ctx.epg.updated.connect(self._epg_updated)
        QApplication.instance().focusChanged.connect(self._focus_changed)

        self.mode = "hidden"
        self.play_ctx = {}
        self._fs_by_player = False
        self._toast = QLabel(central)
        self._toast.setObjectName("OsdToast")
        self._toast.hide()
        self._toast_t = QTimer(self)
        self._toast_t.setSingleShot(True)
        self._toast_t.timeout.connect(self._toast.hide)

        prof = settings.active_profile()
        if prof:
            self.load_profile(prof)
        else:
            self.root_stack.setCurrentIndex(0)

    # ------------------------------------------------------------ Profiller
    def _welcome_saved(self, p):
        p = self.settings.upsert_profile(p)
        self.settings.set_active(p["id"])
        self.load_profile(p)

    def load_profile(self, p):
        self.stop_player()
        if self.ctx.library is not None:
            try:
                self.ctx.library.deleteLater()
            except RuntimeError:
                pass
        self.ctx.userdata = UserData(p["id"])
        lib = Library(p, self.settings)
        self.ctx.library = lib
        self.ctx.epg.set_provider(lib.provider)
        lib.account_ready.connect(self.menu.set_account)
        lib.section_ready.connect(lambda s: self.menu.set_account(lib.account))
        for page in (self.live, self.series, self.movies):
            page.set_library(lib)
        self.sidebar.profile.setText(p.get("name", ""))
        self.root_stack.setCurrentIndex(1)
        self.navigate(0)
        self.menu.refresh()
        lib.start()

    def switch_profile(self, pid):
        p = next((x for x in self.settings.profiles if x["id"] == pid), None)
        if p:
            self.settings.set_active(pid)
            self.load_profile(p)
            self.toast(_("Profil: {name}", name=p["name"]))

    def delete_profile(self, pid):
        was_active = self.ctx.library and self.ctx.library.pid == pid
        self.settings.remove_profile(pid)
        try:
            os.remove(os.path.join(os.path.dirname(self.settings.path), f"user_{pid}.json"))
        except OSError:
            pass
        if was_active:
            nxt = self.settings.active_profile()
            if nxt:
                self.load_profile(nxt)
            else:
                self.stop_player()
                self.ctx.library = None
                self.root_stack.setCurrentIndex(0)
        self.menu.refresh()

    def open_editor(self, profile):
        if self.editor is not None:
            self.editor.deleteLater()
        title = QLabel(_("Profili düzenle") if profile else _("Yeni profil ekle"))
        title.setObjectName("Title")
        self.editor = QWidget()
        v = QVBoxLayout(self.editor)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(title)
        form = ProfileForm(self.settings, profile, show_cancel=True)
        form.saved.connect(self._editor_saved)
        form.cancelled.connect(lambda: self.root_stack.setCurrentIndex(1))
        v.addWidget(form)
        v.addStretch(1)
        while self.editor_lay.count():
            self.editor_lay.takeAt(0)
        self.editor_lay.addWidget(self.editor)
        self.stop_player()
        self.root_stack.setCurrentIndex(2)

    def _editor_saved(self, p):
        p = self.settings.upsert_profile(p)
        self.settings.set_active(p["id"])
        self.load_profile(p)
        self.navigate(PAGE_MENU)

    def refresh_library(self):
        if self.ctx.library:
            self.ctx.library.refresh(silent=True)
            self.ctx.epg.set_provider(self.ctx.library.provider)
            self.toast(_("Liste yenileniyor…"))

    def _categories_changed(self):
        lib = self.ctx.library
        if lib:
            for s in (LIVE, MOVIE, SERIES):
                if lib.state[s] == "ready":
                    lib.section_ready.emit(s)

    # ------------------------------------------------------------ Gezinme
    def navigate(self, idx):
        self.sidebar.buttons[idx].setChecked(True)
        if self.pages.currentIndex() == idx:
            if idx in (1, 2):
                page = self.pages.widget(idx)
                if page.stack.currentIndex() == 1:
                    page.close_detail()
            return
        if idx != 0 and self.mode == "preview":
            self.stop_player()
        self.ctx.animate_switch(self.pages, idx)
        if idx == PAGE_MENU:
            self.menu.refresh()
        if idx == 0 and self.player.url and self.play_ctx.get("kind") == LIVE:
            self.set_player_mode("preview")
        QTimer.singleShot(0, self._place_player)

    def set_player_mode(self, mode):
        self.mode = mode
        if mode == "full" and self.settings.get("osk_enabled"):
            self.osk.hide()
        self.player.set_mode(mode)
        self._place_player()

    def _place_player(self):
        if self.mode == "full":
            r = self.root_stack.geometry()
            self.player.setGeometry(r)
            self.player.raise_()
        elif self.mode == "preview":
            box = self.live.preview
            if self.pages.currentWidget() is self.live and box.isVisible() and self.root_stack.currentIndex() == 1:
                tl = box.mapTo(self.central, box.rect().topLeft())
                self.player.setGeometry(tl.x(), tl.y(), box.width(), box.height())
                self.player.show()
                self.player.raise_()
            else:
                self.player.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._place_player)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self._fs_by_player = False
        else:
            self.showFullScreen()
            self._fs_by_player = self.mode == "full"

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif k == Qt.Key.Key_Escape:
            page = self.pages.currentWidget()
            if page in (self.series, self.movies) and page.stack.currentIndex() == 1:
                page.close_detail()
            elif page is self.guide:
                self.navigate(PAGE_LIVE)
            elif self.isFullScreen() and not self.settings.get("start_fullscreen"):
                self.showNormal()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ Oynatma
    def _headers(self, item=None):
        h = dict(self.ctx.library.provider.http_headers()) if self.ctx.library else {}
        if item is not None:
            if item.extra.get("ua"):
                h["User-Agent"] = item.extra["ua"]
            if item.extra.get("referrer"):
                h["Referer"] = item.extra["referrer"]
        return h

    def _resolve_and_play(self, item, cb_fail_msg=None):
        """Sağlayıcıdan URL alır (Stalker'da ağ isteği gerekir) ve geri çağrıya verir."""
        prov = self.ctx.library.provider
        token = object()
        self._resolve_token = token

        def done(url):
            if self._resolve_token is token and self.play_ctx.get("item") is item:
                self._start(url, item)

        def fail(e):
            if self._resolve_token is token:
                self.player.spinner.hide()
                self.player.show_toast(f"{cb_fail_msg or _('Yayın açılamadı')}: {e}", 4000)

        if prov.kind == "stalker":
            self.player.spinner.show()
            run_async(prov.stream_url, item, on_done=done, on_error=fail)
        else:
            try:
                done(prov.stream_url(item))
            except Exception as e:  # noqa: BLE001
                fail(e)

    def _start(self, url, item):
        c = self.play_ctx
        self.player.play(url, item, c.get("title", item.name), c.get("subtitle", ""), live=c["kind"] == LIVE,
                         start=c.get("start", 0), headers=self._headers(item))

    def play_live(self, item, full=False):
        if not self.ctx.library:
            return
        same = self.play_ctx.get("kind") == LIVE and self.play_ctx.get("item") is not None \
            and self.play_ctx["item"].id == item.id and self.player.url
        if not same and not self.ctx.can_open(LIVE, item):
            return
        self.ctx.playing_id = item.id
        self.ctx.userdata.add_history(LIVE, item.brief())
        self.player.set_favorite(self.ctx.userdata.is_favorite(LIVE, item.id))
        self.set_player_mode("full" if full else ("preview" if self.pages.currentWidget() is self.live else "full"))
        if not same:
            self.play_ctx = {"kind": LIVE, "item": item, "title": item.name, "subtitle": ""}
            self._resolve_and_play(item)
            cur, nxt = self.ctx.epg.now_next(item)
            self.player.set_epg(cur, nxt)
            if self.player.mode == "full":
                self.player.show_toast(f"{item.num or ''}  {item.name}".strip(), 1500)
        self.live.view.viewport().update()
        row = self.live.model.row_of(item.id)
        if row >= 0:
            self.player.drawer_list.setCurrentIndex(self.live.model.index(row))

    def _channel_step(self, d):
        it = self.live.step(d)
        if it:
            self.play_live(it, self.mode == "full")

    def play_catchup(self, item, prog):
        if not self.ctx.can_open(LIVE, item):
            return
        url = self.ctx.library.provider.catchup_url(item, prog)
        if not url:
            self.toast(_("Bu program için arşiv yok"))
            return
        t = time.strftime("%d.%m %H:%M", time.localtime(prog["start"]))
        self.play_ctx = {"kind": "catchup", "item": item, "title": f"{item.name} · {prog['title']}",
                         "subtitle": _("Geçmiş yayın · {time}", time=t)}
        self.ctx.playing_id = None
        self.player.set_favorite(None)
        self.set_player_mode("full")
        self.player.play(url, item, self.play_ctx["title"], self.play_ctx["subtitle"], live=False,
                         headers=self._headers(item))

    def play_vod(self, item, start=0, series=None):
        if not self.ctx.library:
            return
        if not self.ctx.can_open(SERIES if item.kind == EPISODE else MOVIE,
                                 series if item.kind == EPISODE and series is not None else item):
            return
        if item.kind == EPISODE:
            key = f"episode:{item.id}"
            sname = item.extra.get("series_name") or (series.name if series else "")
            title = f"{sname}"
            sub = _("Sezon {s} · Bölüm {e}", s=item.extra.get("season", 1),
                    e=item.extra.get("episode", item.num)) + f" — {item.name}"
            hist_kind, hist_item = SERIES, series
        else:
            key = f"movie:{item.id}"
            title, sub = item.name, item.year
            hist_kind, hist_item = MOVIE, item
        self.ctx.playing_id = None
        self.play_ctx = {"kind": item.kind, "item": item, "key": key, "series": series, "title": title,
                         "subtitle": sub, "start": start}
        if hist_item is not None:
            self.ctx.userdata.add_history(hist_kind, hist_item.brief())
        if series is not None:
            self._set_series_last(series.id, item.id)
        fav_kind, fav_item = (SERIES, series) if item.kind == EPISODE else (MOVIE, item)
        self.player.set_favorite(self.ctx.userdata.is_favorite(fav_kind, fav_item.id) if fav_item else None)
        self.set_player_mode("full")
        t = self.ctx.downloads.find_by_item(key)
        if t and t["status"] == DONE:
            if os.path.exists(t["path"]):
                self.player.play(t["path"], item, title, sub + "  · " + _("İndirilen"), live=False, start=start)
                return
            self.ctx.downloads.prune_missing()
        self._resolve_and_play(item)

    def play_file(self, path, title, key=""):
        """İndirilenler sayfasından oynatma; key varsa (movie:/episode:/local:) kaldığı yerden devam eder."""
        prog = self.ctx.userdata.get_progress(key) if key and self.ctx.userdata else None
        start = int(prog["pos"]) if prog and prog.get("pos", 0) > 30 else 0
        self.play_ctx = {"kind": "file", "item": None, "title": title, "key": key or None}
        self.ctx.playing_id = None
        self.player.set_favorite(None)
        self.set_player_mode("full")
        self.player.play(path, None, title, _("Yerel dosya"), live=False, start=start)

    def _set_series_last(self, sid, ep_id):
        self.ctx.userdata.progress[f"series:{sid}"] = {"ep": ep_id, "ts": int(time.time())}
        self.ctx.userdata.save()

    def _on_progress(self, pos, dur):
        key = self.play_ctx.get("key")
        if key and self.ctx.userdata:
            self.ctx.userdata.set_progress(key, pos, dur)

    def _on_ended(self):
        c = self.play_ctx
        if c.get("kind") == EPISODE and c.get("series") is not None:
            nxt = self.series.detail.next_episode(c["item"])
            if nxt:
                self.player.show_toast(_("Sonraki bölüm başlıyor…"), 2000)
                QTimer.singleShot(1200, lambda: self.play_vod(nxt, 0, c["series"]))
                return
        self.exit_player()

    def _fav_target(self):
        """Oynatılan içerik için (favori türü, öğe); bölümde dizinin kendisi favorilenir."""
        c = self.play_ctx
        kind, it = c.get("kind"), c.get("item")
        if kind == LIVE and it is not None:
            return LIVE, it
        if kind == MOVIE and it is not None:
            return MOVIE, it
        if kind == EPISODE and c.get("series") is not None:
            return SERIES, c["series"]
        return None, None

    def _player_fav(self):
        kind, it = self._fav_target()
        if it is None or not self.ctx.userdata:
            return
        fav = self.ctx.userdata.toggle_favorite(kind, it.id, it.brief())
        self.player.set_favorite(fav)
        self.player.show_toast(_("Favorilere eklendi") if fav else _("Favorilerden çıkarıldı"), 1200)
        self.on_favorites_changed()

    def on_favorites_changed(self):
        self.live.view.viewport().update()
        if self.live.category == FAV_CAT:
            self.live.apply(keep_scroll=True)
        for vp in (self.series, self.movies):
            vp.on_favorites_changed()
        kind, it = self._fav_target()
        if it is not None:
            self.player.set_favorite(self.ctx.userdata.is_favorite(kind, it.id))

    def _on_record(self, started):
        if not started and getattr(self.player, "last_record", None):
            path = self.player.last_record
            QTimer.singleShot(800, lambda: os.path.exists(path) and self.ctx.downloads.add_local(
                _("Kayıt") + f" · {os.path.basename(path)}", path))

    def exit_player(self):
        c = self.play_ctx
        if self.player.position and self.player.duration and c.get("key"):
            self.ctx.userdata.set_progress(c["key"], self.player.position, self.player.duration, flush=True)
        if self._fs_by_player and self.isFullScreen() and not self.settings.get("start_fullscreen"):
            self.showNormal()
        self._fs_by_player = False
        if c.get("kind") == LIVE:
            if self.pages.currentWidget() is not self.live:
                self.navigate(0)
            self.set_player_mode("preview")
            self.live.select(c["item"], play=False)
            return
        self.stop_player()
        for vp in (self.series, self.movies):
            vp.refresh_state()
        if self.pages.currentWidget() is self.dl_page:
            self.dl_page.rebuild()  # izlenme durumu değişmiş olabilir

    def stop_player(self):
        if self.caster.active:
            self.caster.stop()
        if self.player.url:
            self.player.stop()
        self.ctx.playing_id = None
        self.play_ctx = {}
        self.set_player_mode("hidden")
        self.live.view.viewport().update()

    def _epg_updated(self):
        it = self.play_ctx.get("item")
        if it is not None and self.play_ctx.get("kind") == LIVE:
            cur, nxt = self.ctx.epg.now_next(it, fetch=False)
            self.player.set_epg(cur, nxt)
            if self.live.current is not None and self.live.current.id == it.id:
                self.live._refresh_info()
        if self.player.drawer.isVisible():
            self.player.drawer_list.viewport().update()

    # ------------------------------------------------------------ Ebeveyn kilidi
    def toggle_lock(self, section, item):
        lib = self.ctx.library
        if lib is None:
            return
        if not self.settings.get("parental_pin"):
            QMessageBox.information(self, _("PIN gerekli"), _("Önce Menü → Ebeveyn kontrolü bölümünden bir PIN belirleyin."))
            return
        if not self.ctx.ask_pin(self):
            return
        locked = lib.toggle_item_lock(section, item.id)
        self.toast(_("{name} kilitlendi", name=item.name) if locked else _("{name} kilidi kaldırıldı", name=item.name))
        self.live.view.viewport().update()
        self.series.grid.viewport().update()
        self.movies.grid.viewport().update()

    # ------------------------------------------------------------ Rehber ve arama
    def show_guide(self):
        if self.mode == "preview":
            self.stop_player()
        self.sidebar.buttons[PAGE_LIVE].setChecked(True)
        label = self.live.chips.buttons.get(self.live.category)
        self.guide.open(self.live.model.items, label.text() if label else "")
        self.ctx.animate_switch(self.pages, PAGE_GUIDE)

    def _guide_play(self, item):
        self.live.select(item, play=False)
        self.play_live(item, True)

    def _search_channel(self, item):
        self.navigate(PAGE_LIVE)
        self.live.select(item, play=False)
        self.play_live(item, True)

    def _search_vod(self, kind, item):
        page = self.movies if kind == MOVIE else self.series
        self.navigate(PAGE_MOVIES if kind == MOVIE else PAGE_SERIES)
        page.open_detail(item)

    # ------------------------------------------------------------ Çoklu ekran
    def connection_limit(self):
        """(kullanılabilir bağlantı, sağlayıcı sınırı biliniyor mu). Süren indirmeler de bağlantı harcar."""
        acc = (self.ctx.library.account if self.ctx.library else None) or {}
        try:
            mx = int(str(acc.get("max_connections") or "0").strip() or 0)
        except ValueError:
            mx = 0
        busy = sum(1 for t in self.ctx.downloads.tasks if t["status"] in (RUNNING, RESOLVING))
        if mx > 0:
            return min(4, mx - busy), True
        return 4, False

    def open_multiview(self, item=None):
        if not IS_WINDOWS or not self.ctx.library:
            return
        limit, known = self.connection_limit()
        if limit < 2:
            msg = _("Sağlayıcınız aynı anda yalnızca {n} bağlantıya izin veriyor; çoklu ekran kullanılamaz.",
                    n=max(1, limit + sum(1 for t in self.ctx.downloads.tasks if t["status"] in (RUNNING, RESOLVING))))
            if limit < 1 or any(t["status"] in (RUNNING, RESOLVING) for t in self.ctx.downloads.tasks):
                msg += "\n" + _("Süren indirmeler de bağlantı kullanır.")
            QMessageBox.information(self, _("Çoklu ekran"), msg)
            return
        if item is not None and not self.ctx.can_open(LIVE, item):
            return
        if self.multiview is None:
            from .multiview import MultiViewPage  # noqa: PLC0415
            self.multiview = MultiViewPage(self.ctx, self._headers)
            self.multiview.back.connect(self.close_multiview)
            self.root_stack.addWidget(self.multiview)
        self.stop_player()  # oynatıcının bağlantısını serbest bırak
        self.root_stack.setCurrentWidget(self.multiview)
        self.multiview.open(limit, known, item)
        self.multiview.setFocus()

    def close_multiview(self):
        if self.multiview is not None:
            self.multiview.close_all()
        self.root_stack.setCurrentIndex(1)
        self.navigate(PAGE_LIVE)

    # ------------------------------------------------------------ Chromecast
    def cast_menu(self, anchor):
        self._cast_anchor = anchor
        if self.caster.active:
            m = QMenu(self)
            a_stop = m.addAction(icon("close"), _("TV'de oynatmayı durdur ({name})", name=self.caster.device_name))
            a_other = m.addAction(icon("cast"), _("Başka cihaz seç…"))
            act = self._popup(m, anchor)
            if act is a_stop:
                self.caster.stop()
                if self.player.paused:
                    self.player.toggle_pause()  # yerel oynatmaya devam
            elif act is a_other:
                self.player.show_toast(_("Chromecast cihazları aranıyor…"), 5000)
                self.caster.discover()
            return
        self.player.show_toast(_("Chromecast cihazları aranıyor…"), 5000)
        self.caster.discover()

    def _popup(self, menu, anchor):
        self.player.hide_timer.stop()
        pos = anchor.mapToGlobal(anchor.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height() - 6)
        act = menu.exec(pos)
        self.player.hide_timer.start()
        return act

    def _cast_devices(self, devices):
        self.player.toast.hide()
        if self.mode != "full" or not self.player.url or self._cast_anchor is None:
            return
        if not devices:
            self.player.show_toast(_("Ağda Chromecast bulunamadı"), 3000)
            return
        m = QMenu(self)
        acts = [m.addAction(icon("tv"), f"{name}  ·  {model}" if model else name) for name, model in devices]
        act = self._popup(m, self._cast_anchor)
        if act in acts:
            self._cast_to(acts.index(act))

    def _cast_to(self, index):
        url = self.player.url
        live = self.player.is_live
        prov = self.ctx.library.provider if self.ctx.library else None
        # Varsayılan Chromecast alıcısı ham MPEG-TS oynatmaz; Xtream canlı yayında HLS adresi kullanılır
        if live and prov is not None and prov.kind == "xtream" and url.lower().split("?")[0].endswith(".ts"):
            url = url[: url.lower().rfind(".ts")] + ".m3u8"
        self.player.show_toast(_("Chromecast'e bağlanılıyor…"), 4000)
        self.caster.cast(index, url, self.player.lbl_title.text(), live=live, start=int(self.player.position or 0))

    def _cast_started(self, name):
        if not self.player.paused:
            self.player.toggle_pause()  # yerel oynatma duraklatılır
        self.player.set_casting(name)
        self.player.show_toast(_("{name} cihazında oynatılıyor", name=name), 3000)

    # ------------------------------------------------------------ İndirme
    def download(self, item, series=None):
        if not self.ctx.library:
            return
        prov = self.ctx.library.provider
        if item.kind == EPISODE:
            key = f"episode:{item.id}"
            sname = item.extra.get("series_name") or (series.name if series else _("Dizi"))
            title = f"{sname} S{int(item.extra.get('season', 1)):02d}E{int(item.extra.get('episode', item.num) or 0):02d}"
            if item.name and not item.name.lower().startswith(("bölüm", "episode")):
                title += f" - {item.name}"
            folder = sname
            poster = (series.logo if series else "") or item.logo
        else:
            key = f"movie:{item.id}"
            title = item.name
            folder = ""
            poster = item.logo
        existing = self.ctx.downloads.find_by_item(key)
        if existing and existing["status"] == DONE:
            self.toast(_("Bu içerik zaten indirildi"))
            return
        if existing and existing["status"] == PAUSED:
            self.ctx.downloads.resume(existing["id"])
            self.toast(_("İndirme sürdürülüyor → İndirilenler"))
            return
        if existing and existing["status"] != FAILED:
            self.toast(_("Bu içerik zaten indiriliyor → İndirilenler"))
            return
        self.ctx.downloads.add(title, key, lambda: prov.stream_url(item), item.ext or "mp4", poster,
                               {"kind": item.kind}, folder)
        self.toast(_("İndirme başladı → İndirilenler"))

    # ------------------------------------------------------------ Yardımcılar
    def toast(self, text, ms=2200):
        self._toast.setText(text)
        self._toast.adjustSize()
        self._toast.move((self.central.width() - self._toast.width()) // 2, self.central.height() - self._toast.height() - 30)
        self._toast.show()
        self._toast.raise_()
        self._toast_t.start(ms)

    def _focus_changed(self, old, new):
        if not self.settings.get("osk_enabled"):
            return
        if isinstance(new, QLineEdit) and self.isAncestorOf(new):
            self.osk.attach(new)
            QTimer.singleShot(0, self._place_player)
        elif new is not None and not self.osk.isAncestorOf(new) and not isinstance(new, QLineEdit):
            if self.osk.isVisible():
                self.osk.hide()
                QTimer.singleShot(0, self._place_player)

    def apply_setting(self, key):
        s = self.settings
        if key == "sidebar_compact":
            self.sidebar.set_compact(bool(s.get(key)))
            QTimer.singleShot(0, self._place_player)
        elif key == "show_epg_in_list":
            self.ctx.show_epg = bool(s.get(key))
            self.live.view.viewport().update()
        elif key == "osk_enabled" and not s.get(key):
            self.osk.hide()
        elif key == "start_fullscreen":
            if s.get(key):
                self.showFullScreen()
            else:
                self.showNormal()
        elif key == "touch_scroll":
            self.toast(_("Kaydırma ayarı yeniden başlatınca uygulanır"))

    def restart_app(self):
        """Dil / yazı boyutu gibi tüm arayüzü etkileyen ayarlar için uygulamayı yeniden başlatır."""
        self.restart_requested = True
        self.close()

    def closeEvent(self, e):
        c = self.play_ctx
        if self.player.position and self.player.duration and c.get("key") and self.ctx.userdata:
            self.ctx.userdata.set_progress(c["key"], self.player.position, self.player.duration, flush=True)
        self.ctx.downloads.stop_all()
        self.settings.save()
        self.caster.shutdown()
        if self.multiview is not None:
            self.multiview.shutdown()
        self.player.shutdown()
        super().closeEvent(e)
