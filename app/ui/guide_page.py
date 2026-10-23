"""TV Rehberi: kanallar x saat çizelgesi. Program bilgisi görünen satırlar için tembel yüklenir."""
import time
from collections import deque

from ..i18n import _, day_name
from ..images import loader
from ..qt import (QAbstractScrollArea, QBrush, QColor, QFont, QFontMetrics, QHBoxLayout, QLabel, QMessageBox,
                  QPainter, QPen, QPushButton, QRect, QRectF, Qt, QTimer, QVBoxLayout, QWidget, Signal)
from ..tasks import run_async
from . import theme
from .icons import icon, pixmap
from .widgets import _initials, enable_kinetic


class GuideGrid(QAbstractScrollArea):
    """Sol sütunda kanallar, üstte saat şeridi; programlar zaman eksenine göre kutular olarak çizilir."""

    programClicked = Signal(object, dict)   # kanal, program
    channelClicked = Signal(object)

    BEFORE = 3 * 3600      # şimdiden önce gösterilecek süre
    AFTER = 21 * 3600      # şimdiden sonra

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        k = max(1.0, theme.SCALE)
        self.row_h = round(58 * k)
        self.head_h = round(34 * k)
        self.col_w = round(200 * k)
        self.ppm = 4.0 * k                    # dakika başına piksel
        self.channels = []
        self.progs = {}                       # kanal id -> [program]
        self._queue = deque()
        self._loading = set()
        self._running = 0
        self._gen = 0
        self.t0 = 0
        self.f_name = QFont(theme.FONT)
        self.f_name.setPixelSize(theme.fs(13))
        self.f_name.setWeight(QFont.Weight.DemiBold)
        self.f_title = QFont(theme.FONT)
        self.f_title.setPixelSize(theme.fs(13))
        self.f_title.setWeight(QFont.Weight.DemiBold)
        self.f_time = QFont(theme.FONT)
        self.f_time.setPixelSize(theme.fs(11))
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(lambda _v: self.viewport().update())
        self.verticalScrollBar().setSingleStep(self.row_h // 2)
        self.horizontalScrollBar().setSingleStep(60)
        loader().loaded.connect(self.viewport().update)
        enable_kinetic(self, ctx.settings.get("touch_scroll"))
        tick = QTimer(self)
        tick.timeout.connect(self.viewport().update)
        tick.start(30000)

    # ------------------------------------------------------------ Veri
    def set_channels(self, channels):
        self._gen += 1
        self.channels = list(channels)
        self.progs = {}
        self._queue.clear()
        self._loading.clear()
        now = time.time()
        self.t0 = int((now - self.BEFORE) // 1800 * 1800)
        self._update_ranges()
        self.verticalScrollBar().setValue(0)
        self.scroll_to_now()
        self._request_visible()
        self.viewport().update()

    def _update_ranges(self):
        vw, vh = self.viewport().width(), self.viewport().height()
        total_w = int((self.BEFORE + self.AFTER) / 60 * self.ppm)
        self.horizontalScrollBar().setRange(0, max(0, total_w - (vw - self.col_w)))
        self.horizontalScrollBar().setPageStep(max(1, vw - self.col_w))
        self.verticalScrollBar().setRange(0, max(0, len(self.channels) * self.row_h - (vh - self.head_h)))
        self.verticalScrollBar().setPageStep(max(1, vh - self.head_h))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_ranges()
        self._request_visible()

    def scroll_to_now(self):
        x = int((time.time() - 1800 - self.t0) / 60 * self.ppm)
        self.horizontalScrollBar().setValue(max(0, x))

    def _visible_rows(self):
        top = self.verticalScrollBar().value()
        first = max(0, top // self.row_h)
        last = min(len(self.channels), (top + self.viewport().height()) // self.row_h + 2)
        return first, last

    def _on_scroll(self, _v):
        self._request_visible()
        self.viewport().update()

    def _request_visible(self):
        prov = self.ctx.library.provider if self.ctx.library else None
        if prov is None:
            return
        first, last = self._visible_rows()
        for it in self.channels[first:last]:
            if it.id not in self.progs and it.id not in self._loading:
                self._loading.add(it.id)
                self._queue.append(it)
        self._pump(prov)

    def _pump(self, prov):
        gen = self._gen
        while self._running < 4 and self._queue:
            it = self._queue.popleft()
            self._running += 1

            def done(progs, it=it):
                self._running -= 1
                if gen == self._gen:
                    self.progs[it.id] = progs or []
                    self._loading.discard(it.id)
                    self.viewport().update()
                self._pump(prov)

            def fail(_e, it=it):
                done([], it)

            run_async(prov.epg_table, it, on_done=done, on_error=fail)

    # ------------------------------------------------------------ Çizim
    def _x(self, t):
        return self.col_w + (t - self.t0) / 60 * self.ppm - self.horizontalScrollBar().value()

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.viewport().width(), self.viewport().height()
        p.fillRect(0, 0, w, h, QColor(theme.BG))
        now = time.time()
        top = self.verticalScrollBar().value()
        first, last = self._visible_rows()
        fm_t = QFontMetrics(self.f_title)
        t_end = self.t0 + self.BEFORE + self.AFTER
        # Programlar
        p.setClipRect(QRect(self.col_w, self.head_h, w - self.col_w, h - self.head_h))
        for row in range(first, last):
            it = self.channels[row]
            y = self.head_h + row * self.row_h - top
            progs = self.progs.get(it.id)
            if progs is None:
                p.setPen(QColor(theme.DIM))
                p.setFont(self.f_time)
                p.drawText(QRect(self.col_w + 10, y, 300, self.row_h), Qt.AlignmentFlag.AlignVCenter, _("Yükleniyor…"))
                continue
            if not progs:
                p.setPen(QColor(theme.DIM))
                p.setFont(self.f_time)
                p.drawText(QRect(self.col_w + 10, y, 300, self.row_h), Qt.AlignmentFlag.AlignVCenter,
                           _("Program bilgisi yok"))
                continue
            for pr in progs:
                if pr["end"] <= self.t0 or pr["start"] >= t_end:
                    continue
                x1, x2 = self._x(max(pr["start"], self.t0)), self._x(min(pr["end"], t_end))
                if x2 < self.col_w or x1 > w:
                    continue
                r = QRectF(x1 + 1, y + 3, max(2.0, x2 - x1 - 2), self.row_h - 6)
                live = pr["start"] <= now < pr["end"]
                past = pr["end"] <= now
                if live:
                    p.setBrush(QBrush(QColor(48, 213, 200, 40)))
                    p.setPen(QPen(QColor(theme.ACCENT), 1.2))
                else:
                    p.setBrush(QBrush(QColor(theme.SURFACE if past else theme.SURFACE2)))
                    p.setPen(QPen(QColor(theme.BORDER), 1))
                p.drawRoundedRect(r, 7, 7)
                tx = max(r.left(), self.col_w) + 8
                tw = r.right() - tx - 6
                if tw < 18:
                    continue
                arch = past and pr.get("archive") and it.archive
                if arch:
                    p.drawPixmap(int(tx), int(r.top() + 6), pixmap("catchup", theme.ACCENT, 14))
                    tx += 18
                    tw -= 18
                p.setFont(self.f_title)
                p.setPen(QColor(theme.TEXT if not past else theme.MUTED))
                p.drawText(QRectF(tx, r.top() + 4, tw, r.height() / 2), Qt.AlignmentFlag.AlignVCenter,
                           fm_t.elidedText(pr["title"], Qt.TextElideMode.ElideRight, int(tw)))
                p.setFont(self.f_time)
                p.setPen(QColor(theme.MUTED if not live else theme.ACCENT))
                p.drawText(QRectF(tx, r.top() + r.height() / 2, tw, r.height() / 2 - 4), Qt.AlignmentFlag.AlignVCenter,
                           time.strftime("%H:%M", time.localtime(pr["start"])) + " – "
                           + time.strftime("%H:%M", time.localtime(pr["end"])))
        # Şimdi çizgisi
        nx = self._x(now)
        p.setPen(QPen(QColor(theme.DANGER), 2))
        p.drawLine(int(nx), self.head_h, int(nx), h)
        p.setClipping(False)
        # Saat şeridi
        p.fillRect(0, 0, w, self.head_h, QColor(theme.SURFACE))
        p.setFont(self.f_time)
        t = self.t0
        while t <= t_end:
            x = self._x(t)
            if self.col_w - 60 < x < w:
                lt = time.localtime(t)
                label = time.strftime("%H:%M", lt)
                if lt.tm_hour == 0 and lt.tm_min == 0:
                    label = day_name(lt) + "  " + label
                p.setPen(QColor(theme.BORDER))
                p.drawLine(int(x), self.head_h - 8, int(x), self.head_h)
                if x >= self.col_w:
                    p.setPen(QColor(theme.MUTED))
                    p.drawText(QRect(int(x) + 4, 0, 160, self.head_h), Qt.AlignmentFlag.AlignVCenter, label)
            t += 1800
        if self.col_w < nx < w:
            p.setBrush(QBrush(QColor(theme.DANGER)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(nx - 22, self.head_h - 18, 44, 16), 5, 5)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(nx - 22, self.head_h - 18, 44, 16), Qt.AlignmentFlag.AlignCenter, time.strftime("%H:%M"))
        # Kanal sütunu
        p.fillRect(0, self.head_h, self.col_w, h - self.head_h, QColor(theme.SURFACE))
        p.setClipRect(QRect(0, self.head_h, self.col_w, h - self.head_h))
        fm_n = QFontMetrics(self.f_name)
        for row in range(first, last):
            it = self.channels[row]
            y = self.head_h + row * self.row_h - top
            playing = it.id == self.ctx.playing_id
            if playing:
                p.fillRect(QRect(0, y + 2, 3, self.row_h - 4), QColor(theme.ACCENT))
            lr = QRect(10, y + (self.row_h - 36) // 2, 48, 36)
            p.setBrush(QBrush(QColor(theme.SURFACE3)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(lr), 6, 6)
            pm = loader().get(it.logo, 96, 72) if it.logo else None
            if pm is not None:
                dpr = pm.devicePixelRatio() or 1
                pw, ph = pm.width() / dpr, pm.height() / dpr
                s = min((lr.width() - 4) / max(pw, 1), (lr.height() - 4) / max(ph, 1), 1.0)
                iw, ih = int(pw * s), int(ph * s)
                p.drawPixmap(QRect(lr.center().x() - iw // 2 + 1, lr.center().y() - ih // 2 + 1, iw, ih), pm)
            else:
                p.setFont(self.f_time)
                p.setPen(QColor(theme.MUTED))
                p.drawText(lr, Qt.AlignmentFlag.AlignCenter, _initials(it.name))
            p.setFont(self.f_name)
            p.setPen(QColor(theme.ACCENT if playing else theme.TEXT))
            nw = self.col_w - lr.right() - 18
            p.drawText(QRect(lr.right() + 10, y, nw, self.row_h), Qt.AlignmentFlag.AlignVCenter,
                       fm_n.elidedText(it.name, Qt.TextElideMode.ElideRight, nw))
            p.setPen(QColor(theme.BORDER))
            p.drawLine(0, y + self.row_h - 1, w, y + self.row_h - 1)
        p.setClipping(False)
        p.setPen(QColor(theme.BORDER))
        p.drawLine(self.col_w, 0, self.col_w, h)
        p.end()

    # ------------------------------------------------------------ Etkileşim
    def _hit(self, pos):
        if pos.y() < self.head_h:
            return None, None
        row = (pos.y() - self.head_h + self.verticalScrollBar().value()) // self.row_h
        if not 0 <= row < len(self.channels):
            return None, None
        it = self.channels[row]
        if pos.x() < self.col_w:
            return it, None
        t = self.t0 + (pos.x() - self.col_w + self.horizontalScrollBar().value()) / self.ppm * 60
        for pr in self.progs.get(it.id) or []:
            if pr["start"] <= t < pr["end"]:
                return it, pr
        return it, None

    def mousePressEvent(self, e):
        self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        pos = e.position().toPoint()
        press = getattr(self, "_press", None)
        if e.button() != Qt.MouseButton.LeftButton or press is None or (pos - press).manhattanLength() > 12:
            return  # parmakla kaydırma tıklama sayılmaz
        it, pr = self._hit(pos)
        if it is None:
            return
        if pr is None:
            self.channelClicked.emit(it)
        else:
            self.programClicked.emit(it, pr)

    def mouseMoveEvent(self, e):
        it, pr = self._hit(e.position().toPoint())
        tip = ""
        if pr is not None:
            tip = f"{time.strftime('%H:%M', time.localtime(pr['start']))} – " \
                  f"{time.strftime('%H:%M', time.localtime(pr['end']))}  {pr['title']}"
            if pr.get("desc"):
                tip += "\n\n" + pr["desc"][:400]
        self.viewport().setToolTip(tip)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if it is not None else Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, e):
        d = e.angleDelta()
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier or abs(d.x()) > abs(d.y()):
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - (d.x() or d.y()))
        else:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() - d.y())


class GuidePage(QWidget):
    back = Signal()
    playChannel = Signal(object)
    catchup = Signal(object, dict)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        b = QPushButton("  " + _("Geri"))
        b.setIcon(icon("back"))
        b.setObjectName("Flat")
        b.clicked.connect(self.back.emit)
        head.addWidget(b)
        t = QLabel(_("TV Rehberi"))
        t.setObjectName("Title")
        head.addWidget(t)
        self.sub = QLabel()
        self.sub.setObjectName("Muted")
        head.addWidget(self.sub)
        head.addStretch(1)
        now = QPushButton("  " + _("Şimdi"))
        now.setIcon(icon("history"))
        now.clicked.connect(lambda: self.grid.scroll_to_now())
        head.addWidget(now)
        root.addLayout(head)
        self.grid = GuideGrid(ctx)
        self.grid.channelClicked.connect(self.playChannel.emit)
        self.grid.programClicked.connect(self._program)
        root.addWidget(self.grid, 1)

    def open(self, channels, label=""):
        self.sub.setText(_("{n} kanal", n=len(channels)) + (f"  ·  {label}" if label else ""))
        self.grid.set_channels(channels)

    def _program(self, it, pr):
        now = time.time()
        if pr["start"] <= now < pr["end"]:
            self.playChannel.emit(it)
        elif pr["end"] <= now and pr.get("archive") and it.archive:
            self.catchup.emit(it, pr)
        else:
            t = time.localtime(pr["start"])
            when = f"{day_name(t)} {time.strftime('%H:%M', t)} – {time.strftime('%H:%M', time.localtime(pr['end']))}"
            msg = f"<b>{pr['title']}</b><br><span style='color:{theme.MUTED}'>{it.name} · {when}</span>"
            if pr.get("desc"):
                msg += f"<br><br>{pr['desc'][:600]}"
            if pr["end"] <= now:
                msg += f"<br><br><span style='color:{theme.MUTED}'>{_('Bu program için arşiv yok')}</span>"
            box = QMessageBox(self)
            box.setWindowTitle(_("Program"))
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setText(msg)
            box.exec()
