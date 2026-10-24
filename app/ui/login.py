"""İlk açılış / profil ekleme ekranı: Xtream, M3U ve Stalker."""
from ..i18n import _
from ..providers import ProviderError, create_provider, parse_xtream_m3u_link, random_mac
from ..qt import (QButtonGroup, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                  QPushButton, QScrollArea, QStackedWidget, Qt, QVBoxLayout, QWidget, Signal)
from ..tasks import run_async
from . import theme
from .icons import icon
from .player import Spinner


class ProfileForm(QWidget):
    """Hesap bilgisi formu. Doğrulama başarılı olunca 'saved' sinyali profil sözlüğüyle gelir."""

    saved = Signal(dict)
    cancelled = Signal()

    def __init__(self, settings, profile=None, show_cancel=False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.profile = dict(profile or {})
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # Tür seçimi
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.type_group = QButtonGroup(self)
        self.type_btns = {}
        for key, label in (("xtream", "Xtream Codes"), ("m3u", _("M3U Liste")), ("stalker", "Stalker Portal")):
            b = QPushButton(label)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, k=key: self._set_type(k))
            self.type_group.addButton(b)
            self.type_btns[key] = b
            seg.addWidget(b, 1)
        lay.addLayout(seg)

        self.name = QLineEdit(self.profile.get("name", ""))
        self.name.setPlaceholderText(_("Örn: Ev IPTV"))
        self.stack = QStackedWidget()

        # Xtream
        xw = QWidget()
        xf = QFormLayout(xw)
        xf.setContentsMargins(0, 0, 0, 0)
        xf.setVerticalSpacing(10)
        self.x_url = QLineEdit()
        self.x_url.setPlaceholderText(_("http://sunucu.com:8080"))
        self.x_user = QLineEdit()
        self.x_user.setPlaceholderText(_("Kullanıcı adı"))
        self.x_pass = QLineEdit()
        self.x_pass.setPlaceholderText(_("Şifre"))
        self.x_pass.setEchoMode(QLineEdit.EchoMode.Password)
        xf.addRow(_("Sunucu URL"), self.x_url)
        xf.addRow(_("Kullanıcı adı"), self.x_user)
        xf.addRow(_("Şifre"), self.x_pass)
        self.stack.addWidget(xw)

        # M3U
        mw = QWidget()
        mf = QFormLayout(mw)
        mf.setContentsMargins(0, 0, 0, 0)
        mf.setVerticalSpacing(10)
        row = QHBoxLayout()
        self.m_url = QLineEdit()
        self.m_url.setPlaceholderText(_("http://.../liste.m3u  veya dosya yolu"))
        pick = QPushButton(_("Dosya"))
        pick.setIcon(icon("folder"))
        pick.clicked.connect(self._pick_file)
        row.addWidget(self.m_url, 1)
        row.addWidget(pick)
        self.m_epg = QLineEdit()
        self.m_epg.setPlaceholderText(_("İsteğe bağlı XMLTV EPG adresi"))
        mf.addRow("M3U URL", row)
        mf.addRow("EPG URL", self.m_epg)
        hint = QLabel(_("İpucu: get.php?username=…&password=… biçimindeki linkler otomatik olarak Xtream'e çevrilir."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        mf.addRow("", hint)
        self.stack.addWidget(mw)

        # Stalker
        sw = QWidget()
        sf = QFormLayout(sw)
        sf.setContentsMargins(0, 0, 0, 0)
        sf.setVerticalSpacing(10)
        self.s_url = QLineEdit()
        self.s_url.setPlaceholderText("http://portal.com:8080/c/")
        mrow = QHBoxLayout()
        self.s_mac = QLineEdit()
        self.s_mac.setPlaceholderText("00:1A:79:XX:XX:XX")
        gen = QPushButton(_("Üret"))
        gen.clicked.connect(lambda: self.s_mac.setText(random_mac()))
        mrow.addWidget(self.s_mac, 1)
        mrow.addWidget(gen)
        sf.addRow(_("Portal URL"), self.s_url)
        sf.addRow(_("MAC adresi"), mrow)
        self.stack.addWidget(sw)

        nf = QFormLayout()
        nf.setContentsMargins(0, 0, 0, 0)
        nf.addRow(_("Profil adı"), self.name)
        lay.addLayout(nf)
        lay.addWidget(self.stack)
        # Tüm formlardaki etiketler aynı genişlikte olsun ki alanlar hizalı dursun
        self.stack.setContentsMargins(0, 0, 0, 0)
        for form in (nf, xf, mf, sf):
            form.setHorizontalSpacing(12)
            for r in range(form.rowCount()):
                li = form.itemAt(r, QFormLayout.ItemRole.LabelRole)
                if li and li.widget():
                    li.widget().setFixedWidth(120)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        self.spinner = Spinner(self, 26)
        self.spinner.hide()
        srow = QHBoxLayout()
        srow.addWidget(self.spinner)
        srow.addWidget(self.status, 1)
        lay.addLayout(srow)

        brow = QHBoxLayout()
        brow.addStretch(1)
        if show_cancel:
            c = QPushButton(_("İptal"))
            c.clicked.connect(self.cancelled.emit)
            brow.addWidget(c)
        self.btn_ok = QPushButton(_("Bağlan ve Kaydet"))
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.setMinimumHeight(40)
        self.btn_ok.setMinimumWidth(180)
        self.btn_ok.clicked.connect(self._submit)
        brow.addWidget(self.btn_ok)
        lay.addLayout(brow)

        for e in (self.x_url, self.x_user, self.x_pass, self.m_url, self.s_url, self.s_mac, self.name):
            e.returnPressed.connect(self._submit)

        # Mevcut profili doldur
        t = self.profile.get("type", "xtream")
        if t == "xtream":
            self.x_url.setText(self.profile.get("url", ""))
            self.x_user.setText(self.profile.get("username", ""))
            self.x_pass.setText(self.profile.get("password", ""))
        elif t == "m3u":
            self.m_url.setText(self.profile.get("url", ""))
            self.m_epg.setText(self.profile.get("epg_url", ""))
        elif t == "stalker":
            self.s_url.setText(self.profile.get("url", ""))
            self.s_mac.setText(self.profile.get("mac", ""))
        if not self.s_mac.text():
            self.s_mac.setText(random_mac())
        self._set_type(t)

    def _set_type(self, t):
        self.type = t
        self.type_btns[t].setChecked(True)
        self.stack.setCurrentIndex({"xtream": 0, "m3u": 1, "stalker": 2}[t])
        self.status.setText("")

    def _pick_file(self):
        fn, _filter = QFileDialog.getOpenFileName(self, _("M3U dosyası seç"), "",
                                            _("Çalma listesi") + " (*.m3u *.m3u8);;" + _("Tümü") + " (*)")
        if fn:
            self.m_url.setText(fn)

    def _collect(self):
        p = {"id": self.profile.get("id"), "type": self.type}
        if self.type == "xtream":
            p.update(url=self.x_url.text().strip(), username=self.x_user.text().strip(),
                     password=self.x_pass.text().strip())
            if not (p["url"] and p["username"] and p["password"]):
                raise ValueError(_("URL, kullanıcı adı ve şifre gerekli."))
        elif self.type == "m3u":
            url = self.m_url.text().strip()
            if not url:
                raise ValueError(_("M3U adresi gerekli."))
            x = parse_xtream_m3u_link(url) if "get.php" in url else None
            if x:
                p.update(type="xtream", url=x[0], username=x[1], password=x[2], m3u_fallback=url)
            else:
                p.update(url=url, epg_url=self.m_epg.text().strip())
        else:
            p.update(url=self.s_url.text().strip(), mac=self.s_mac.text().strip().upper())
            if not (p["url"] and p["mac"]):
                raise ValueError(_("Portal URL ve MAC adresi gerekli."))
        p["name"] = self.name.text().strip() or {"xtream": "Xtream", "m3u": "M3U", "stalker": "Stalker"}[p["type"]]
        return p

    def _submit(self):
        try:
            p = self._collect()
        except ValueError as e:
            self.status.setStyleSheet(f"color:{theme.DANGER};")
            self.status.setText(str(e))
            return
        self.btn_ok.setEnabled(False)
        self.spinner.show()
        self.status.setStyleSheet("")
        self.status.setText(_("Bağlantı test ediliyor…"))
        ua = self.settings.get("user_agent")

        def work():
            try:
                return p, create_provider(p, ua).authenticate()
            except ProviderError:
                if p.get("m3u_fallback"):
                    q = dict(p, type="m3u", url=p["m3u_fallback"])
                    for k in ("username", "password", "m3u_fallback"):
                        q.pop(k, None)
                    return q, create_provider(q, ua).authenticate()
                raise

        run_async(work, on_done=self._ok, on_error=self._fail)

    def _ok(self, res):
        p, info = res
        p.pop("m3u_fallback", None)
        self.spinner.hide()
        self.btn_ok.setEnabled(True)
        self.status.setStyleSheet(f"color:{theme.ACCENT};")
        self.status.setText(_("Bağlantı başarılı."))
        self.saved.emit(p)

    def _fail(self, e):
        self.spinner.hide()
        self.btn_ok.setEnabled(True)
        self.status.setStyleSheet(f"color:{theme.DANGER};")
        self.status.setText(str(e) if isinstance(e, ProviderError) else _("Bağlantı hatası: {err}", err=e))


class WelcomePage(QWidget):
    """İlk açılışta gösterilen tam ekran karşılama + hesap ekleme."""

    saved = Signal(dict)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        # Ekran klavyesi açılınca (600 piksel yükseklikte) form ezilmesin, kaydırılabilsin
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        page.addWidget(self.scroll)
        inner = QWidget()
        self.scroll.setWidget(inner)
        outer = QHBoxLayout(inner)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.addStretch(1)
        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(620)
        card.setMinimumWidth(440)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(26, 20, 26, 20)
        cl.setSpacing(6)
        brand = QLabel("ONR<span style='color:#e6e9ec;font-weight:300'> IPTV</span>")
        brand.setObjectName("Brand")
        brand.setStyleSheet(theme.scaled("font-size:28px;"))
        cl.addWidget(brand)
        sub = QLabel(_("Başlamak için IP TV hesabınızı ekleyin. Bilgileriniz bu cihazda saklanır."))
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        cl.addWidget(sub)
        cl.addSpacing(8)
        self.form = ProfileForm(settings)
        self.form.saved.connect(self.saved.emit)
        cl.addWidget(self.form)
        col = QVBoxLayout()
        col.addStretch(1)
        col.addWidget(card)
        col.addStretch(1)
        outer.addLayout(col, 3)
        outer.addStretch(1)


class ProfileDialog(QDialog):
    def __init__(self, settings, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Profil düzenle") if profile else _("Yeni profil"))
        self.result_profile = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        self.form = ProfileForm(settings, profile, show_cancel=True)
        self.form.saved.connect(self._saved)
        self.form.cancelled.connect(self.reject)
        lay.addWidget(self.form)
        if parent:
            self.resize(min(600, parent.width() - 40), 0)

    def _saved(self, p):
        self.result_profile = p
        self.accept()
