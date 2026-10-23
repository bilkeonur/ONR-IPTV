"""Genel arama: kanallar, filmler ve diziler tek ekranda."""
from ..i18n import _
from ..providers import LIVE, MOVIE, SERIES
from ..qt import QAbstractItemView, QHBoxLayout, QLabel, QListView, QScrollArea, QSize, Qt, QVBoxLayout, QWidget, Signal
from . import theme
from .widgets import ChannelDelegate, ItemModel, ItemRole, ListView, PosterDelegate, SearchBox, StatusView, enable_kinetic


class _Section(QWidget):
    """Başlık + sonuç listesi."""

    def __init__(self, title, view, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(6)
        h = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("H2")
        h.addWidget(self.title)
        self.count = QLabel()
        self.count.setObjectName("Badge")
        h.addWidget(self.count)
        h.addStretch(1)
        self.note = QLabel()
        self.note.setObjectName("Muted")
        h.addWidget(self.note)
        v.addLayout(h)
        v.addWidget(view)
        self.view = view


class SearchPage(QWidget):
    channelPicked = Signal(object)
    vodPicked = Signal(str, object)    # bölüm, öğe

    MAX_CHANNEL_ROWS = 6

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel(_("Ara"))
        t.setObjectName("Title")
        head.addWidget(t)
        self.box = SearchBox(_("Kanal, film veya dizi ara…"))
        self.box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.box.setMinimumHeight(40)
        self.box.debounced.connect(self._search)
        head.addWidget(self.box, 1)
        root.addLayout(head)

        self.status = StatusView()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        enable_kinetic(self.scroll, ctx.settings.get("touch_scroll"))
        inner = QWidget()
        self.scroll.setWidget(inner)
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(10)

        self.ch_model = ItemModel(self)
        self.ch_view = ListView()
        self.ch_view.setModel(self.ch_model)
        self.ch_delegate = ChannelDelegate(ctx)
        self.ch_view.setItemDelegate(self.ch_delegate)
        self.ch_view.clicked.connect(lambda idx: self._pick(LIVE, idx))
        self.ch_view.activated.connect(lambda idx: self._pick(LIVE, idx))
        self.sec_live = _Section(_("Kanallar"), self.ch_view)
        col.addWidget(self.sec_live)

        self.vod = {}
        for kind, title in ((MOVIE, _("Filmler")), (SERIES, _("Diziler"))):
            model = ItemModel(self)
            view = ListView()
            view.setModel(model)
            dlg = PosterDelegate(ctx, kind)
            dlg.cell = QSize(140, int(128 * 1.5) + 12 + round(42 * max(1.0, theme.SCALE)))
            view.setItemDelegate(dlg)
            view.setViewMode(QListView.ViewMode.IconMode)
            view.setFlow(QListView.Flow.LeftToRight)
            view.setWrapping(False)
            view.setMovement(QListView.Movement.Static)
            view.setGridSize(dlg.cell)
            view.setFixedHeight(dlg.cell.height() + 16)
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.horizontalScrollBar().setSingleStep(40)
            enable_kinetic(view, True)
            view.clicked.connect(lambda idx, k=kind: self._pick(k, idx))
            view.activated.connect(lambda idx, k=kind: self._pick(k, idx))
            sec = _Section(title, view)
            col.addWidget(sec)
            self.vod[kind] = (model, view, sec)
        col.addStretch(1)
        root.addWidget(self.scroll, 1)
        root.addWidget(self.status, 1)
        self._search("")

    def showEvent(self, e):
        super().showEvent(e)
        self.box.setFocus()
        self.box.selectAll()

    def _search(self, q):
        q = q.strip()
        lib = self.ctx.library
        if not q or lib is None:
            self.scroll.hide()
            self.status.show()
            self.status.empty(_("Kanal, film ve dizilerde aynı anda arayın."), "search")
            return
        if len(q) < 2:
            return
        total = 0
        chans = lib.search(LIVE, q, limit=80)
        self.ch_model.set_items(chans)
        self.ch_view.setFixedHeight(max(1, min(len(chans), self.MAX_CHANNEL_ROWS)) * self.ch_delegate.row_h + 6)
        self._fill(self.sec_live, chans, lib.is_paged(LIVE))
        total += len(chans)
        for kind, (model, view, sec) in self.vod.items():
            items = lib.search(kind, q, limit=60)
            model.set_items(items)
            view.horizontalScrollBar().setValue(0)
            self._fill(sec, items, lib.is_paged(kind))
            total += len(items)
        self.scroll.setVisible(bool(total))
        self.status.setVisible(not total)
        if not total:
            self.status.empty(_("“{q}” için sonuç bulunamadı.", q=q), "search")

    @staticmethod
    def _fill(sec, items, paged):
        sec.setVisible(bool(items))
        sec.count.setText(str(len(items)))
        sec.note.setText(_("Yalnızca açılmış kategorilerde arandı") if paged else "")

    def _pick(self, kind, idx):
        it = idx.data(ItemRole)
        if it is None:
            return
        if kind == LIVE:
            self.channelPicked.emit(it)
        else:
            self.vodPicked.emit(kind, it)
