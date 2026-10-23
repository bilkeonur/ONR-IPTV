"""Filmler ve Diziler: poster ızgarası, detay ekranı, sezon/bölüm listesi."""
from ..downloads import DONE, FAILED, PAUSED, QUEUED, RESOLVING, RUNNING
from ..i18n import N_, _
from ..images import loader
from ..library import ALL_CAT, FAV_CAT, RECENT_CAT
from ..providers import EPISODE, MOVIE, SERIES
from ..qt import (QButtonGroup, QColor, QComboBox, QFrame, QHBoxLayout, QLabel, QLinearGradient, QMenu,
                  QMessageBox, QPainter, QPainterPath, QProgressBar, QPushButton, QRectF, QScrollArea, QSize,
                  QStackedWidget, Qt, QToolButton, QVBoxLayout, QWidget, Signal)
from ..tasks import run_async
from . import theme
from .icons import icon
from .player import Spinner, fmt_time
from .widgets import (GridView, ItemModel, ItemRole, LangFilterBox, PosterDelegate, SearchBox, StatusView,
                      enable_kinetic)

SORTS = [("default", N_("Varsayılan")), ("new", N_("Son eklenen")), ("az", "A → Z"), ("za", "Z → A"),
         ("rating", N_("Puan")), ("year", N_("Yıl"))]


def dl_percent(t):
    total = t.get("total") or 0
    return int((t.get("done") or 0) / total * 100) if total else 0


