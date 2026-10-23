"""İndirilenler: devam eden/tamamlanan indirmeler ve canlı yayın kayıtları."""
import html
import os
import shutil
import subprocess
import sys

from ..downloads import DONE, FAILED, PAUSED, QUEUED, RESOLVING, RUNNING, STATUS_TEXT
from ..i18n import _
from ..qt import (QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSize,
                  Qt, QTimer, QToolButton, QVBoxLayout, QWidget, Signal)
from . import theme
from .icons import icon
from .player import fmt_time
from .vod_page import PosterLabel
from .widgets import StatusView, enable_kinetic


def human(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


class TaskRow(QFrame):
    play = Signal(str)

    def __init__(self, dm, task, userdata=None, parent=None):
        super().__init__(parent)
        self.dm = dm
        self.userdata = userdata
        self.tid = task["id"]
        self.setObjectName("Panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)
        self.poster = PosterLabel(46, 68)
        self.poster.set_url(task.get("poster"))
        lay.addWidget(self.poster)
        col = QVBoxLayout()
        col.setSpacing(4)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        self.title = QLabel(task["title"])
        trow.addWidget(self.title)
        self.badge = QLabel()
        trow.addWidget(self.badge)
        trow.addStretch(1)
        col.addLayout(trow)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        col.addWidget(self.bar)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        self.btn_play = self._btn("play", _("Oynat"), lambda: self.play.emit(self.tid))
        self.btn_pause = self._btn("pause", _("Duraklat"), lambda: self.dm.pause(self.tid))
        self.btn_resume = self._btn("download", _("Devam et"), lambda: self.dm.resume(self.tid))
        self.btn_folder = self._btn("folder", _("Klasörü aç"), self._open_folder)
        self.btn_del = self._btn("delete", _("Sil"), self._delete)
        for b in (self.btn_play, self.btn_pause, self.btn_resume, self.btn_folder, self.btn_del):
            lay.addWidget(b)
        self.update_task(task)

    def _btn(self, ic, tip, fn, color=None):
        b = QToolButton()
        b.setIcon(icon(ic, color or theme.TEXT))
        b.setIconSize(QSize(22, 22))
        b.setToolTip(tip)
        b.setMinimumSize(40, 40)
        b.clicked.connect(fn)
        return b

    def update_task(self, t):
        st = t["status"]
        total, done = t.get("total") or 0, t.get("done") or 0
        key = t.get("key") or ""
        ud = self.userdata
        watched = bool(st == DONE and ud and ud.is_watched(key))
        prog = ud.get_progress(key) if st == DONE and ud and key else None
        watching = bool(prog and prog.get("dur") and not watched)
        # Durum rengi: indiriliyor mavi, indirildi turkuaz, izleniyor mor, izlendi yeşil
        if st == DONE:
            if watched:
                color, label = theme.WATCHED, "✓ " + _("İzlendi")
            elif watching:
                color = theme.WATCHING
                label = "▶ " + _("İzleniyor %{n}", n=int(prog["pos"] / prog["dur"] * 100))
            else:
                color, label = theme.ACCENT, "✓ " + _("İndirildi")
        elif st == FAILED:
            color, label = theme.DANGER, _("Hata")
        elif st == PAUSED:
            color, label = theme.WARN, _("Duraklatıldı")
        else:
            color, label = theme.INFO, _(STATUS_TEXT.get(st, st))
        self.badge.setText(label)
        self.poster.set_tint(color)
        self.badge.setStyleSheet(theme.scaled(f"background:{theme.rgba(color, 0.16)}; color:{color}; border-radius:8px;"
                                              "padding:2px 8px; font-size:12px; font-weight:700;"))
        self.title.setStyleSheet(theme.scaled("font-weight:700;font-size:15px;"
                                              + (f"color:{theme.MUTED};" if watched else "")))
        self.setStyleSheet(f"#Panel{{background:{theme.BG if watched else theme.SURFACE};"
                           f"border-left:4px solid {color}; border-radius:12px;}}"
                           f"QProgressBar::chunk{{background:{color}; border-radius:3px;}}")
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done / total * 1000))
        else:
            self.bar.setRange(0, 0 if st == RUNNING else 1)
            self.bar.setValue(1 if st == DONE else 0)
        txt = _(STATUS_TEXT.get(st, st))
        if st == RUNNING:
            spd = t.get("speed") or 0
            txt += f"  ·  {human(done)}" + (f" / {human(total)}" if total else "")
            if spd:
                txt += f"  ·  {human(spd)}/s"
                if total:
                    eta = int((total - done) / max(spd, 1))
                    txt += "  ·  " + _("{m} dk {s} sn kaldı", m=eta // 60, s=eta % 60)
        elif st == DONE:
            txt = human(total or done)
            if watching:
                # Çubuk izlenen kısmı gösterir
                self.bar.setRange(0, prog["dur"])
                self.bar.setValue(prog["pos"])
                txt += "  ·  " + _("{pos} / {dur} izlendi", pos=fmt_time(prog["pos"]), dur=fmt_time(prog["dur"]))
            if t.get("meta", {}).get("record"):
                txt = _("Kayıt") + "  ·  " + txt
        elif st == FAILED:
            txt += f": {t.get('error', '')}"
        elif st == PAUSED and total:
            txt += "  ·  " + _("%{n}", n=int(done / total * 100))
        self.bar.setVisible(not watched)
        self.info.setText(html.escape(txt))
        self.info.setStyleSheet(f"color:{theme.DANGER};" if st == FAILED else "")
        self.btn_play.setVisible(st == DONE)
        self.btn_pause.setVisible(st in (RUNNING, QUEUED, RESOLVING))
        self.btn_resume.setVisible(st in (PAUSED, FAILED))
        self.btn_folder.setVisible(st == DONE)
        self.btn_resume.setToolTip(_("Tekrar dene") if st == FAILED else _("Devam et"))

    def _open_folder(self):
        t = self.dm.find(self.tid)
        if not t:
            return
        d = os.path.dirname(t["path"])
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(t["path"])])
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", d])
        except OSError:
            pass

    def _delete(self):
        t = self.dm.find(self.tid)
        if not t:
            return
        r = QMessageBox.question(self, _("Sil"), _("“{title}” silinsin mi?\nDosya da diskten kaldırılacak.",
                                                   title=t["title"]))
        if r == QMessageBox.StandardButton.Yes:
            self.dm.remove(self.tid, delete_file=True)


