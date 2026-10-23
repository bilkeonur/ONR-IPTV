"""Canlı TV: kategori çipleri, kanal listesi, önizleme oynatıcı ve yayın akışı (EPG / catch-up)."""
import time

from ..config import IS_WINDOWS
from ..i18n import N_, _, day_name
from ..library import ALL_CAT, FAV_CAT, RECENT_CAT
from ..providers import LIVE
from ..qt import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                  QMenu, QMessageBox, QProgressBar, QPushButton, QSize, QStackedWidget, Qt, QTimer, QVBoxLayout,
                  QWidget, Signal)
from ..tasks import run_async
from . import theme
from .icons import icon
from .widgets import (ChannelDelegate, ChipBar, ItemModel, ItemRole, LangFilterBox, ListView, SearchBox, StatusView,
                      enable_kinetic)

SORTS = [("default", N_("Varsayılan sıra")), ("num", N_("Kanal no")), ("az", "A → Z"), ("za", "Z → A"),
         ("new", N_("Yeni eklenen"))]


class AspectBox(QWidget):
    """16:9 oranını koruyan önizleme alanı (oynatıcı bunun üzerine konumlanır)."""

    geometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setStyleSheet(f"background:#000; border-radius:12px;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.hint = QLabel(_("Bir kanal seçin"), self)
        self.hint.setObjectName("Muted")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return int(w * 9 / 16)

    def resizeEvent(self, e):
        self.hint.setGeometry(self.rect())
        h = self.heightForWidth(self.width())
        par = self.parentWidget()
        if par is not None and par.height() > 0:
            h = min(h, int(par.height() * 0.55))
        if self.height() != h:
            self.setFixedHeight(h)
        self.geometryChanged.emit()

    def moveEvent(self, e):
        self.geometryChanged.emit()


class LivePage(QWidget):
    playRequested = Signal(object, bool)       # kanal, tam ekran
    catchupRequested = Signal(object, dict)
    guideRequested = Signal()
    multiviewRequested = Signal(object)        # başlangıç kanalı ya da None

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.lib = None
        self.category = ALL_CAT
        self.query = ""
        self.sort = ctx.settings.get("live_sort", "default")
        self.lang = ctx.settings.get("lang_filter", {}).get(LIVE, "")
        self.current = None
        self._epg_req = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(_("Canlı TV"))
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
        self.btn_guide = QPushButton("  " + _("TV Rehberi"))
        self.btn_guide.setIcon(icon("list"))
        self.btn_guide.clicked.connect(self.guideRequested.emit)
        head.addWidget(self.btn_guide)
        self.btn_multi = QPushButton("  " + _("Çoklu ekran"))
        self.btn_multi.setIcon(icon("grid"))
        self.btn_multi.clicked.connect(lambda: self.multiviewRequested.emit(None))
        self.btn_multi.setVisible(IS_WINDOWS)
        head.addWidget(self.btn_multi)
        self.lang_box = LangFilterBox()
        self.lang_box.changedLang.connect(self._on_lang)
        head.addWidget(self.lang_box)
        self.search = SearchBox(_("Kanal ara…"))
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(240)
        self.search.debounced.connect(self._on_search)
        head.addWidget(self.search)
        self.sort_box = QComboBox()
        for k, v in SORTS:
            self.sort_box.addItem(_(v), k)
        self.sort_box.setCurrentIndex(max(0, [k for k, _ in SORTS].index(self.sort) if self.sort in dict(SORTS) else 0))
        self.sort_box.currentIndexChanged.connect(self._on_sort)
        head.addWidget(self.sort_box)
        root.addLayout(head)

        self.chips = ChipBar(mouse_drag=True)
        self.chips.selected.connect(self._on_category)
        root.addWidget(self.chips)

        body = QHBoxLayout()
        body.setSpacing(12)
        # Sol: kanal listesi
        self.list_stack = QStackedWidget()
        self.model = ItemModel(self)
        self.delegate = ChannelDelegate(ctx)
        self.view = ListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.clicked.connect(self._clicked)
        self.view.activated.connect(lambda idx: self._open(idx, True))
        self.view.doubleClicked.connect(lambda idx: self._open(idx, True))
        self.view.contextRequested.connect(self._context)
        enable_kinetic(self.view, ctx.settings.get("touch_scroll"))
        self.status = StatusView()
        self.status.retry.connect(lambda: self.lib and self.lib.refresh())
        self.list_stack.addWidget(self.view)
        self.list_stack.addWidget(self.status)
        body.addWidget(self.list_stack, 11)
        ctx.epg.updated.connect(self.view.viewport().update)

        # Sağ: önizleme + bilgi + program akışı
        right = QVBoxLayout()
        right.setSpacing(8)
        self.preview = AspectBox()
        right.addWidget(self.preview)
        info = QFrame()
        info.setObjectName("Panel")
        il = QVBoxLayout(info)
        il.setContentsMargins(12, 10, 12, 10)
        il.setSpacing(3)
        r1 = QHBoxLayout()
        self.ch_name = QLabel("—")
        self.ch_name.setObjectName("H2")
        r1.addWidget(self.ch_name, 1)
        self.live_badge = QLabel(_("CANLI"))
        self.live_badge.setObjectName("LiveBadge")
        self.live_badge.hide()
        r1.addWidget(self.live_badge)
        il.addLayout(r1)
        self.now_title = QLabel()
        self.now_title.setObjectName("Accent")
        self.now_title.setWordWrap(True)
        il.addWidget(self.now_title)
        self.now_bar = QProgressBar()
        self.now_bar.setFixedHeight(4)
        self.now_bar.setTextVisible(False)
        self.now_bar.hide()
        il.addWidget(self.now_bar)
        self.now_desc = QLabel()
        self.now_desc.setObjectName("Muted")
        self.now_desc.setWordWrap(True)
        self.now_desc.setMaximumHeight(34)
        il.addWidget(self.now_desc)
        right.addWidget(info)
        self.progs = QListWidget()
        self.progs.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.progs.itemClicked.connect(self._prog_clicked)
        enable_kinetic(self.progs, ctx.settings.get("touch_scroll"))
        right.addWidget(self.progs, 1)
        rw = QWidget()
        rw.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        body.addWidget(rw, 10)
        root.addLayout(body, 1)

        self._tick = QTimer(self)
        self._tick.setInterval(30000)
        self._tick.timeout.connect(self._refresh_info)
        self._tick.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Dar ekranda (ör. Pi 1024x600) başlık düğmeleri yalnızca simge olur
        wide = self.width() >= 1000
        for b, text in ((self.btn_guide, _("TV Rehberi")), (self.btn_multi, _("Çoklu ekran"))):
            b.setText("  " + text if wide else "")
            b.setToolTip("" if wide else text)

    # ------------------------------------------------------------------
    def set_library(self, lib):
        self.lib = lib
        self.category = ALL_CAT
        self.current = None
        self.model.set_items([])
        self.ch_name.setText("—")
        self.now_title.setText("")
        self.now_desc.setText("")
        self.progs.clear()
        lib.section_ready.connect(self._section_ready)
        lib.section_loading.connect(self._section_loading)
        lib.section_failed.connect(self._section_failed)
        if lib.state[LIVE] == "ready":
            self._section_ready(LIVE)
        else:
            self._section_loading(LIVE, _("Kanallar yükleniyor…"))

    def _section_loading(self, s, msg):
        if s != LIVE:
            return
        if not self.model.items:
            self.status.loading(msg)
            self.list_stack.setCurrentWidget(self.status)

    def _section_failed(self, s, msg):
        if s != LIVE:
            return
        self.status.error(msg)
        self.list_stack.setCurrentWidget(self.status)

    def _section_ready(self, s):
        if s != LIVE:
            return
        cats = [(ALL_CAT, _("Tümü"), None), (FAV_CAT, _("Favoriler"), "star"), (RECENT_CAT, _("Son izlenen"), "history")]
        for c in self.lib.visible_categories(LIVE):
            cats.append((c.id, c.name, "lock" if self.lib.is_locked(LIVE, c) else None))
        self.chips.set_categories(cats, self.category)
        self.category = self.chips.current
        self.lang = self.lang_box.set_languages(self.lib.languages(LIVE), self.lang)
        self.apply()

    def _on_lang(self, code):
        self.lang = code
        self.ctx.settings.data.setdefault("lang_filter", {})[LIVE] = code
        self.ctx.settings.save()
        self.apply()

    def apply(self, keep_scroll=False):
        if not self.lib:
            return
        items = self.lib.filtered(LIVE, self.category, self.query, self.sort, self.ctx.userdata, self.lang)
        sb = self.view.verticalScrollBar().value()
        self.model.set_items(items)
        if keep_scroll:
            self.view.verticalScrollBar().setValue(sb)
        self.count.setText(f"{len(items)}")
        self.btn_clear.setVisible(self.category == RECENT_CAT and bool(items))
        if items:
            self.list_stack.setCurrentWidget(self.view)
            if self.current:
                row = self.model.row_of(self.current.id)
                if row >= 0:
                    self.view.setCurrentIndex(self.model.index(row))
                    if not keep_scroll:
                        self.view.scrollTo(self.model.index(row), QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            msg = {FAV_CAT: _("Henüz favori kanal yok.\nKanal üzerinde sağ tık / uzun bas → Favori"),
                   RECENT_CAT: _("Henüz izlenen kanal yok.")}.get(self.category, _("Kanal bulunamadı."))
            self.status.empty(msg, "live")
            self.list_stack.setCurrentWidget(self.status)

    def _on_category(self, cid):
        if self.lib:
            cat = next((c for c in self.lib.cats[LIVE] if c.id == cid), None)
            if cat and self.lib.is_locked(LIVE, cat) and not self.ctx.ask_pin(self):
                self.chips.set_current(self.category, emit=False)
                return
        self.category = cid
        self.apply()
        self.view.scrollToTop()

    def _on_search(self, q):
        self.query = q.strip()
        self.apply()

    def _on_sort(self, i):
        self.sort = self.sort_box.itemData(i)
        self.ctx.settings.set("live_sort", self.sort)
        self.apply()

    # ------------------------------------------------------------------
    def _clicked(self, idx):
        it = idx.data(ItemRole)
        if it is None:
            return
        if self.current is not None and self.current.id == it.id and self.ctx.player_playing(it.id):
            self.playRequested.emit(it, True)
        else:
            self.select(it, play=True)

    def _open(self, idx, full):
        it = idx.data(ItemRole)
        if it:
            self.select(it, play=False)
            self.playRequested.emit(it, full)

    def select(self, it, play=True):
        self.current = it
        self.ch_name.setText(it.name)
        self.live_badge.show()
        self.preview.hint.setText("")
        self._refresh_info()
        self._load_programs(it)
        if play:
            self.playRequested.emit(it, False)
        self.view.viewport().update()

    def step(self, delta):
        """Oynatıcıdan kanal yukarı/aşağı."""
        n = len(self.model.items)
        if not n:
            return None
        row = self.model.row_of(self.current.id) if self.current else -1
        row = (row + delta) % n
        it = self.model.items[row]
        self.view.setCurrentIndex(self.model.index(row))
        self.select(it, play=False)
        return it

    def _refresh_info(self):
        it = self.current
        if not it:
            return
        cur, nxt = self.ctx.epg.now_next(it)
        if cur:
            t = f"{time.strftime('%H:%M', time.localtime(cur['start']))} – {time.strftime('%H:%M', time.localtime(cur['end']))}"
            self.now_title.setText(f"{cur['title']}   <span style='color:{theme.MUTED};font-weight:400'>{t}</span>")
            self.now_title.setTextFormat(Qt.TextFormat.RichText)
            dur = max(1, cur["end"] - cur["start"])
            self.now_bar.setRange(0, dur)
            self.now_bar.setValue(int(time.time() - cur["start"]))
            self.now_bar.show()
            desc = cur.get("desc") or ""
            if nxt:
                desc = (desc[:140] + "  ") if desc else ""
                desc += _("Sıradaki: {time} {title}", time=time.strftime("%H:%M", time.localtime(nxt["start"])),
                          title=nxt["title"])
            self.now_desc.setText(desc)
        else:
            self.now_title.setText(_("Program bilgisi yok") if self.ctx.epg.programs(it, fetch=False) is not None else "")
            self.now_bar.hide()
            self.now_desc.setText("")
        self.ctx.update_player_epg(it, cur, nxt)

    def _load_programs(self, it):
        self.progs.clear()
        self._epg_req += 1
        req = self._epg_req
        prov = self.lib.provider

        def done(progs):
            if req != self._epg_req:
                return
            self._fill_programs(it, progs or [])

        run_async(prov.epg_table, it, on_done=done, on_error=lambda e: None)

    def _fill_programs(self, it, progs):
        self.progs.clear()
        now = time.time()
        cur_row = -1
        last_day = None
        for p in progs:
            lt = time.localtime(p["start"])
            day = time.strftime("%d.%m ", lt) + day_name(lt)
            if day != last_day:
                last_day = day
                h = QListWidgetItem(day)
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                h.setForeground(self.palette().mid())
                h.setSizeHint(QSize(100, 26))
                self.progs.addItem(h)
            t = time.strftime("%H:%M", time.localtime(p["start"]))
            live = p["start"] <= now < p["end"]
            text = f"{t}   {p['title']}"
            li = QListWidgetItem(text)
            li.setData(ItemRole, p)
            li.setSizeHint(QSize(100, 34))
            if live:
                li.setForeground(Qt.GlobalColor.white)
                f = li.font()
                f.setBold(True)
                li.setFont(f)
                li.setIcon(icon("play", theme.ACCENT, size=16))
                cur_row = self.progs.count()
            elif p.get("archive") and it.archive:
                li.setIcon(icon("catchup", theme.ACCENT, size=16))
                li.setToolTip(_("Geçmiş yayını izle (catch-up)"))
            elif p["end"] < now:
                li.setForeground(self.palette().mid())
            self.progs.addItem(li)
        if not progs:
            li = QListWidgetItem(_("Yayın akışı bulunamadı"))
            li.setFlags(Qt.ItemFlag.NoItemFlags)
            self.progs.addItem(li)
        if cur_row >= 0:
            self.progs.scrollToItem(self.progs.item(cur_row), QAbstractItemView.ScrollHint.PositionAtTop)
        self._refresh_info()

    def _prog_clicked(self, li):
        p = li.data(ItemRole)
        if not p or not self.current:
            return
        now = time.time()
        if p["start"] <= now < p["end"]:
            self.playRequested.emit(self.current, True)
        elif p.get("archive") and self.current.archive:
            self.catchupRequested.emit(self.current, p)

    def _context(self, idx, pos):
        it = idx.data(ItemRole)
        if it is None:
            return
        fav = self.ctx.userdata.is_favorite(LIVE, it.id)
        m = QMenu(self)
        a_fav = m.addAction(icon("star" if not fav else "star_border"),
                            _("Favorilerden çıkar") if fav else _("Favorilere ekle"))
        a_full = m.addAction(icon("fullscreen"), _("Tam ekran izle"))
        a_prev = m.addAction(icon("play"), _("Önizlemede oynat"))
        a_rm = m.addAction(icon("delete", theme.DANGER), _("Son izlenenlerden kaldır")) \
            if self.category == RECENT_CAT else None
        a_multi = m.addAction(icon("grid"), _("Çoklu ekranda izle")) if IS_WINDOWS else None
        locked = it.id in self.lib.lock_sets(LIVE)[1]
        a_lock = m.addAction(icon("lock", theme.WARN), _("Kilidi kaldır") if locked else _("PIN ile kilitle"))
        act = m.exec(pos)
        if act is a_fav:
            self.ctx.userdata.toggle_favorite(LIVE, it.id, it.brief())
            self.view.viewport().update()
            if self.category == FAV_CAT:
                self.apply(keep_scroll=True)
            self.ctx.favorites_changed()
        elif act is a_full:
            self.select(it, play=False)
            self.playRequested.emit(it, True)
        elif act is a_prev:
            self.select(it, play=True)
        elif a_rm is not None and act is a_rm:
            self.ctx.userdata.remove_history(LIVE, it.id)
            self.apply(keep_scroll=True)
        elif a_multi is not None and act is a_multi:
            self.multiviewRequested.emit(it)
        elif act is a_lock:
            self.ctx.win.toggle_lock(LIVE, it)
            self.view.viewport().update()

    def _clear_recent(self):
        r = QMessageBox.question(self, _("Son izlenen"), _("Son izlenenler listesi temizlensin mi?"))
        if r == QMessageBox.StandardButton.Yes:
            self.ctx.userdata.clear_history(LIVE)
            self.apply()

    def toggle_favorite_current(self):
        if self.current:
            self.ctx.userdata.toggle_favorite(LIVE, self.current.id, self.current.brief())
            self.view.viewport().update()
            if self.category == FAV_CAT:
                self.apply(keep_scroll=True)
