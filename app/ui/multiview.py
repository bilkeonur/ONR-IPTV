"""Çoklu ekran (Windows): aynı anda 4 canlı kanala kadar. Sesi tek kanal verir; bir kanal büyütülebilir,
kutular sürükle-bırak ile yer değiştirir. Kanal sayısı sağlayıcının izin verdiği bağlantı sayısıyla sınırlıdır."""
from ..i18n import _
from ..library import ALL_CAT
from ..providers import LIVE
from ..qt import (QApplication, QDialog, QDrag, QFrame, QGridLayout, QHBoxLayout, QLabel, QMimeData, QPushButton,
                  QSize, Qt, QToolButton, QVBoxLayout, QWidget, Signal)
from ..tasks import run_async
from . import theme
from .icons import icon
from .player import MpvPlayer, MpvSurface, Spinner
from .widgets import ChannelDelegate, ItemModel, ItemRole, ListView, SearchBox, enable_kinetic

MIME = "application/x-onriptv-cell"


class ChannelPicker(QDialog):
    """Kanal seçimi (arama ile)."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Kanal seç"))
        self.ctx = ctx
        self.chosen = None
        lay = QVBoxLayout(self)
        self.search = SearchBox(_("Kanal ara…"))
        self.search.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.search.debounced.connect(self._fill)
        lay.addWidget(self.search)
        self.model = ItemModel(self)
        self.view = ListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(ChannelDelegate(ctx))
        self.view.clicked.connect(self._pick)
        self.view.activated.connect(self._pick)
        enable_kinetic(self.view, True)
        lay.addWidget(self.view, 1)
        self._fill("")
        if parent:
            self.resize(min(560, parent.width() - 40), parent.height() - 60)

    def _fill(self, q):
        lib = self.ctx.library
        self.model.set_items(lib.filtered(LIVE, ALL_CAT, q.strip(), "default", self.ctx.userdata) if lib else [])

    def _pick(self, idx):
        self.chosen = idx.data(ItemRole)
        if self.chosen is not None:
            self.accept()


class MultiCell(QFrame):
    activated = Signal(object)         # hücre (ses bu hücreye geçer)
    maximizeRequested = Signal(object)
    pickRequested = Signal(object)
    closeRequested = Signal(object)
    swapRequested = Signal(object, int)  # hedef hücre, kaynak hücre sırası

    def __init__(self, settings, index, parent=None):
        super().__init__(parent)
        self.setObjectName("Cell")
        self.index = index
        self.settings = settings
        self.item = None
        self.url = ""
        self.active = False
        self._pending = None
        self._ready = False
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.core = MpvPlayer(settings)
        self.core.mpv.mute = True
        self.surface = MpvSurface(self.core, self)
        self.surface.ready.connect(self._surface_ready)
        self.core.bridge.prop.connect(self._on_prop)
        self.spinner = Spinner(self, 44)
        self.spinner.hide()

        self.bar = QFrame(self)
        self.bar.setObjectName("OsdTop")
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(8, 4, 6, 10)
        bl.setSpacing(2)
        self.ic_audio = QLabel()
        bl.addWidget(self.ic_audio)
        self.title = QLabel()
        self.title.setObjectName("OsdTitle")
        self.title.setStyleSheet(theme.scaled("font-size:14px;"))
        self.title.setCursor(Qt.CursorShape.OpenHandCursor)
        self.title.setToolTip(_("Yerini değiştirmek için sürükleyin"))
        bl.addWidget(self.title, 1)
        self.btn_change = self._btn("list", _("Kanalı değiştir"), lambda: self.pickRequested.emit(self))
        self.btn_max = self._btn("fullscreen", _("Büyüt / küçült"), lambda: self.maximizeRequested.emit(self))
        self.btn_close = self._btn("close", _("Kapat"), lambda: self.closeRequested.emit(self))
        for b in (self.btn_change, self.btn_max, self.btn_close):
            bl.addWidget(b)

        self.add_btn = QPushButton("  " + _("Kanal ekle"), self)
        self.add_btn.setIcon(icon("add", theme.ACCENT))
        self.add_btn.setIconSize(QSize(22, 22))
        self.add_btn.setMinimumHeight(44)
        self.add_btn.clicked.connect(lambda: self.pickRequested.emit(self))
        self._update()

    def _btn(self, ic, tip, fn):
        b = QToolButton()
        b.setIcon(icon(ic, "#ffffff"))
        b.setIconSize(QSize(20, 20))
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(fn)
        return b

    def resizeEvent(self, e):
        w, h = self.width(), self.height()
        self.surface.setGeometry(2, 2, w - 4, h - 4)
        self.bar.setGeometry(2, 2, w - 4, self.bar.sizeHint().height())
        self.spinner.move((w - self.spinner.width()) // 2, (h - self.spinner.height()) // 2)
        self.add_btn.adjustSize()
        self.add_btn.move((w - self.add_btn.width()) // 2, (h - self.add_btn.height()) // 2)

    def _update(self):
        has = self.item is not None
        self.add_btn.setVisible(not has)
        self.bar.setVisible(has)
        self.surface.setVisible(has)
        self.title.setText(self.item.name if has else "")
        self.ic_audio.setPixmap(icon("volume" if self.active else "volume_off",
                                     theme.ACCENT if self.active else "#ffffff").pixmap(18, 18))
        border = theme.ACCENT if self.active and has else theme.BORDER
        self.setStyleSheet(f"#Cell{{background:#000; border:2px solid {border}; border-radius:6px;}}")
        self.add_btn.raise_()
        self.bar.raise_()

    def set_active(self, active):
        self.active = active
        try:
            self.core.mpv.mute = not active
        except Exception:  # noqa: BLE001
            pass
        self._update()

    def play(self, item, url, headers):
        self.item = item
        self.url = url
        self.core.set_headers(headers)
        self.spinner.show()
        self.spinner.raise_()
        self._update()
        if self._ready:
            self.core.load(url)
        else:
            self._pending = url
            self.surface.update()

    def stop(self):
        self.item = None
        self.url = ""
        self._pending = None
        self.core.stop()
        self.spinner.hide()
        self._update()

    def _surface_ready(self):
        self._ready = True
        if self._pending:
            url, self._pending = self._pending, None
            self.core.load(url)

    def _on_prop(self, name, value):
        if name == "video-params" and value:
            self.spinner.hide()
        elif name == "paused-for-cache":
            self.spinner.setVisible(bool(value) and bool(self.url))

    def shutdown(self):
        self.core.stop()
        self.surface._free()
        self.core.terminate()

    # --- Fare: tık = ses, çift tık = büyüt, başlıktan sürükle = yer değiştir
    def mousePressEvent(self, e):
        self._press = e.position().toPoint()
        if self.item is not None:
            self.activated.emit(self)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.item is not None:
            self.maximizeRequested.emit(self)

    def mouseMoveEvent(self, e):
        press = getattr(self, "_press", None)
        if (e.buttons() & Qt.MouseButton.LeftButton and press is not None and self.item is not None
                and (e.position().toPoint() - press).manhattanLength() > QApplication.startDragDistance()):
            self._press = None
            drag = QDrag(self)
            md = QMimeData()
            md.setData(MIME, str(self.index).encode())
            drag.setMimeData(md)
            drag.setPixmap(self.title.grab())
            drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()

    def dropEvent(self, e):
        src = int(bytes(e.mimeData().data(MIME)).decode() or -1)
        if src != self.index:
            self.swapRequested.emit(self, src)
        e.acceptProposedAction()


class MultiViewPage(QWidget):
    back = Signal()

    def __init__(self, ctx, headers_fn, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.headers_fn = headers_fn
        self.cells = []
        self.order = []           # ızgaradaki sıra (hücre listesi)
        self.limit = 4
        self.maximized = None
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        b = QPushButton("  " + _("Geri"))
        b.setIcon(icon("back"))
        b.setObjectName("Flat")
        b.clicked.connect(self.back.emit)
        head.addWidget(b)
        t = QLabel(_("Çoklu ekran"))
        t.setObjectName("Title")
        head.addWidget(t)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        head.addWidget(self.info, 1)
        hint = QLabel(_("Tık: sesi seç · Çift tık: büyüt · Başlıktan sürükle: yer değiştir"))
        hint.setObjectName("Muted")
        head.addWidget(hint)
        root.addLayout(head)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        root.addWidget(self.grid_host, 1)

    def _ensure_cells(self):
        while len(self.cells) < self.limit:
            c = MultiCell(self.ctx.settings, len(self.cells))
            c.activated.connect(self._activate)
            c.maximizeRequested.connect(self._toggle_max)
            c.pickRequested.connect(self._pick)
            c.closeRequested.connect(self._close_cell)
            c.swapRequested.connect(self._swap)
            self.cells.append(c)
        self.order = [c for c in self.order if c in self.cells[:self.limit]]
        for c in self.cells[:self.limit]:
            if c not in self.order:
                self.order.append(c)

    def _relayout(self):
        while self.grid.count():
            self.grid.takeAt(0)
        for c in self.cells:
            c.hide()
        if self.maximized is not None:
            self.grid.addWidget(self.maximized, 0, 0)
            self.maximized.show()
            return
        n = len(self.order)
        cols = 1 if n == 1 else 2
        for i, c in enumerate(self.order):
            self.grid.addWidget(c, i // cols, i % cols)
            c.show()
        for r in range(2):
            self.grid.setRowStretch(r, 1)
            self.grid.setColumnStretch(r, 1)

    def open(self, limit, known, first_item=None):
        """limit: kullanılabilir bağlantı sayısı; known: sağlayıcı sınırı bildirdi mi."""
        self.limit = max(1, min(4, limit))
        self.maximized = None
        self._ensure_cells()
        txt = _("En fazla {n} kanal", n=self.limit)
        if known:
            txt += "  ·  " + _("sağlayıcının izin verdiği bağlantı sayısına göre")
        else:
            txt += "  ·  " + _("sağlayıcı bağlantı sınırını bildirmiyor; fazla bağlantıda yayın açılmayabilir")
        self.info.setText(txt)
        self._relayout()
        if first_item is not None:
            free = next((c for c in self.order if c.item is None), self.order[0])
            self._start(free, first_item)

    def close_all(self):
        for c in self.cells:
            if c.item is not None:
                c.stop()
            c.set_active(False)
        self.maximized = None

    def shutdown(self):
        for c in self.cells:
            c.shutdown()

    def _pick(self, cell):
        dlg = ChannelPicker(self.ctx, self.window())
        if dlg.exec() and dlg.chosen is not None:
            if not self.ctx.can_open(LIVE, dlg.chosen, self):
                return
            self._start(cell, dlg.chosen)

    def _start(self, cell, item):
        prov = self.ctx.library.provider if self.ctx.library else None
        if prov is None:
            return
        cell.item = item
        cell.spinner.show()
        cell._update()

        def done(url):
            if cell.item is item:
                cell.play(item, url, self.headers_fn(item))
                if not any(c.active and c.item is not None for c in self.cells):
                    self._activate(cell)

        def fail(e):
            if cell.item is item:
                cell.stop()
                self.ctx.win.toast(_("Yayın açılamadı") + f": {e}")

        run_async(prov.stream_url, item, on_done=done, on_error=fail)

    def _activate(self, cell):
        for c in self.cells:
            c.set_active(c is cell)

    def _toggle_max(self, cell):
        self.maximized = None if self.maximized is cell else cell
        self._relayout()

    def _close_cell(self, cell):
        was_active = cell.active
        if self.maximized is cell:
            self.maximized = None
        cell.stop()
        cell.set_active(False)
        if was_active:
            nxt = next((c for c in self.order if c.item is not None), None)
            if nxt:
                self._activate(nxt)
        self._relayout()

    def _swap(self, target, src_index):
        src = next((c for c in self.cells if c.index == src_index), None)
        if src is None or src not in self.order or target not in self.order:
            return
        a, b = self.order.index(src), self.order.index(target)
        self.order[a], self.order[b] = self.order[b], self.order[a]
        self._relayout()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if self.maximized is not None:
                self._toggle_max(self.maximized)
            else:
                self.back.emit()
        else:
            super().keyPressEvent(e)
