"""Ortak arayüz bileşenleri."""
import time

from ..i18n import N_, _
from ..images import loader
from ..qt import (QAbstractItemView, QAbstractListModel, QApplication, QBrush, QButtonGroup, QColor, QComboBox, QDialog,
                  QEvent, QFont, QFontMetrics, QFrame, QGridLayout, QHBoxLayout, QLabel, QLinearGradient,
                  QLineEdit, QListView, QModelIndex, QPainter, QPainterPath, QPen, QPushButton, QRect, QRectF,
                  QScrollArea, QScroller, QScrollerProperties, QSize, QStyle, QStyledItemDelegate, Qt, QTimer,
                  QToolButton, QVBoxLayout, QWidget, Signal)
from . import theme
from .icons import icon, pixmap

ItemRole = Qt.ItemDataRole.UserRole


def enable_kinetic(widget, mouse_drag):
    """Dokunmatik ekranlarda parmakla kaydırmayı etkinleştirir."""
    target = widget.viewport() if hasattr(widget, "viewport") else widget
    gesture = (QScroller.ScrollerGestureType.LeftMouseButtonGesture if mouse_drag
               else QScroller.ScrollerGestureType.TouchGesture)
    QScroller.grabGesture(target, gesture)
    sc = QScroller.scroller(target)
    props = sc.scrollerProperties()
    off = QScrollerProperties.OvershootPolicy.OvershootAlwaysOff
    props.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy, off)
    props.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy, off)
    props.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor, 0.35)
    props.setScrollMetric(QScrollerProperties.ScrollMetric.DragStartDistance, 0.004)
    sc.setScrollerProperties(props)


class ItemModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.items):
            return None
        it = self.items[index.row()]
        if role == ItemRole:
            return it
        if role == Qt.ItemDataRole.DisplayRole:
            return it.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return it.name
        return None

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def append(self, items):
        if not items:
            return
        n = len(self.items)
        self.beginInsertRows(QModelIndex(), n, n + len(items) - 1)
        self.items.extend(items)
        self.endInsertRows()

    def row_of(self, item_id):
        for i, it in enumerate(self.items):
            if it.id == item_id:
                return i
        return -1

    def refresh(self):
        if self.items:
            self.dataChanged.emit(self.index(0), self.index(len(self.items) - 1))


def _rounded(p, rect, radius, brush):
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    p.fillPath(path, brush)


