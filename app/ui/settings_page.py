"""Menü seçenekleri: profiller, hesap, oynatıcı, görünüm, indirme, ebeveyn kontrolü."""
import os
import shutil

from ..config import APP_AUTHOR, APP_NAME, APP_VERSION, IMAGE_CACHE_DIR
from ..providers import LIVE, MOVIE, SERIES
from ..qt import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
                  QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, Qt,
                  QVBoxLayout, QWidget, Signal)
from . import theme
from .icons import icon
from .widgets import SearchBox, enable_kinetic


def card(title, ic=None):
    f = QFrame()
    f.setObjectName("Card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 12, 16, 14)
    v.setSpacing(10)
    h = QHBoxLayout()
    if ic:
        li = QLabel()
        li.setPixmap(icon(ic, theme.ACCENT).pixmap(20, 20))
        h.addWidget(li)
    t = QLabel(title)
    t.setObjectName("H2")
    h.addWidget(t)
    h.addStretch(1)
    v.addLayout(h)
    return f, v


class HiddenCategoriesDialog(QDialog):
    def __init__(self, cats, hidden, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kategorileri gizle")
        lay = QVBoxLayout(self)
        info = QLabel("İşaretli kategoriler listelerde gösterilmez.")
        info.setObjectName("Muted")
        lay.addWidget(info)
        self.search = SearchBox("Kategori ara…")
        lay.addWidget(self.search)
        self.lst = QListWidget()
        enable_kinetic(self.lst, True)
        for c in cats:
            it = QListWidgetItem(c.name)
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c.id in hidden else Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        self.lst.itemClicked.connect(lambda it: it.setCheckState(
            Qt.CheckState.Unchecked if it.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked))
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        c = QPushButton("İptal")
        c.clicked.connect(self.reject)
        ok = QPushButton("Kaydet")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addWidget(c)
        row.addWidget(ok)
        lay.addLayout(row)
        if parent:
            self.resize(min(520, parent.width() - 40), parent.height() - 60)

    def _filter(self, q):
        q = q.casefold()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setHidden(bool(q) and q not in it.text().casefold())

    def hidden_ids(self):
        return {self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.CheckState.Checked}


class SettingsPage(QWidget):
    profileSwitch = Signal(str)
    profileAdd = Signal()
    profileEdit = Signal(str)
    profileDelete = Signal(str)
    refreshRequested = Signal()
    categoriesChanged = Signal()
    quitRequested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        s = ctx.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 0)
        t = QLabel("Menü")
        t.setObjectName("Title")
        outer.addWidget(t)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        enable_kinetic(scroll, s.get("touch_scroll"))
        outer.addWidget(scroll, 1)
        inner = QWidget()
        scroll.setWidget(inner)
        cols = QHBoxLayout(inner)
        cols.setContentsMargins(0, 6, 6, 14)
        cols.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self._left, self._right, self._cols = left, right, cols
        self._lc, self._rc = [], []
        self._two_cols = None

        # --- Profiller
        f, v = card("Profiller", "person")
        self.profile_list = QListWidget()
        self.profile_list.setMinimumHeight(110)
        self.profile_list.setMaximumHeight(170)
        v.addWidget(self.profile_list)
        row = QHBoxLayout()
        for label, ic, fn in (("Kullan", "check", self._use), ("Ekle", "add", self.profileAdd.emit),
                              ("Düzenle", "edit", self._edit), ("Sil", "delete", self._delete)):
            b = QPushButton(label)
            b.setIcon(icon(ic))
            if label == "Sil":
                b.setObjectName("Danger")
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        self._lc.append(f)

        # --- Hesap
        f, v = card("Hesap bilgisi", "info")
        self.account = QLabel("—")
        self.account.setTextFormat(Qt.TextFormat.RichText)
        self.account.setWordWrap(True)
        v.addWidget(self.account)
        row = QHBoxLayout()
        b = QPushButton("  Listeyi yenile")
        b.setIcon(icon("refresh"))
        b.setObjectName("Primary")
        b.clicked.connect(self.refreshRequested.emit)
        row.addWidget(b)
        self.cache_box = QComboBox()
        for h, label in ((1, "1 saat"), (6, "6 saat"), (12, "12 saat"), (24, "24 saat"), (72, "3 gün")):
            self.cache_box.addItem(f"Otomatik yenile: {label}", h)
        self._select(self.cache_box, s.get("cache_hours"))
        self.cache_box.currentIndexChanged.connect(lambda i: s.set("cache_hours", self.cache_box.itemData(i)))
        row.addWidget(self.cache_box, 1)
        v.addLayout(row)
        self._lc.append(f)

        # --- Ebeveyn kontrolü
        f, v = card("Ebeveyn kontrolü ve kategoriler", "lock")
        row = QHBoxLayout()
        b = QPushButton("PIN belirle")
        b.clicked.connect(self._set_pin)
        row.addWidget(b)
        self.pin_state = QLabel()
        self.pin_state.setObjectName("Muted")
        row.addWidget(self.pin_state, 1)
        v.addLayout(row)
        self.chk_adult = QCheckBox("Yetişkin kategorilerini PIN ile kilitle")
        self.chk_adult.setChecked(bool(s.get("lock_adult")))
        self.chk_adult.toggled.connect(self._lock_adult)
        v.addWidget(self.chk_adult)
        row = QHBoxLayout()
        for label, sec in (("Canlı TV", LIVE), ("Filmler", MOVIE), ("Diziler", SERIES)):
            b = QPushButton(label)
            b.setIcon(icon("eye_off"))
            b.clicked.connect(lambda _=False, x=sec: self._hide_cats(x))
            row.addWidget(b)
        v.addWidget(QLabel("Kategori gizle:"))
        v.addLayout(row)
        self._lc.append(f)

        # --- Oynatıcı
        f, v = card("Oynatıcı", "play")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.hw = QComboBox()
        from ..config import IS_ARM, PI_HWDEC  # noqa: PLC0415
        hw_opts = [("auto-safe", "Otomatik (önerilen)")]
        if IS_ARM:
            hw_opts = [(PI_HWDEC, "Raspberry Pi donanım çözücü (önerilen)")]
        for k, label in (*hw_opts, ("auto-copy", "Otomatik – kopya modu"),
                         ("auto", "Otomatik – tüm yöntemler"), ("no", "Kapalı (yazılımsal)")):
            self.hw.addItem(label, k)
        self._select(self.hw, s.get("hwdec"))
        self.hw.currentIndexChanged.connect(self._hwdec)
        form.addRow("Donanım hızlandırma", self.hw)
        self.buf = QComboBox()
        for sec in (2, 4, 8, 15, 30):
            self.buf.addItem(f"{sec} saniye", sec)
        self._select(self.buf, s.get("buffer_seconds"))
        self.buf.currentIndexChanged.connect(lambda i: self._restart_note("buffer_seconds", self.buf.itemData(i)))
        form.addRow("Tampon (buffer)", self.buf)
        self.fmt = QComboBox()
        self.fmt.addItem("MPEG-TS (.ts)", "ts")
        self.fmt.addItem("HLS (.m3u8)", "m3u8")
        self._select(self.fmt, s.get("live_format"))
        self.fmt.currentIndexChanged.connect(self._live_format)
        form.addRow("Canlı yayın formatı", self.fmt)
        self.quality = QComboBox()
        for k, label in (("max", "En yüksek"), ("6000000", "En fazla 6 Mbit/s"), ("4000000", "En fazla 4 Mbit/s"),
                         ("2000000", "En fazla 2 Mbit/s (yavaş internet)"), ("1000000", "En fazla 1 Mbit/s"),
                         ("min", "En düşük")):
            self.quality.addItem(label, k)
        self._select(self.quality, str(s.get("hls_bitrate")))
        self.quality.setToolTip("Birden çok kalitesi olan (HLS) yayınlarda seçilecek en yüksek kalite. "
                                "Yavaş internette takılmayı azaltır.")
        self.quality.currentIndexChanged.connect(self._quality)
        form.addRow("Yayın kalitesi", self.quality)
        self.ua = QLineEdit(s.get("user_agent"))
        self.ua.editingFinished.connect(lambda: s.set("user_agent", self.ua.text().strip() or "VLC/3.0.20 LibVLC/3.0.20"))
        form.addRow("User-Agent", self.ua)
        v.addLayout(form)
        self.chk_recon = QCheckBox("Yayın koparsa otomatik yeniden bağlan")
        self.chk_recon.setChecked(bool(s.get("auto_reconnect")))
        self.chk_recon.toggled.connect(lambda c: s.set("auto_reconnect", c))
        v.addWidget(self.chk_recon)
        self._rc.append(f)

        # --- Görünüm
        f, v = card("Görünüm ve kontrol", "tv")
        for key, label in (("start_fullscreen", "Uygulamayı tam ekran başlat"),
                           ("touch_scroll", "Parmakla/sürükleyerek kaydırma (dokunmatik)"),
                           ("osk_enabled", "Ekran klavyesi (dokunmatik ekran için)"),
                           ("show_epg_in_list", "Kanal listesinde yayın bilgisini göster"),
                           ("animations", "Sayfa geçiş animasyonları"),
                           ("sidebar_compact", "Dar kenar çubuğu (sadece ikonlar)")):
            c = QCheckBox(label)
            c.setChecked(bool(s.get(key)))
            c.toggled.connect(lambda val, k=key: self._toggle(k, val))
            v.addWidget(c)
        self._rc.append(f)

        # --- İndirme
        f, v = card("İndirme", "download")
        row = QHBoxLayout()
        self.dl_dir = QLabel(s.get("download_dir"))
        self.dl_dir.setObjectName("Muted")
        self.dl_dir.setWordWrap(True)
        row.addWidget(self.dl_dir, 1)
        b = QPushButton("Değiştir")
        b.setIcon(icon("folder"))
        b.clicked.connect(self._pick_dir)
        row.addWidget(b)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Aynı anda indirme"))
        self.maxdl = QComboBox()
        for n in (1, 2, 3):
            self.maxdl.addItem(str(n), n)
        self._select(self.maxdl, s.get("max_downloads"))
        self.maxdl.currentIndexChanged.connect(lambda i: s.set("max_downloads", self.maxdl.itemData(i)))
        row.addWidget(self.maxdl)
        row.addStretch(1)
        v.addLayout(row)
        note = QLabel("Not: Birçok IPTV hesabı tek bağlantıya izin verir; indirme sürerken izleme yapılamayabilir.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self._rc.append(f)

        # --- Hakkında
        f, v = card("Hakkında", "info")
        self.cache_lbl = QLabel()
        self.cache_lbl.setObjectName("Muted")
        about = QLabel(f"<span style='font-size:16px;font-weight:800;color:{theme.ACCENT}'>{APP_NAME}</span>"
                       f"  <span style='color:{theme.MUTED}'>sürüm {APP_VERSION}</span><br>"
                       f"Geliştirici: <b>{APP_AUTHOR}</b><br>"
                       f"<span style='color:{theme.MUTED}'>Xtream Codes · M3U · Stalker Portal</span>")
        about.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(about)
        v.addWidget(self.cache_lbl)
        row = QHBoxLayout()
        b = QPushButton("Görsel önbelleğini temizle")
        b.clicked.connect(self._clear_images)
        row.addWidget(b)
        q = QPushButton("  Çıkış")
        q.setIcon(icon("power", theme.DANGER))
        q.setObjectName("Danger")
        q.clicked.connect(self.quitRequested.emit)
        row.addWidget(q)
        v.addLayout(row)
        self._rc.append(f)
        self._arrange(True)
        self.refresh()

    def _arrange(self, two_cols):
        """Geniş ekranda iki sütun, 1024x600 gibi dar ekranda tek sütun."""
        if two_cols == self._two_cols:
            return
        self._two_cols = two_cols
        for lay in (self._left, self._right):
            while lay.count():
                lay.takeAt(0)
        if two_cols:
            for c in self._lc:
                self._left.addWidget(c)
            for c in self._rc:
                self._right.addWidget(c)
            self._right.addStretch(1)
        else:
            for c in self._lc + self._rc:
                self._left.addWidget(c)
        self._left.addStretch(1)
        self._cols.setStretch(1, 1 if two_cols else 0)
        self._cols.setSpacing(12 if two_cols else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._arrange(self.width() >= 1000)

    @staticmethod
    def _select(box, value):
        for i in range(box.count()):
            if box.itemData(i) == value:
                box.setCurrentIndex(i)
                return

    def refresh(self):
        s = self.ctx.settings
        self.profile_list.clear()
        active = s.active_profile()
        for p in s.profiles:
            label = f"{p['name']}   ·   {p['type'].upper()}"
            it = QListWidgetItem(icon("check", theme.ACCENT) if active and p["id"] == active["id"] else icon("person"), label)
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.profile_list.addItem(it)
            if active and p["id"] == active["id"]:
                self.profile_list.setCurrentItem(it)
        self.pin_state.setText("PIN tanımlı" if s.get("parental_pin") else "PIN tanımlı değil")
        self.set_account(self.ctx.library.account if self.ctx.library else None)
        self._cache_size()

    def set_account(self, acc):
        lib = self.ctx.library
        if not lib:
            self.account.setText("—")
            return
        rows = [f"<b>{lib.profile.get('name')}</b>  <span style='color:{theme.MUTED}'>({lib.profile.get('type')})</span>"]
        if acc:
            if acc.get("status"):
                rows.append(f"Durum: <span style='color:{theme.ACCENT}'>{acc['status']}</span>")
            if acc.get("expires"):
                rows.append(f"Bitiş: {acc['expires']}")
            if acc.get("max_connections"):
                rows.append(f"Bağlantı: {acc.get('active_connections', '?')} / {acc['max_connections']}")
        counts = []
        for sec, label in ((LIVE, "kanal"), (MOVIE, "film"), (SERIES, "dizi")):
            if lib.items[sec]:
                counts.append(f"{len(lib.items[sec])} {label}")
        if counts:
            rows.append(" · ".join(counts))
        self.account.setText("<br>".join(rows))

    def _cache_size(self):
        total = 0
        try:
            for e in os.scandir(IMAGE_CACHE_DIR):
                total += e.stat().st_size
        except OSError:
            pass
        self.cache_lbl.setText(f"Görsel önbelleği: {total / 1e6:.0f} MB")

    def _selected_pid(self):
        it = self.profile_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _use(self):
        pid = self._selected_pid()
        if pid:
            self.profileSwitch.emit(pid)

    def _edit(self):
        pid = self._selected_pid()
        if pid:
            self.profileEdit.emit(pid)

    def _delete(self):
        pid = self._selected_pid()
        if pid:
            r = QMessageBox.question(self, "Profili sil", "Seçili profil silinsin mi?")
            if r == QMessageBox.StandardButton.Yes:
                self.profileDelete.emit(pid)

    def _toggle(self, key, val):
        self.ctx.settings.set(key, val)
        self.ctx.apply_setting(key)

    def _hwdec(self, i):
        self.ctx.settings.set("hwdec", self.hw.itemData(i))
        try:
            self.ctx.player.core.mpv["hwdec"] = self.hw.itemData(i)
        except Exception:  # noqa: BLE001
            pass

    def _quality(self, i):
        v = self.quality.itemData(i)
        self.ctx.settings.set("hls_bitrate", v)
        try:
            self.ctx.player.core.mpv["hls-bitrate"] = v  # sonraki açılan yayında geçerli olur
        except Exception:  # noqa: BLE001
            pass

    def _live_format(self, i):
        v = self.fmt.itemData(i)
        self.ctx.settings.set("live_format", v)
        if self.ctx.library and hasattr(self.ctx.library.provider, "live_ext"):
            self.ctx.library.provider.live_ext = v

    def _restart_note(self, key, val):
        self.ctx.settings.set(key, val)
        try:
            m = self.ctx.player.core.mpv
            m["cache-secs"] = str(val)
            m["demuxer-readahead-secs"] = str(val)
        except Exception:  # noqa: BLE001
            pass

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "İndirme klasörü", self.ctx.settings.get("download_dir"))
        if d:
            self.ctx.settings.set("download_dir", d)
            self.dl_dir.setText(d)

    def _set_pin(self):
        s = self.ctx.settings
        if s.get("parental_pin") and not self.ctx.ask_pin(self):
            return
        pin, ok = QInputDialog.getText(self, "PIN", "Yeni 4 haneli PIN (boş bırakırsanız kaldırılır):",
                                       QLineEdit.EchoMode.Password)
        if ok:
            pin = pin.strip()
            if pin and (not pin.isdigit() or len(pin) < 4):
                QMessageBox.warning(self, "PIN", "PIN en az 4 rakam olmalı.")
                return
            s.set("parental_pin", pin)
            self.refresh()
            self.categoriesChanged.emit()

    def _lock_adult(self, val):
        s = self.ctx.settings
        if val and not s.get("parental_pin"):
            QMessageBox.information(self, "PIN gerekli", "Önce bir PIN belirleyin.")
            self.chk_adult.setChecked(False)
            return
        if not val and s.get("lock_adult") and not self.ctx.ask_pin(self):
            self.chk_adult.blockSignals(True)
            self.chk_adult.setChecked(True)
            self.chk_adult.blockSignals(False)
            return
        s.set("lock_adult", val)
        self.categoriesChanged.emit()

    def _hide_cats(self, section):
        lib = self.ctx.library
        if not lib or not lib.cats[section]:
            QMessageBox.information(self, "Kategoriler", "Kategoriler henüz yüklenmedi.")
            return
        if self.ctx.settings.get("parental_pin") and not self.ctx.ask_pin(self):
            return
        dlg = HiddenCategoriesDialog(lib.cats[section], self.ctx.settings.hidden(lib.pid, section), self.window())
        if dlg.exec():
            self.ctx.settings.set_hidden(lib.pid, section, dlg.hidden_ids())
            self.categoriesChanged.emit()

    def _clear_images(self):
        shutil.rmtree(IMAGE_CACHE_DIR, ignore_errors=True)
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        self._cache_size()
