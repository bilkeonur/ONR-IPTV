"""İndirilenler: devam eden/tamamlanan indirmeler ve canlı yayın kayıtları."""
import os
import shutil
import subprocess
import sys

from ..downloads import DONE, FAILED, PAUSED, QUEUED, RESOLVING, RUNNING, STATUS_TEXT
from ..qt import (QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSize,
                  Qt, QToolButton, QVBoxLayout, QWidget, Signal)
from . import theme
from .icons import icon
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

    def __init__(self, dm, task, parent=None):
        super().__init__(parent)
        self.dm = dm
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
        self.title = QLabel(task["title"])
        self.title.setStyleSheet("font-weight:700;font-size:14px;")
        col.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        col.addWidget(self.bar)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        self.btn_play = self._btn("play", "Oynat", lambda: self.play.emit(self.tid), theme.ACCENT)
        self.btn_pause = self._btn("pause", "Duraklat", lambda: self.dm.pause(self.tid))
        self.btn_resume = self._btn("download", "Devam et", lambda: self.dm.resume(self.tid))
        self.btn_folder = self._btn("folder", "Klasörü aç", self._open_folder)
        self.btn_del = self._btn("delete", "Sil", self._delete)
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
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done / total * 1000))
        else:
            self.bar.setRange(0, 0 if st == RUNNING else 1)
            self.bar.setValue(1 if st == DONE else 0)
        txt = STATUS_TEXT.get(st, st)
        if st == RUNNING:
            spd = t.get("speed") or 0
            txt += f"  ·  {human(done)}" + (f" / {human(total)}" if total else "")
            if spd:
                txt += f"  ·  {human(spd)}/s"
                if total:
                    eta = int((total - done) / max(spd, 1))
                    txt += f"  ·  {eta // 60} dk {eta % 60} sn kaldı"
        elif st == DONE:
            txt += f"  ·  {human(total or done)}"
            if t.get("meta", {}).get("record"):
                txt = "Kayıt  ·  " + txt
        elif st == FAILED:
            txt += f": {t.get('error', '')}"
        elif st == PAUSED and total:
            txt += f"  ·  %{int(done / total * 100)}"
        self.info.setText(txt)
        self.info.setStyleSheet(f"color:{theme.DANGER};" if st == FAILED else "")
        self.btn_play.setVisible(st == DONE)
        self.btn_pause.setVisible(st in (RUNNING, QUEUED, RESOLVING))
        self.btn_resume.setVisible(st in (PAUSED, FAILED))
        self.btn_folder.setVisible(st == DONE)
        self.btn_resume.setToolTip("Tekrar dene" if st == FAILED else "Devam et")

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
        r = QMessageBox.question(self, "Sil", f"“{t['title']}” silinsin mi?\nDosya da diskten kaldırılacak.")
        if r == QMessageBox.StandardButton.Yes:
            self.dm.remove(self.tid, delete_file=True)


class DownloadsPage(QWidget):
    playFile = Signal(str, str)  # yol, başlık

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
        t = QLabel("İndirilenler")
        t.setObjectName("Title")
        head.addWidget(t)
        self.count = QLabel()
        self.count.setObjectName("Badge")
        head.addWidget(self.count)
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
        self.status.empty("Henüz indirme yok.\nFilm veya dizi detayından “İndir”e dokunun.\n"
                          "Canlı yayınları oynatıcıdaki kayıt düğmesiyle kaydedebilirsiniz.", "download")
        root.addWidget(self.scroll, 1)
        root.addWidget(self.status, 1)
        self.dm.listChanged.connect(self.rebuild)
        self.dm.changed.connect(self._changed)
        self.rebuild()

    def rebuild(self):
        for r in self.rows.values():
            r.deleteLater()
        self.rows = {}
        for t in self.dm.tasks:
            row = TaskRow(self.dm, t)
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
            self.disk.setText(f"Boş alan: {human(u.free)}")
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
            self.playFile.emit(t["path"], t["title"])
        elif t:
            QMessageBox.warning(self, "Dosya yok", "Dosya bulunamadı, silinmiş olabilir.")