def _initials(name):
    parts = [w for w in name.replace("|", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in parts[:2]).upper() or "TV"


class ChannelDelegate(QStyledItemDelegate):
    def __init__(self, ctx, parent=None, compact=False):
        super().__init__(parent)
        self.ctx = ctx  # .userdata, .epg, .playing_id, .show_epg
        self.compact = compact
        self.k = max(1.0, theme.SCALE)  # büyük yazıda satırlar da büyür
        self.row_h = round(62 * self.k)
        self.f_name = QFont(theme.FONT)
        self.f_name.setPixelSize(theme.fs(15))
        self.f_name.setWeight(QFont.Weight.DemiBold)
        self.f_sub = QFont(theme.FONT)
        self.f_sub.setPixelSize(theme.fs(12))
        self.f_num = QFont(theme.FONT)
        self.f_num.setPixelSize(theme.fs(13))
        self.f_num.setWeight(QFont.Weight.Bold)
        self.f_ini = QFont(theme.FONT)
        self.f_ini.setPixelSize(theme.fs(13))
        self.f_ini.setWeight(QFont.Weight.Bold)

    def sizeHint(self, option, index):
        return QSize(200, self.row_h)

    def paint(self, p, option, index):
        it = index.data(ItemRole)
        if it is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        playing = it.id == self.ctx.playing_id
        if selected or playing:
            _rounded(p, r, 10, QBrush(QColor(48, 213, 200, 34)))
            bar = QRect(r.left(), r.top() + 12, 3, r.height() - 24)
            _rounded(p, bar, 1.5, QBrush(QColor(theme.ACCENT)))
        elif hover:
            _rounded(p, r, 10, QBrush(QColor(theme.SURFACE2)))

        x = r.left() + 10
        if not self.compact:
            p.setFont(self.f_num)
            p.setPen(QColor(theme.ACCENT if playing else theme.DIM))
            num = str(it.num or index.row() + 1)
            p.drawText(QRect(x, r.top(), 34, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, num)
            x += 36
        # Logo
        lr = QRect(x, r.top() + (r.height() - 42) // 2, 56, 42)
        _rounded(p, lr, 8, QBrush(QColor(theme.SURFACE3)))
        pm = loader().get(it.logo, 112, 84) if it.logo else None
        if pm is not None:
            dpr = pm.devicePixelRatio() or 1
            pw, ph = pm.width() / dpr, pm.height() / dpr
            s = min((lr.width() - 6) / max(pw, 1), (lr.height() - 6) / max(ph, 1), 1.0)
            w, h = int(pw * s), int(ph * s)
            p.drawPixmap(QRect(lr.center().x() - w // 2 + 1, lr.center().y() - h // 2 + 1, w, h), pm)
        else:
            p.setFont(self.f_ini)
            p.setPen(QColor(theme.MUTED))
            p.drawText(lr, Qt.AlignmentFlag.AlignCenter, _initials(it.name))
        x = lr.right() + 12

        fav = self.ctx.userdata.is_favorite("live", it.id) if self.ctx.userdata else False
        locked = bool(self.ctx.library and self.ctx.library.item_locked("live", it))
        right = r.right() - 8 - (18 if fav else 0) - (18 if locked else 0)
        tw = right - x
        cur = None
        if self.ctx.show_epg and self.ctx.epg is not None:
            cur, _nxt = self.ctx.epg.now_next(it)
        p.setFont(self.f_name)
        p.setPen(QColor(theme.ACCENT if playing else theme.TEXT))
        fm = QFontMetrics(self.f_name)
        name = fm.elidedText(it.name, Qt.TextElideMode.ElideRight, tw)
        if cur:
            k = self.k
            p.drawText(QRect(x, r.top() + round(7 * k), tw, round(21 * k)), Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(self.f_sub)
            p.setPen(QColor(theme.MUTED))
            fs = QFontMetrics(self.f_sub)
            p.drawText(QRect(x, r.top() + round(28 * k), tw, round(17 * k)), Qt.AlignmentFlag.AlignVCenter,
                       fs.elidedText(cur["title"], Qt.TextElideMode.ElideRight, tw))
            now = time.time()
            frac = max(0.0, min(1.0, (now - cur["start"]) / max(1, cur["end"] - cur["start"])))
            pb = QRect(x, r.bottom() - 9, min(tw, 140), 3)
            _rounded(p, pb, 1.5, QBrush(QColor(theme.SURFACE3)))
            _rounded(p, QRect(pb.left(), pb.top(), int(pb.width() * frac), 3), 1.5, QBrush(QColor(theme.ACCENT_LO)))
        else:
            p.drawText(QRect(x, r.top(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter, name)
        ix = r.right() - 22
        if fav:
            p.drawPixmap(QRect(ix, r.center().y() - 8, 16, 16), pixmap("star", theme.ACCENT, 16))
            ix -= 20
        if locked:
            p.drawPixmap(QRect(ix, r.center().y() - 8, 16, 16), pixmap("lock", theme.WARN, 16))
        p.restore()


class PosterDelegate(QStyledItemDelegate):
    def __init__(self, ctx, kind, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kind = kind
        self.cell = QSize(140, 248)
        self.f_title = QFont(theme.FONT)
        self.f_title.setPixelSize(theme.fs(13))
        self.f_title.setWeight(QFont.Weight.DemiBold)
        self.f_meta = QFont(theme.FONT)
        self.f_meta.setPixelSize(theme.fs(12))
        self.f_ini = QFont(theme.FONT)
        self.f_ini.setPixelSize(theme.fs(26))
        self.f_ini.setWeight(QFont.Weight.Black)
        self.f_badge = QFont(theme.FONT)
        self.f_badge.setPixelSize(theme.fs(11))
        self.f_badge.setWeight(QFont.Weight.Bold)

    def sizeHint(self, option, index):
        return self.cell

    def paint(self, p, option, index):
        it = index.data(ItemRole)
        if it is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cr = option.rect
        pad = 6
        pw = cr.width() - pad * 2
        ph = int(pw * 1.5)
        pr = QRect(cr.left() + pad, cr.top() + pad, pw, ph)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        path = QPainterPath()
        path.addRoundedRect(QRectF(pr), 10, 10)
        pm = loader().get(it.logo, pw * 2, ph * 2) if it.logo else None
        if pm is not None:
            p.setClipPath(path)
            p.fillRect(pr, QColor(theme.SURFACE2))
            dpr = 2.0
            iw, ih = pm.width() / dpr, pm.height() / dpr
            s = max(pw / max(iw, 1), ph / max(ih, 1))
            w, h = int(iw * s), int(ih * s)
            p.drawPixmap(QRect(pr.center().x() - w // 2, pr.center().y() - h // 2, w, h), pm)
            p.setClipping(False)
        else:
            g = QLinearGradient(pr.topLeft().toPointF(), pr.bottomRight().toPointF())
            g.setColorAt(0, QColor("#1f2a2e"))
            g.setColorAt(1, QColor("#111518"))
            p.fillPath(path, QBrush(g))
            p.setFont(self.f_ini)
            p.setPen(QColor(48, 213, 200, 150))
            p.drawText(pr, Qt.AlignmentFlag.AlignCenter, _initials(it.name))
        if hover or selected:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawRoundedRect(QRectF(pr).adjusted(1, 1, -1, -1), 10, 10)
        # Puan rozeti
        if it.rating:
            txt = f"★ {it.rating:.1f}"
            br = QRect(pr.right() - 50, pr.top() + 6, 44, 18)
            _rounded(p, br, 6, QBrush(QColor(0, 0, 0, 170)))
            p.setFont(self.f_badge)
            p.setPen(QColor(theme.WARN))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, txt)
        if self.ctx.userdata and self.ctx.userdata.is_favorite(self.kind, it.id):
            fr = QRect(pr.left() + 6, pr.top() + 6, 22, 22)
            _rounded(p, fr, 6, QBrush(QColor(0, 0, 0, 170)))
            p.drawPixmap(fr.adjusted(3, 3, -3, -3), pixmap("star", theme.ACCENT, 16))
        if self.ctx.library and self.ctx.library.item_locked(self.kind, it):
            lr = QRect(pr.left() + 6, pr.bottom() - 30, 22, 22)
            _rounded(p, lr, 6, QBrush(QColor(0, 0, 0, 170)))
            p.drawPixmap(lr.adjusted(3, 3, -3, -3), pixmap("lock", theme.WARN, 16))
        # İzleme ilerlemesi
        if self.kind == "movie" and self.ctx.userdata:
            prog = self.ctx.userdata.get_progress(f"movie:{it.id}")
            if prog and prog.get("dur"):
                frac = min(1.0, prog["pos"] / prog["dur"])
                bar = QRect(pr.left() + 8, pr.bottom() - 9, pw - 16, 4)
                _rounded(p, bar, 2, QBrush(QColor(0, 0, 0, 160)))
                _rounded(p, QRect(bar.left(), bar.top(), int(bar.width() * frac), 4), 2, QBrush(QColor(theme.ACCENT)))
        # Başlık
        fm = QFontMetrics(self.f_title)
        tr = QRect(cr.left() + pad, pr.bottom() + 6, pw, fm.lineSpacing() * 2 + 2)
        p.setFont(self.f_title)
        p.setPen(QColor(theme.ACCENT if hover else theme.TEXT))
        lines = self._wrap(it.name, fm, pw)
        p.drawText(tr, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, "\n".join(lines))
        if it.year and it.year not in it.name:
            p.setFont(self.f_meta)
            p.setPen(QColor(theme.DIM))
            p.drawText(QRect(tr.left(), tr.top() + fm.lineSpacing() * len(lines) + 2, pw, theme.fs(16)),
                       Qt.AlignmentFlag.AlignHCenter, it.year)
        p.restore()

    @staticmethod
    def _wrap(text, fm, width):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if fm.horizontalAdvance(t) <= width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if len(lines) == 1:
                    break
        if cur and len(lines) < 2:
            lines.append(cur)
        if len(lines) == 2:
            rest = text[len(lines[0]):].strip()
            lines[1] = fm.elidedText(rest, Qt.TextElideMode.ElideRight, width)
        return lines or [text]


LANG_NAMES = {"TR": N_("Türkçe"), "EN": N_("İngilizce"), "DE": N_("Almanca"), "FR": N_("Fransızca"),
              "IT": N_("İtalyanca"), "ES": N_("İspanyolca"), "NL": N_("Felemenkçe"), "AR": N_("Arapça"),
              "PT": N_("Portekizce"), "PL": N_("Lehçe"), "RU": N_("Rusça"), "AL": N_("Arnavutça"),
              "GR": N_("Yunanca"), "RO": N_("Rumence"), "BG": N_("Bulgarca"), "SE": N_("İsveççe"),
              "NO": N_("Norveççe"), "DK": N_("Danca"), "FI": N_("Fince"), "IN": N_("Hintçe"), "PK": N_("Urduca"),
              "IR": N_("Farsça"), "KU": N_("Kürtçe"), "AZ": N_("Azerice"), "RS": N_("Sırpça"), "HR": N_("Hırvatça"),
              "BA": N_("Boşnakça"), "UA": N_("Ukraynaca"), "HU": N_("Macarca"), "CZ": N_("Çekçe")}


def lang_label(code):
    name = LANG_NAMES.get(code)
    return f"{_(name)} ({code})" if name else code


class LangFilterBox(QComboBox):
    """İçerik dili filtresi; listede en az iki dil bulunursa görünür."""

    changedLang = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip(_("İçerik dili"))
        self.setMinimumContentsLength(7)
        self.currentIndexChanged.connect(lambda i: self.changedLang.emit(self.itemData(i) or ""))
        self.hide()

    def set_languages(self, langs, current=""):
        """langs: [(kod, adet)]"""
        self.blockSignals(True)
        self.clear()
        self.addItem(_("Tüm diller"), "")
        for code, n in langs:
            self.addItem(f"{lang_label(code)}  ·  {n}", code)
        i = self.findData(current) if current else 0
        self.setCurrentIndex(max(0, i))
        self.blockSignals(False)
        self.setVisible(len(langs) >= 2)
        return self.itemData(self.currentIndex()) or ""


class ListView(QListView):
    """Görseller geldiğinde görünür alanı yeniden çizen liste."""

    nearEnd = Signal()
    contextRequested = Signal(object, object)  # QModelIndex, global QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lp_timer = QTimer(self)
        self._lp_timer.setSingleShot(True)
        self._lp_timer.setInterval(650)
        self._lp_timer.timeout.connect(self._long_press)
        self._lp_pos = None
        self._lp_fired = False
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(200)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalScrollBar().setSingleStep(24)
        loader().loaded.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self._check_end)

    def _check_end(self, v):
        sb = self.verticalScrollBar()
        if sb.maximum() > 0 and v > sb.maximum() - 600:
            self.nearEnd.emit()

    # Sağ tık ve dokunmatik uzun basma ile bağlam menüsü
    def contextMenuEvent(self, e):
        idx = self.indexAt(e.pos())
        if idx.isValid():
            self.contextRequested.emit(idx, e.globalPos())

    def mousePressEvent(self, e):
        self._lp_fired = False
        if e.button() == Qt.MouseButton.LeftButton:
            self._lp_pos = e.position().toPoint()
            self._lp_timer.start()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._lp_timer.isActive() and self._lp_pos is not None:
            if (e.position().toPoint() - self._lp_pos).manhattanLength() > 12:
                self._lp_timer.stop()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._lp_timer.stop()
        if self._lp_fired:
            self._lp_fired = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _long_press(self):
        if self._lp_pos is None:
            return
        idx = self.indexAt(self._lp_pos)
        if idx.isValid():
            self._lp_fired = True
            self.contextRequested.emit(idx, self.viewport().mapToGlobal(self._lp_pos))


class GridView(ListView):
    def __init__(self, delegate, parent=None):
        super().__init__(parent)
        self.delegate = delegate
        self.setItemDelegate(delegate)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setSpacing(0)
        self.setSelectionRectVisible(False)
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        w = self.width() - self.verticalScrollBar().sizeHint().width() - 6
        target = 150 if w > 900 else 136
        cols = max(2, w // target)
        cw = w // cols
        ch = int((cw - 12) * 1.5) + 12 + round(42 * max(1.0, theme.SCALE))
        size = QSize(cw, ch)
        if self.delegate.cell != size:
            self.delegate.cell = size
            self.setGridSize(size)
            self.doItemsLayout()


class ChipBar(QWidget):
    """Üstte yatay kaydırılabilir kategori çipleri."""

    selected = Signal(str)

    def __init__(self, parent=None, mouse_drag=False):
        super().__init__(parent)
        self.setObjectName("ChipBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btn_l = QToolButton()
        self.btn_l.setIcon(icon("chev_left"))
        self.btn_l.setAutoRepeat(True)
        self.btn_l.clicked.connect(lambda: self._scroll(-260))
        self.btn_r = QToolButton()
        self.btn_r.setIcon(icon("chev_right"))
        self.btn_r.setAutoRepeat(True)
        self.btn_r.clicked.connect(lambda: self._scroll(260))
        self.btn_all = QToolButton()
        self.btn_all.setIcon(icon("grid"))
        self.btn_all.setToolTip(_("Tüm kategoriler"))
        self.btn_all.clicked.connect(self._open_picker)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setFixedHeight(42)
        self.inner = QWidget()
        self.inner.setObjectName("ChipBar")
        self.row = QHBoxLayout(self.inner)
        self.row.setContentsMargins(2, 4, 2, 4)
        self.row.setSpacing(6)
        self.row.addStretch(1)
        self.area.setWidget(self.inner)
        enable_kinetic(self.area, True)
        lay.addWidget(self.btn_l)
        lay.addWidget(self.area, 1)
        lay.addWidget(self.btn_r)
        lay.addWidget(self.btn_all)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        self.cats = []
        self.current = None

    def _scroll(self, dx):
        sb = self.area.horizontalScrollBar()
        sb.setValue(sb.value() + dx)

    def wheelEvent(self, e):
        self._scroll(-e.angleDelta().y())

    def set_categories(self, cats, current=None):
        """cats: [(id, ad, ikon_adı_ya_da_None)]"""
        for b in self.buttons.values():
            self.group.removeButton(b)
            b.deleteLater()
        self.buttons = {}
        self.cats = cats
        for cid, name, ic in cats:
            b = QPushButton(name)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if ic:
                b.setIcon(icon(ic, theme.MUTED, "#06201e", 16))
                b.setIconSize(QSize(15, 15))
            b.clicked.connect(lambda _=False, c=cid: self._click(c))
            self.row.insertWidget(self.row.count() - 1, b)
            self.group.addButton(b)
            self.buttons[cid] = b
        if current not in self.buttons and cats:
            current = cats[0][0]
        self.set_current(current, emit=False)

    def set_current(self, cid, emit=True):
        self.current = cid
        b = self.buttons.get(cid)
        if b:
            b.setChecked(True)
            QTimer.singleShot(0, lambda: self.area.ensureWidgetVisible(b, 60, 0))
        if emit:
            self.selected.emit(cid)

    def _click(self, cid):
        self.current = cid
        self.selected.emit(cid)

    def _open_picker(self):
        dlg = CategoryPicker(self.cats, self.current, self.window())
        if dlg.exec() and dlg.chosen is not None:
            self.set_current(dlg.chosen)


class CategoryPicker(QDialog):
    def __init__(self, cats, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Kategoriler"))
        self.setModal(True)
        self.chosen = None
        self.cats = cats
        lay = QVBoxLayout(self)
        self.search = SearchBox(_("Kategori ara…"))
        lay.addWidget(self.search)
        from ..qt import QListWidget, QListWidgetItem  # noqa: PLC0415
        self.lst = QListWidget()
        self.lst.setUniformItemSizes(True)
        enable_kinetic(self.lst, True)
        self._QLI = QListWidgetItem
        lay.addWidget(self.lst, 1)
        self.search.textChanged.connect(self._fill)
        self.lst.itemClicked.connect(self._pick)
        self.lst.itemActivated.connect(self._pick)
        self._fill("")
        if parent:
            self.resize(min(520, parent.width() - 40), parent.height() - 60)

    def _fill(self, q):
        from ..library import fold  # noqa: PLC0415
        self.lst.clear()
        fq = fold(q)
        for cid, name, _ic in self.cats:
            if fq and fq not in fold(name):
                continue
            it = self._QLI(name)
            it.setData(ItemRole, cid)
            it.setSizeHint(QSize(100, 40))
            self.lst.addItem(it)

    def _pick(self, it):
        self.chosen = it.data(ItemRole)
        self.accept()


class ElidedLabel(QLabel):
    """Sığmayan metni "…" ile kısaltan etiket; dar pencerede yanındaki düğmeleri dışarı itmez."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full)
        self._elide()
        self.updateGeometry()

    def text(self):
        return self._full

    def sizeHint(self):
        sh = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 6, sh.height())

    def minimumSizeHint(self):
        return QSize(30, super().minimumSizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._elide()

    def _elide(self):
        QLabel.setText(self, self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                                           max(10, self.width())))


class SearchBox(QLineEdit):
    debounced = Signal(str)

    def __init__(self, placeholder=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Search")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setPlaceholderText(placeholder or _("Ara…"))
        self.setClearButtonEnabled(True)
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(280)
        self._t.timeout.connect(lambda: self.debounced.emit(self.text()))
        self.textChanged.connect(lambda _: self._t.start())

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.drawPixmap(10, (self.height() - 16) // 2, pixmap("search", theme.MUTED, 16))


class StatusView(QWidget):
    """Yükleniyor / boş / hata durumları için orta mesaj."""

    retry = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from .player import Spinner  # noqa: PLC0415
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.spinner = Spinner(self, 48)
        lay.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.ic = QLabel()
        self.ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.ic)
        self.msg = QLabel()
        self.msg.setObjectName("Muted")
        self.msg.setStyleSheet(theme.scaled("font-size:15px;"))
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.btn = QPushButton(_("Tekrar dene"))
        self.btn.setObjectName("Primary")
        self.btn.clicked.connect(self.retry.emit)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)

    def loading(self, text=None):
        self.spinner.show()
        self.ic.hide()
        self.btn.hide()
        self.msg.setText(text or _("Yükleniyor…"))

    def empty(self, text, ic="info"):
        self.spinner.hide()
        self.ic.setPixmap(pixmap(ic, theme.DIM, 48))
        self.ic.show()
        self.btn.hide()
        self.msg.setText(text)

    def error(self, text):
        self.empty(text, "info")
        self.btn.show()


class OnScreenKeyboard(QFrame):
    """Dokunmatik ekran için Türkçe ekran klavyesi."""

    ROWS = [
        list("1234567890"),
        list("qwertyuıopğü"),
        list("asdfghjklşi"),
        ["⇧"] + list("zxcvbnmöç") + ["⌫"],
    ]
    SYM = [
        list("1234567890"),
        list("!@#$%&*()=+"),
        list("-_/\\:;\"'?~"),
        ["⇧"] + list("<>[]{}|,^") + ["⌫"],
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Osk")
        self.shift = False
        self.sym = False
        self.target = None
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(8, 6, 8, 8)
        self.v.setSpacing(5)
        self.grid_host = QWidget()
        self.grid = QVBoxLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(5)
        self.v.addWidget(self.grid_host)
        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        for label, txt, stretch in (("?123", None, 1), ("http://", "http://", 1), (".", ".", 1), ("/", "/", 1),
                                    (":", ":", 1), (_("boşluk"), " ", 4), (".com", ".com", 1), ("@", "@", 1)):
            b = self._key(label, alt=label in ("?123", "http://", ".com"))
            if txt is None:
                b.clicked.connect(self._toggle_sym)
                self.btn_sym = b
            else:
                b.clicked.connect(lambda _=False, t=txt: self._type(t))
            bottom.addWidget(b, stretch)
        ok = self._key(_("Tamam"), alt=True)
        ok.clicked.connect(self._enter)
        hide = self._key("▼", alt=True)
        hide.clicked.connect(self.hide)
        bottom.addWidget(ok, 1)
        bottom.addWidget(hide, 1)
        self.v.addLayout(bottom)
        self._build()
        self.hide()

    def _key(self, label, alt=False):
        b = QPushButton(label)
        b.setObjectName("KeyAlt" if alt else "Key")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setAutoRepeat(label == "⌫")
        return b

    def _build(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            lay = item.layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        rows = self.SYM if self.sym else self.ROWS
        for row in rows:
            h = QHBoxLayout()
            h.setSpacing(5)
            for k in row:
                label = k
                if not self.sym and self.shift and len(k) == 1:
                    label = {"i": "İ", "ı": "I"}.get(k, k.upper())
                b = self._key(label, alt=k in ("⇧", "⌫"))
                if k == "⇧":
                    b.clicked.connect(self._toggle_shift)
                elif k == "⌫":
                    b.clicked.connect(self._backspace)
                else:
                    b.clicked.connect(lambda _=False, t=label: self._type(t))
                h.addWidget(b, 1)
            self.grid.addLayout(h)

    def _toggle_shift(self):
        self.shift = not self.shift
        self._build()

    def _toggle_sym(self):
        self.sym = not self.sym
        self.btn_sym.setText("abc" if self.sym else "?123")
        self._build()

    def _edit(self):
        w = QApplication.focusWidget()
        return w if isinstance(w, QLineEdit) else self.target

    def _type(self, t):
        e = self._edit()
        if e:
            e.insert(t)
        if self.shift:
            self.shift = False
            self._build()

    def _backspace(self):
        e = self._edit()
        if e:
            e.backspace()

    def _enter(self):
        e = self._edit()
        if e:
            e.returnPressed.emit()
            e.editingFinished.emit()
        self.hide()

    def attach(self, edit):
        self.target = edit
        self.show()
        self.raise_()