class PosterLabel(QWidget):
    """Yuvarlatılmış köşeli poster."""

    def __init__(self, w=200, h=300, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self.url = ""
        self.tint = theme.ACCENT  # görsel yokken çizilen simgenin rengi
        loader().loaded.connect(self.update)

    def set_url(self, url):
        self.url = url or ""
        self.update()

    def set_tint(self, color):
        if color != self.tint:
            self.tint = color
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor(theme.SURFACE2))
        pm = loader().get(self.url, self.width() * 2, self.height() * 2) if self.url else None
        if pm:
            iw, ih = pm.width() / 2, pm.height() / 2
            s = max(self.width() / max(iw, 1), self.height() / max(ih, 1))
            w, h = int(iw * s), int(ih * s)
            p.drawPixmap((self.width() - w) // 2, (self.height() - h) // 2, w, h, pm)
        else:
            c = QColor(self.tint)
            c.setAlpha(130)
            p.setPen(c)
            f = p.font()
            f.setPixelSize(theme.fs(40))
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▶")


class Backdrop(QWidget):
    """Detay ekranı arka planı: bulanık hissi veren karartılmış görsel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = ""
        loader().loaded.connect(self.update)

    def set_url(self, url):
        self.url = url or ""
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        pm = loader().get(self.url, 640, 360) if self.url else None
        if pm:
            s = max(self.width() / max(pm.width(), 1), self.height() / max(pm.height(), 1))
            w, h = int(pm.width() * s), int(pm.height() * s)
            p.setOpacity(0.28)
            p.drawPixmap((self.width() - w) // 2, 0, w, h, pm)
            p.setOpacity(1.0)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(14, 16, 18, 120))
        g.setColorAt(0.55, QColor(14, 16, 18, 235))
        g.setColorAt(1, QColor(14, 16, 18, 255))
        p.fillRect(self.rect(), g)
        g2 = QLinearGradient(0, 0, self.width(), 0)
        g2.setColorAt(0, QColor(14, 16, 18, 230))
        g2.setColorAt(0.6, QColor(14, 16, 18, 60))
        g2.setColorAt(1, QColor(14, 16, 18, 0))
        p.fillRect(self.rect(), g2)


class EpisodeRow(QFrame):
    play = Signal(object)
    download = Signal(object)

    def __init__(self, ep, progress=None, dl_task=None, watched=False, parent=None):
        super().__init__(parent)
        self.ep = ep
        self.setObjectName("Panel")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(10)
        num = QLabel(f"{ep.extra.get('episode') or ep.num}")
        num.setFixedWidth(30)
        num.setStyleSheet(theme.scaled(f"font-size:19px;font-weight:800;color:{theme.ACCENT};"))
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(num)
        col = QVBoxLayout()
        col.setSpacing(2)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        t = QLabel(ep.name)
        t.setStyleSheet(theme.scaled("font-weight:700;font-size:14px;" + (f"color:{theme.MUTED};" if watched else "")))
        trow.addWidget(t)
        if watched:
            w = QLabel("✓ " + _("İzlendi"))
            w.setObjectName("Badge")
            trow.addWidget(w)
        trow.addStretch(1)
        col.addLayout(trow)
        meta = []
        if ep.extra.get("duration"):
            meta.append(str(ep.extra["duration"]))
        plot = (ep.extra.get("plot") or "").strip()
        if plot:
            meta.append(plot[:110] + ("…" if len(plot) > 110 else ""))
        if meta:
            m = QLabel("  ·  ".join(meta))
            m.setObjectName("Muted")
            m.setWordWrap(True)
            col.addWidget(m)
        if progress and progress.get("dur"):
            pb = QProgressBar()
            pb.setFixedHeight(3)
            pb.setRange(0, progress["dur"])
            pb.setValue(progress["pos"])
            pb.setFixedWidth(220)
            prow = QHBoxLayout()
            prow.addWidget(pb)
            prow.addStretch(1)
            col.addLayout(prow)
        lay.addLayout(col, 1)
        self.dl_lbl = QLabel()
        self.dl_lbl.setObjectName("Muted")
        lay.addWidget(self.dl_lbl)
        self.btn_dl = QToolButton()
        self.btn_dl.setIconSize(QSize(22, 22))
        self.btn_dl.clicked.connect(lambda: self.download.emit(self.ep))
        lay.addWidget(self.btn_dl)
        self.set_dl(dl_task)
        bp = QToolButton()
        bp.setIcon(icon("play", theme.ACCENT))
        bp.setIconSize(QSize(26, 26))
        bp.clicked.connect(lambda: self.play.emit(self.ep))
        lay.addWidget(bp)

    def set_dl(self, t):
        """İndirme durumunu düğmeye yansıtır; indirme bitince anında ✓ gösterilir."""
        st = t["status"] if t else None
        if st == DONE:
            self.btn_dl.setIcon(icon("check", theme.ACCENT))
            self.btn_dl.setToolTip(_("İndirildi"))
            self.dl_lbl.setText(_("İndirildi"))
        elif st in (RUNNING, QUEUED, RESOLVING, PAUSED):
            self.btn_dl.setIcon(icon("download", theme.ACCENT))
            pct = dl_percent(t)
            txt = _("Duraklatıldı") if st == PAUSED else (_("%{n}", n=pct) if pct else _("Sırada"))
            self.btn_dl.setToolTip(txt)
            self.dl_lbl.setText(txt)
        elif st == FAILED:
            self.btn_dl.setIcon(icon("download", theme.DANGER))
            self.btn_dl.setToolTip(_("İndirme hatası — tekrar dene"))
            self.dl_lbl.setText(_("Hata"))
        else:
            self.btn_dl.setIcon(icon("download"))
            self.btn_dl.setToolTip(_("İndir"))
            self.dl_lbl.setText("")
        self.dl_lbl.setVisible(bool(self.dl_lbl.text()))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.play.emit(self.ep)


class DetailView(QWidget):
    back = Signal()
    playRequested = Signal(object, int)        # öğe, başlangıç saniyesi
    downloadRequested = Signal(object)
    favoriteChanged = Signal()

    def __init__(self, ctx, kind, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kind = kind
        self.item = None
        self.info = {}
        self.seasons = {}
        self._req = 0
        self._ep_rows = {}  # bölüm id -> EpisodeRow
        self.bg = Backdrop(self)
        ctx.downloads.changed.connect(self._dl_changed)
        ctx.downloads.listChanged.connect(self._dl_list_changed)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        enable_kinetic(self.scroll, ctx.settings.get("touch_scroll"))
        inner = QWidget()
        self.scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 10, 16, 16)
        root.setSpacing(10)

        top = QHBoxLayout()
        b = QPushButton("  " + _("Geri"))
        b.setIcon(icon("back"))
        b.setObjectName("Flat")
        b.clicked.connect(self.back.emit)
        top.addWidget(b)
        top.addStretch(1)
        root.addLayout(top)

        hero = QHBoxLayout()
        hero.setSpacing(20)
        self.poster = PosterLabel(180, 270)
        hero.addWidget(self.poster, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        col.addWidget(self.title)
        self.meta = QLabel()
        self.meta.setObjectName("Muted")
        self.meta.setStyleSheet(theme.scaled("font-size:14px;"))
        self.meta.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(self.meta)
        self.genre = QLabel()
        self.genre.setObjectName("Accent")
        col.addWidget(self.genre)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_play = QPushButton("  " + _("Oynat"))
        self.btn_play.setObjectName("Primary")
        self.btn_play.setIcon(icon("play", "#06201e"))
        self.btn_play.setMinimumHeight(40)
        self.btn_play.clicked.connect(self._play_main)
        self.btn_restart = QPushButton("  " + _("Baştan başla"))
        self.btn_restart.setIcon(icon("refresh"))
        self.btn_restart.setMinimumHeight(40)
        self.btn_restart.clicked.connect(lambda: self._play_main(restart=True))
        self.btn_dl = QPushButton("  " + _("İndir"))
        self.btn_dl.setIcon(icon("download"))
        self.btn_dl.setMinimumHeight(40)
        self.btn_dl.clicked.connect(lambda: self.item and self.downloadRequested.emit(self.item))
        self.btn_fav = QPushButton()
        self.btn_fav.setMinimumHeight(40)
        self.btn_fav.clicked.connect(self._toggle_fav)
        for x in (self.btn_play, self.btn_restart, self.btn_dl, self.btn_fav):
            btns.addWidget(x)
        btns.addStretch(1)
        col.addLayout(btns)
        self.plot = QLabel()
        self.plot.setWordWrap(True)
        self.plot.setStyleSheet(theme.scaled("font-size:14px;line-height:150%;color:#c9d1d9;"))
        col.addWidget(self.plot)
        self.credits = QLabel()
        self.credits.setObjectName("Muted")
        self.credits.setWordWrap(True)
        self.credits.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(self.credits)
        self.loading = Spinner(self, 30)
        col.addWidget(self.loading)
        col.addStretch(1)
        hero.addLayout(col, 1)
        root.addLayout(hero)

        # Diziler için sezonlar ve bölümler
        self.season_bar = QHBoxLayout()
        self.season_bar.setSpacing(6)
        self.season_group = QButtonGroup(self)
        self.season_wrap = QWidget()
        self.season_wrap.setLayout(self.season_bar)
        self.season_bar.setContentsMargins(0, 6, 0, 0)
        root.addWidget(self.season_wrap)
        self.eps_host = QWidget()
        self.eps = QVBoxLayout(self.eps_host)
        self.eps.setContentsMargins(0, 0, 0, 0)
        self.eps.setSpacing(6)
        root.addWidget(self.eps_host)
        root.addStretch(1)
        self.season_wrap.setVisible(kind == SERIES)
        self.eps_host.setVisible(kind == SERIES)
        self.current_season = None

    def resizeEvent(self, e):
        self.bg.setGeometry(self.rect())
        self.scroll.setGeometry(self.rect())

    def show_item(self, item):
        self.item = item
        self._req += 1
        req = self._req
        self.info = {}
        self.seasons = {}
        self.title.setText(item.name)
        self.poster.set_url(item.logo)
        self.bg.set_url(item.extra.get("backdrop") or item.logo)
        self.plot.setText(item.extra.get("plot", ""))
        self.genre.setText(item.extra.get("genre", ""))
        self.credits.setText("")
        self._set_meta()
        self._update_fav()
        self._update_play_btn()
        self._clear_eps()
        self.btn_dl.setVisible(self.kind == MOVIE)
        self._update_dl_btn()
        self.btn_restart.setVisible(False)
        self.loading.show()
        prov = self.ctx.library.provider
        fn = prov.vod_info if self.kind == MOVIE else prov.series_info

        def done(res):
            if req != self._req:
                return
            self.loading.hide()
            if self.kind == MOVIE:
                self.info = res or {}
            else:
                self.info = (res or {}).get("info", {})
                self.seasons = (res or {}).get("seasons", {})
                self._build_seasons()
            self._apply_info()

        def fail(e):
            if req == self._req:
                self.loading.hide()
                self.credits.setText(f"<span style='color:{theme.DANGER}'>" + _("Ayrıntılar alınamadı: {err}", err=e)
                                     + "</span>")

        run_async(fn, item, on_done=done, on_error=fail)
        self.scroll.verticalScrollBar().setValue(0)

    def _set_meta(self, extra=None):
        it = self.item
        parts = []
        if it.year:
            parts.append(it.year)
        r = it.rating or (float(self.info.get("rating") or 0) if str(self.info.get("rating") or "").replace(".", "", 1).isdigit() else 0)
        if r:
            parts.append(f"<span style='color:{theme.WARN}'>★ {r:.1f}</span>")
        if extra:
            parts.extend(extra)
        self.meta.setText("   •   ".join(parts))

    def _apply_info(self):
        i = self.info
        if i.get("plot"):
            self.plot.setText(i["plot"])
        if i.get("genre"):
            self.genre.setText(i["genre"])
        if i.get("cover") and not self.item.logo:
            self.poster.set_url(i["cover"])
        if i.get("backdrop"):
            self.bg.set_url(i["backdrop"])
        extra = []
        if i.get("duration"):
            extra.append(str(i["duration"]))
        if i.get("release") and not self.item.year:
            extra.append(str(i["release"])[:10])
        if self.kind == SERIES and self.seasons:
            extra.append(_("{n} sezon", n=len(self.seasons)))
        self._set_meta(extra)
        cr = []
        if i.get("director"):
            cr.append(f"<b style='color:{theme.TEXT}'>{_('Yönetmen:')}</b> {i['director']}")
        if i.get("cast"):
            cr.append(f"<b style='color:{theme.TEXT}'>{_('Oyuncular:')}</b> {i['cast']}")
        self.credits.setText("<br>".join(cr))
        self._update_play_btn()

    def _update_fav(self):
        fav = self.ctx.userdata.is_favorite(self.kind, self.item.id)
        self.btn_fav.setText("  " + (_("Favoride") if fav else _("Favori")))
        self.btn_fav.setIcon(icon("star" if fav else "star_border", theme.ACCENT if fav else theme.TEXT))

    def _toggle_fav(self):
        self.ctx.userdata.toggle_favorite(self.kind, self.item.id, self.item.brief())
        self._update_fav()
        self.favoriteChanged.emit()

    def _resume_target(self):
        """Dizi için devam edilecek bölüm; film için kendisi."""
        if self.kind == MOVIE:
            return self.item, self.ctx.userdata.get_progress(f"movie:{self.item.id}")
        last = self.ctx.userdata.get_progress(f"series:{self.item.id}")
        if last and self.seasons:
            for s, eps in self.seasons.items():
                for e in eps:
                    if e.id == last.get("ep"):
                        return e, self.ctx.userdata.get_progress(f"episode:{e.id}")
        first = next(iter(self.seasons.values()), [None])[0] if self.seasons else None
        return first, None

    def _update_play_btn(self):
        target, prog = self._resume_target()
        if prog and prog.get("pos", 0) > 30:
            label = _("Devam et ({time})", time=fmt_time(prog["pos"]))
            if self.kind == SERIES and target is not None:
                label = _("S{s} B{e} devam et", s=target.extra.get("season", 1), e=target.extra.get("episode", target.num))
            self.btn_play.setText("  " + label)
            self.btn_restart.setVisible(self.kind == MOVIE)
        else:
            if self.kind == SERIES and target is not None and self.ctx.userdata.get_progress(f"series:{self.item.id}"):
                self.btn_play.setText("  " + _("S{s} B{e} oynat", s=target.extra.get("season", 1),
                                                e=target.extra.get("episode", target.num)))
            else:
                self.btn_play.setText("  " + (_("Oynat") if self.kind == MOVIE else _("İlk bölümü oynat")))
            self.btn_restart.setVisible(False)
        self.btn_play.setEnabled(target is not None)

    def _play_main(self, restart=False):
        target, prog = self._resume_target()
        if target is None:
            return
        start = 0 if restart or not prog else prog.get("pos", 0)
        self.playRequested.emit(target, int(start))

    # --- İndirme durumu --------------------------------------------
    def _update_dl_btn(self):
        if self.kind != MOVIE or self.item is None:
            return
        t = self.ctx.downloads.find_by_item(f"movie:{self.item.id}")
        st = t["status"] if t else None
        if st == DONE:
            self.btn_dl.setText("  " + _("İndirildi"))
            self.btn_dl.setIcon(icon("check", theme.ACCENT))
        elif st in (RUNNING, QUEUED, RESOLVING):
            pct = dl_percent(t)
            self.btn_dl.setText("  " + (_("İndiriliyor %{n}", n=pct) if pct else _("Sırada")))
            self.btn_dl.setIcon(icon("download", theme.ACCENT))
        elif st == PAUSED:
            self.btn_dl.setText("  " + _("Duraklatıldı %{n}", n=dl_percent(t)))
            self.btn_dl.setIcon(icon("download", theme.ACCENT))
        else:
            self.btn_dl.setText("  " + _("İndir"))
            self.btn_dl.setIcon(icon("download", theme.DANGER if st == FAILED else theme.TEXT))

    def _dl_changed(self, tid):
        t = self.ctx.downloads.find(tid)
        if not t or self.item is None:
            return
        key = t.get("key") or ""
        if self.kind == MOVIE:
            if key == f"movie:{self.item.id}":
                self._update_dl_btn()
        elif key.startswith("episode:"):
            row = self._ep_rows.get(key[len("episode:"):])
            if row is not None:
                row.set_dl(t)

    def _dl_list_changed(self):
        if self.item is None:
            return
        if self.kind == MOVIE:
            self._update_dl_btn()
            return
        dm = self.ctx.downloads
        for eid, row in self._ep_rows.items():
            row.set_dl(dm.find_by_item(f"episode:{eid}"))

    # --- Sezonlar ---------------------------------------------------
    def _clear_eps(self):
        self._ep_rows = {}
        while self.eps.count():
            w = self.eps.takeAt(0).widget()
            if w:
                w.deleteLater()
        for b in self.season_group.buttons():
            self.season_group.removeButton(b)
            b.deleteLater()
        while self.season_bar.count():
            self.season_bar.takeAt(0)

    def _build_seasons(self):
        self._clear_eps()
        if not self.seasons:
            lbl = QLabel(_("Bölüm bulunamadı."))
            lbl.setObjectName("Muted")
            self.eps.addWidget(lbl)
            return
        target, _ = self._resume_target()
        sel = target.extra.get("season") if target is not None else None
        for s in self.seasons:
            b = QPushButton(_("Sezon {n}", n=s))
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, x=s: self._show_season(x))
            self.season_group.addButton(b)
            self.season_bar.addWidget(b)
            if sel is None:
                sel = s
            if s == sel:
                b.setChecked(True)
        self.season_bar.addStretch(1)
        self._show_season(sel)

    def _show_season(self, s):
        self.current_season = s
        self._ep_rows = {}
        while self.eps.count():
            w = self.eps.takeAt(0).widget()
            if w:
                w.deleteLater()
        dm = self.ctx.downloads
        dm.prune_missing()
        for ep in self.seasons.get(s, []):
            prog = self.ctx.userdata.get_progress(f"episode:{ep.id}")
            row = EpisodeRow(ep, prog, dm.find_by_item(f"episode:{ep.id}"),
                             self.ctx.userdata.is_watched(f"episode:{ep.id}"))
            row.play.connect(self._play_ep)
            row.download.connect(self.downloadRequested.emit)
            self.eps.addWidget(row)
            self._ep_rows[ep.id] = row

    def _play_ep(self, ep):
        prog = self.ctx.userdata.get_progress(f"episode:{ep.id}")
        self.playRequested.emit(ep, int(prog["pos"]) if prog and prog.get("pos", 0) > 30 else 0)

    def next_episode(self, ep):
        flat = [e for eps in self.seasons.values() for e in eps]
        for i, e in enumerate(flat):
            if e.id == ep.id and i + 1 < len(flat):
                return flat[i + 1]
        return None

    def refresh_state(self):
        if self.item is None:
            return
        self._update_play_btn()
        if self.kind == SERIES and self.current_season is not None:
            self._show_season(self.current_season)


class VodPage(QWidget):
    playRequested = Signal(object, int, object)   # öğe, başlangıç, dizi öğesi (bölüm ise)
    downloadRequested = Signal(object, object)    # öğe, dizi öğesi

    def __init__(self, ctx, kind, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.kind = kind
        self.lib = None
        self.category = ALL_CAT
        self.query = ""
        self.sort = ctx.settings.get("vod_sort" if kind == MOVIE else "series_sort", "default")
        self.lang = ctx.settings.get("lang_filter", {}).get(kind, "")
        self._pending_req = None
        self._loading_more = False

        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        # Izgara sayfası
        grid_page = QWidget()
        root = QVBoxLayout(grid_page)
        root.setContentsMargins(14, 12, 14, 6)
        root.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel(_("Filmler") if kind == MOVIE else _("Diziler"))
        title.setObjectName("Title")
        head.addWidget(title)
        self.count = QLabel()
        self.count.setObjectName("Badge")
        head.addWidget(self.count)
        head.addStretch(1)
        self.btn_clear = QPushButton("  " + _("Listeyi temizle"))
        self.btn_clear.setIcon(icon("delete", theme.DANGER))
        self.btn_clear.setObjectName("Danger")
        self.btn_clear.clicked.connect(self._clear_recent)
        self.btn_clear.hide()
        head.addWidget(self.btn_clear)
        self.lang_box = LangFilterBox()
        self.lang_box.changedLang.connect(self._on_lang)
        head.addWidget(self.lang_box)
        self.search = SearchBox(_("Film ara…") if kind == MOVIE else _("Dizi ara…"))
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(240)
        self.search.debounced.connect(self._on_search)
        head.addWidget(self.search)
        self.sort_box = QComboBox()
        for k, v in SORTS:
            self.sort_box.addItem(_(v), k)
        keys = [k for k, _ in SORTS]
        self.sort_box.setCurrentIndex(keys.index(self.sort) if self.sort in keys else 0)
        self.sort_box.currentIndexChanged.connect(self._on_sort)
        head.addWidget(self.sort_box)
        root.addLayout(head)
        from .widgets import ChipBar  # noqa: PLC0415
        self.chips = ChipBar(mouse_drag=True)
        self.chips.selected.connect(self._on_category)
        root.addWidget(self.chips)
        self.body = QStackedWidget()
        self.model = ItemModel(self)
        self.delegate = PosterDelegate(ctx, kind)
        self.grid = GridView(self.delegate)
        self.grid.setModel(self.model)
        self.grid.clicked.connect(self._clicked)
        self.grid.activated.connect(self._clicked)
        self.grid.nearEnd.connect(self._load_more)
        self.grid.contextRequested.connect(self._context)
        enable_kinetic(self.grid, ctx.settings.get("touch_scroll"))
        self.status = StatusView()
        self.status.retry.connect(lambda: self.lib and self.lib.refresh())
        self.body.addWidget(self.grid)
        self.body.addWidget(self.status)
        root.addWidget(self.body, 1)
        self.stack.addWidget(grid_page)

        self.detail = DetailView(ctx, kind)
        self.detail.back.connect(self.close_detail)
        self.detail.playRequested.connect(self._detail_play)
        self.detail.downloadRequested.connect(lambda it: self.downloadRequested.emit(it, self.detail.item))
        self.detail.favoriteChanged.connect(self._fav_changed)
        self.stack.addWidget(self.detail)

    # ------------------------------------------------------------------
    def set_library(self, lib):
        self.lib = lib
        self.category = ALL_CAT
        self.model.set_items([])
        self.stack.setCurrentIndex(0)
        lib.section_ready.connect(self._section_ready)
        lib.section_loading.connect(self._section_loading)
        lib.section_failed.connect(self._section_failed)
        lib.page_ready.connect(self._page_ready)
        if lib.state[self.kind] == "ready":
            self._section_ready(self.kind)
        else:
            self._section_loading(self.kind, _("Yükleniyor…"))

    def _section_loading(self, s, msg):
        if s == self.kind and not self.model.items:
            self.status.loading(msg)
            self.body.setCurrentWidget(self.status)

    def _section_failed(self, s, msg):
        if s == self.kind:
            self.status.error(msg)
            self.body.setCurrentWidget(self.status)

    def _section_ready(self, s):
        if s != self.kind:
            return
        cats = [(ALL_CAT, _("Tümü"), None), (FAV_CAT, _("Favoriler"), "star"), (RECENT_CAT, _("Son izlenen"), "history")]
        for c in self.lib.visible_categories(self.kind):
            cats.append((c.id, c.name, "lock" if self.lib.is_locked(self.kind, c) else None))
        self.chips.set_categories(cats, self.category)
        self.category = self.chips.current
        self.lang = self.lang_box.set_languages(self.lib.languages(self.kind), self.lang)
        self.apply()

    def _on_lang(self, code):
        self.lang = code
        self.ctx.settings.data.setdefault("lang_filter", {})[self.kind] = code
        self.ctx.settings.save()
        self.apply()

    def apply(self):
        if not self.lib:
            return
        loader().cancel_pending()
        paged = self.lib.is_paged(self.kind) and self.category not in (FAV_CAT, RECENT_CAT)
        if paged:
            cache = self.lib.cached_pages(self.kind, self.category)
            if cache:
                self._show(self._local_filter(cache["items"]), total=None)
            else:
                self.model.set_items([])
                self.status.loading(_("Yükleniyor…"))
                self.body.setCurrentWidget(self.status)
                self._pending_req = self.lib.request_page(self.kind, self.category, 1)
            return
        items = self.lib.filtered(self.kind, self.category, self.query, self.sort, self.ctx.userdata, self.lang)
        self._show(items)

    def _local_filter(self, items):
        from ..library import fold, folded, sort_items  # noqa: PLC0415
        items = self.lib.filter_lang(self.kind, items, self.lang)
        if self.query:
            q = fold(self.query)
            items = [i for i in items if q in folded(i)]
        return sort_items(items, self.sort)

    def _show(self, items, total=None):
        self.model.set_items(items)
        self.count.setText(str(len(items)))
        self.btn_clear.setVisible(self.category == RECENT_CAT and bool(items))
        if items:
            self.body.setCurrentWidget(self.grid)
        else:
            msg = {FAV_CAT: _("Favori listeniz boş."), RECENT_CAT: _("Henüz bir şey izlemediniz.")}.get(
                self.category, _("İçerik bulunamadı."))
            self.status.empty(msg, "movie" if self.kind == MOVIE else "series")
            self.body.setCurrentWidget(self.status)

    def _page_ready(self, section, cat, page, items, pages, req):
        if section != self.kind or cat != self.category:
            return
        self._loading_more = False
        if page == 1:
            self._show(self._local_filter(items))
        else:
            self.model.append(self._local_filter(items) if self.query else items)
            self.count.setText(str(len(self.model.items)))

    def _load_more(self):
        if not self.lib or not self.lib.is_paged(self.kind) or self._loading_more:
            return
        c = self.lib.cached_pages(self.kind, self.category)
        if c and c["loaded"] < c["pages"]:
            self._loading_more = True
            self.lib.request_page(self.kind, self.category, c["loaded"] + 1)

    def _on_category(self, cid):
        if self.lib:
            cat = next((c for c in self.lib.cats[self.kind] if c.id == cid), None)
            if cat and self.lib.is_locked(self.kind, cat) and not self.ctx.ask_pin(self):
                self.chips.set_current(self.category, emit=False)
                return
        self.category = cid
        self.apply()
        self.grid.scrollToTop()

    def _on_search(self, q):
        self.query = q.strip()
        self.apply()

    def _on_sort(self, i):
        self.sort = self.sort_box.itemData(i)
        self.ctx.settings.set("vod_sort" if self.kind == MOVIE else "series_sort", self.sort)
        self.apply()

    def _clicked(self, idx):
        it = idx.data(ItemRole)
        if it:
            self.open_detail(it)

    def open_detail(self, it):
        if not self.ctx.can_open(self.kind, it, self):
            return
        self.detail.show_item(it)
        self.ctx.animate_switch(self.stack, 1)

    def close_detail(self):
        self.ctx.animate_switch(self.stack, 0)
        self.grid.viewport().update()

    def _detail_play(self, it, start):
        series = self.detail.item if it.kind == EPISODE else None
        self.playRequested.emit(it, start, series)

    def _fav_changed(self):
        if self.category == FAV_CAT:
            self.apply()
        self.grid.viewport().update()

    def on_favorites_changed(self):
        """Favori başka yerden (ör. oynatıcıdaki yıldız) değiştiğinde."""
        self._fav_changed()
        if self.detail.item is not None:
            self.detail._update_fav()

    def _clear_recent(self):
        r = QMessageBox.question(self, _("Son izlenen"), _("Son izlenenler listesi temizlensin mi?"))
        if r == QMessageBox.StandardButton.Yes:
            self.ctx.userdata.clear_history(self.kind)
            self.apply()

    def _context(self, idx, pos):
        it = idx.data(ItemRole)
        if it is None:
            return
        fav = self.ctx.userdata.is_favorite(self.kind, it.id)
        m = QMenu(self)
        a_open = m.addAction(icon("info"), _("Ayrıntılar"))
        a_play = m.addAction(icon("play"), _("Oynat")) if self.kind == MOVIE else None
        a_dl = m.addAction(icon("download"), _("İndir")) if self.kind == MOVIE else None
        a_fav = m.addAction(icon("star"), _("Favorilerden çıkar") if fav else _("Favorilere ekle"))
        a_rm = m.addAction(icon("delete", theme.DANGER), _("Son izlenenlerden kaldır")) \
            if self.category == RECENT_CAT else None
        locked = it.id in self.lib.lock_sets(self.kind)[1]
        a_lock = m.addAction(icon("lock", theme.WARN), _("Kilidi kaldır") if locked else _("PIN ile kilitle"))
        act = m.exec(pos)
        if act is a_open:
            self.open_detail(it)
        elif act is a_lock:
            self.ctx.win.toggle_lock(self.kind, it)
            self.grid.viewport().update()
        elif a_play is not None and act is a_play:
            prog = self.ctx.userdata.get_progress(f"movie:{it.id}")
            self.playRequested.emit(it, int(prog["pos"]) if prog else 0, None)
        elif a_dl is not None and act is a_dl:
            self.downloadRequested.emit(it, None)
        elif act is a_fav:
            self.ctx.userdata.toggle_favorite(self.kind, it.id, it.brief())
            self._fav_changed()
        elif a_rm is not None and act is a_rm:
            self.ctx.userdata.remove_history(self.kind, it.id)
            self.apply()

    def refresh_state(self):
        self.grid.viewport().update()
        if self.stack.currentIndex() == 1:
            self.detail.refresh_state()
        elif self.category == RECENT_CAT:
            self.apply()