class DownloadsPage(QWidget):
    playFile = Signal(str, str, str)  # yol, başlık, izleme konumu anahtarı

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.dm = ctx.downloads
        self.rows = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel(_("İndirilenler"))
        t.setObjectName("Title")
        head.addWidget(t)
        self.count = QLabel()
        self.count.setObjectName("Badge")
        head.addWidget(self.count)
        head.addSpacing(12)
        legend = QLabel("   ".join(f"<span style='color:{c}'>●</span> {html.escape(t)}" for c, t in (
            (theme.INFO, _("İndiriliyor")), (theme.ACCENT, _("İndirildi")),
            (theme.WATCHING, _("İzleniyor")), (theme.WATCHED, _("İzlendi")))))
        legend.setObjectName("Muted")
        legend.setTextFormat(Qt.TextFormat.RichText)
        head.addWidget(legend)
        head.addStretch(1)
        self.disk = QLabel()
        self.disk.setObjectName("Muted")
        head.addWidget(self.disk)
        root.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        enable_kinetic(self.scroll, ctx.settings.get("touch_scroll"))
        self.inner = QWidget()
        self.list = QVBoxLayout(self.inner)
        self.list.setContentsMargins(0, 0, 4, 0)
        self.list.setSpacing(6)
        self.list.addStretch(1)
        self.scroll.setWidget(self.inner)
        self.status = StatusView()
        self.status.empty(_("Henüz indirme yok.\nFilm veya dizi detayından “İndir”e dokunun.\n"
                            "Canlı yayınları oynatıcıdaki kayıt düğmesiyle kaydedebilirsiniz."), "download")
        root.addWidget(self.scroll, 1)
        root.addWidget(self.status, 1)
        self.dm.listChanged.connect(self.rebuild)
        self.dm.changed.connect(self._changed)
        # Sayfa açıkken klasörden elle silinen dosyaları da yakala
        self._watch = QTimer(self)
        self._watch.setInterval(5000)
        self._watch.timeout.connect(self.dm.prune_missing)
        self.rebuild()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.dm.prune_missing():
            self.rebuild()  # izlenme durumları ve profil değişmiş olabilir
        self._watch.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._watch.stop()

    def rebuild(self):
        for r in self.rows.values():
            r.deleteLater()
        self.rows = {}
        for t in self.dm.tasks:
            row = TaskRow(self.dm, t, self.ctx.userdata)
            row.play.connect(self._play)
            self.list.insertWidget(self.list.count() - 1, row)
            self.rows[t["id"]] = row
        has = bool(self.dm.tasks)
        self.scroll.setVisible(has)
        self.status.setVisible(not has)
        self.count.setText(str(len(self.dm.tasks)))
        self._disk()

    def _disk(self):
        d = self.ctx.settings.get("download_dir")
        p = d
        while p and not os.path.exists(p):
            p = os.path.dirname(p)
        try:
            u = shutil.disk_usage(p or os.path.expanduser("~"))
            self.disk.setText(_("Boş alan: {size}", size=human(u.free)))
        except OSError:
            self.disk.setText("")
        self.disk.setToolTip(d)

    def _changed(self, tid):
        t = self.dm.find(tid)
        row = self.rows.get(tid)
        if t and row:
            row.update_task(t)
            if t["status"] == DONE:
                self._disk()

    def _play(self, tid):
        t = self.dm.find(tid)
        if t and os.path.exists(t["path"]):
            self.playFile.emit(t["path"], t["title"], t.get("key") or "")
        elif t:
            self.dm.prune_missing()
            QMessageBox.warning(self, _("Dosya yok"), _("Dosya bulunamadı, silinmiş olabilir."))
