"""Koyu gri + turkuaz tema."""
import os
import re

from ..config import CACHE_DIR, IS_WINDOWS

BG = "#0e1012"         # siyaha yakın çok koyu gri
SURFACE = "#15181b"
SURFACE2 = "#1b1f23"
SURFACE3 = "#23282d"
BORDER = "#2a3036"
TEXT = "#e6e9ec"
MUTED = "#8b949e"
DIM = "#5b636b"
ACCENT = "#30d5c8"     # turkuaz
ACCENT_HI = "#5ee6db"
ACCENT_LO = "#1a9d93"
ACCENT_BG = "rgba(48, 213, 200, 0.14)"
DANGER = "#ff5c6c"
WARN = "#ffb547"

FONT = "Segoe UI" if IS_WINDOWS else "Noto Sans"

# Yazı boyutu ölçeği (Menü → Görünüm). Tüm piksel font boyutları fs() / scaled() üzerinden geçer.
SCALES = {"small": 0.92, "normal": 1.0, "large": 1.12, "xlarge": 1.25}
SCALE = 1.0


def set_scale(name):
    global SCALE
    SCALE = SCALES.get(name, 1.0)


def fs(px):
    """Ölçeklenmiş font boyutu (piksel)."""
    return max(1, round(px * SCALE))


_FS_RE = re.compile(r"font-size:\s*(\d+)px")


def scaled(css):
    """Stil metnindeki font-size değerlerini ölçeğe göre büyütür."""
    return _FS_RE.sub(lambda m: f"font-size:{fs(int(m.group(1)))}px", css)


def _asset(name, svg):
    """QSS'te kullanılacak küçük SVG görselleri önbellek klasörüne yazar."""
    d = os.path.join(CACHE_DIR, "ui")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
    except OSError:
        pass
    return path.replace("\\", "/")


ARROW = _asset("arrow.svg", f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8">'
                            f'<path d="M1 1l5 5 5-5" stroke="{MUTED}" stroke-width="2" fill="none" stroke-linecap="round"/></svg>')
SW_OFF = _asset("sw_off.svg", f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="22" viewBox="0 0 40 22">'
                              f'<rect x="1" y="1" width="38" height="20" rx="10" fill="{SURFACE3}" stroke="{BORDER}"/>'
                              f'<circle cx="11" cy="11" r="7" fill="{MUTED}"/></svg>')
SW_ON = _asset("sw_on.svg", f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="22" viewBox="0 0 40 22">'
                            f'<rect x="1" y="1" width="38" height="20" rx="10" fill="{ACCENT}"/>'
                            f'<circle cx="29" cy="11" r="7" fill="#06201e"/></svg>')
CHK_ON = _asset("chk_on.svg", f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">'
                              f'<rect x="1" y="1" width="18" height="18" rx="5" fill="{ACCENT}"/>'
                              f'<path d="M5 10l3.5 3.5L15 7" stroke="#06201e" stroke-width="2.4" fill="none" stroke-linecap="round"/></svg>')
CHK_OFF = _asset("chk_off.svg", f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">'
                                f'<rect x="1.5" y="1.5" width="17" height="17" rx="5" fill="{SURFACE3}" stroke="{BORDER}"/></svg>')

_QSS = f"""
* {{
    font-family: "{FONT}", "DejaVu Sans", sans-serif;
    color: {TEXT};
    outline: none;
}}
QMainWindow, #Root {{ background: {BG}; }}
QWidget#Page {{ background: {BG}; }}
QToolTip {{ background: {SURFACE3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px; border-radius: 6px; }}

/* --- Kenar çubuğu --- */
#Sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#Brand {{ font-size: 19px; font-weight: 800; color: {ACCENT}; letter-spacing: 1px; }}
#BrandSub {{ font-size: 11px; color: {MUTED}; letter-spacing: 3px; }}
#NavButton {{
    background: transparent; border: none; border-radius: 10px;
    padding: 0 12px; text-align: left; font-size: 15px; font-weight: 600; color: {MUTED};
    min-height: 44px;
}}
#NavButton:hover {{ background: {SURFACE2}; color: {TEXT}; }}
#NavButton:checked {{ background: {ACCENT_BG}; color: {ACCENT}; }}
#SideInfo {{ color: {MUTED}; font-size: 13px; }}
#Clock {{ color: {TEXT}; font-size: 24px; font-weight: 300; }}

/* --- Genel düğmeler --- */
QPushButton {{
    background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 14px; font-size: 14px; font-weight: 600; min-height: 22px;
}}
QPushButton:hover {{ background: {SURFACE3}; border-color: {ACCENT_LO}; }}
QPushButton:pressed {{ background: {ACCENT_LO}; }}
QPushButton:disabled {{ color: {DIM}; border-color: {SURFACE3}; }}
QPushButton#Primary {{ background: {ACCENT}; color: #06201e; border: none; }}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_LO}; }}
QPushButton#Danger {{ background: transparent; color: {DANGER}; border: 1px solid #5a2a31; }}
QPushButton#Danger:hover {{ background: #2a1519; }}
QPushButton#Flat, QToolButton#Flat {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QPushButton#Flat:hover, QToolButton#Flat:hover {{ background: {SURFACE3}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: rgba(255,255,255,0.08); }}
QToolButton:checked {{ background: {ACCENT_BG}; }}

/* --- Kategori çipleri --- */
#ChipBar {{ background: {BG}; }}
QPushButton#Chip {{
    background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 16px;
    padding: 5px 14px; font-size: 14px; font-weight: 600; color: {MUTED}; min-height: 20px;
}}
QPushButton#Chip:hover {{ color: {TEXT}; border-color: {ACCENT_LO}; }}
QPushButton#Chip:checked {{ background: {ACCENT}; color: #06201e; border-color: {ACCENT}; }}

/* --- Girdiler --- */
QLineEdit, QSpinBox, QComboBox {{
    background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 10px; font-size: 14px; selection-background-color: {ACCENT_LO};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit#Search {{ padding-left: 32px; border-radius: 18px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{ARROW}"); width: 12px; height: 8px; margin-right: 10px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_BG};
    selection-color: {ACCENT}; padding: 4px; outline: none;
}}
QCheckBox {{ font-size: 14px; spacing: 10px; }}
QCheckBox::indicator {{ width: 40px; height: 22px; image: url("{SW_OFF}"); }}
QCheckBox::indicator:checked {{ image: url("{SW_ON}"); }}
QListWidget::indicator {{ width: 20px; height: 20px; image: url("{CHK_OFF}"); }}
QListWidget::indicator:checked {{ image: url("{CHK_ON}"); }}

/* --- Listeler --- */
QListView, QListWidget, QTreeView {{ background: transparent; border: none; }}
QListView::item:selected {{ background: transparent; }}
QListWidget::item {{ border-radius: 8px; padding: 6px; }}
QListWidget::item:hover {{ background: {SURFACE2}; }}
QListWidget::item:selected {{ background: {ACCENT_BG}; color: {ACCENT}; }}

/* --- Kaydırma çubukları --- */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE3}; border-radius: 4px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_LO}; }}
QScrollBar:horizontal {{ background: transparent; height: 6px; margin: 1px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE3}; border-radius: 3px; min-width: 40px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractScrollArea {{ background: transparent; }}

/* --- Kartlar / paneller --- */
#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Panel {{ background: {SURFACE}; border-radius: 12px; }}
#Title {{ font-size: 23px; font-weight: 800; }}
#H2 {{ font-size: 17px; font-weight: 700; }}
#Muted {{ color: {MUTED}; font-size: 13px; }}
#Accent {{ color: {ACCENT}; font-weight: 700; }}
#Badge {{ background: {ACCENT_BG}; color: {ACCENT}; border-radius: 8px; padding: 2px 8px; font-size: 12px; font-weight: 700; }}

QProgressBar {{ background: {SURFACE3}; border: none; border-radius: 3px; height: 6px; text-align: center; font-size: 1px; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.22); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HI}; }}
QSlider::handle:horizontal:disabled {{ background: transparent; width: 0; margin: 0; }}
QSlider::sub-page:horizontal:disabled {{ background: {ACCENT}; }}

QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px; font-weight: 700; font-size: 14px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabWidget::pane {{ border: none; }}

QMenu {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 26px 8px 14px; border-radius: 6px; font-size: 14px; }}
QMenu::item:selected {{ background: {ACCENT_BG}; color: {ACCENT}; }}
QMenu::item:checked {{ color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QDialog {{ background: {SURFACE}; }}
QMessageBox {{ background: {SURFACE}; }}
QSplitter::handle {{ background: {BG}; }}

/* --- Oynatıcı katmanı --- */
#OsdBar {{ background: rgba(10, 12, 14, 0.78); border-radius: 14px; }}
#OsdTop {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(8,10,12,0.92), stop:0.6 rgba(8,10,12,0.7), stop:1 rgba(8,10,12,0)); }}
#OsdBottom {{ background: qlineargradient(x1:0, y1:1, x2:0, y2:0, stop:0 rgba(8,10,12,0.96), stop:0.55 rgba(8,10,12,0.86), stop:1 rgba(8,10,12,0)); }}
#OsdTitle {{ font-size: 19px; font-weight: 800; }}
#OsdText {{ font-size: 14px; color: #c9d1d9; }}
#OsdToast {{ background: rgba(10,12,14,0.85); border: 1px solid {ACCENT_LO}; border-radius: 12px; padding: 10px 18px; font-size: 15px; font-weight: 700; }}
#Drawer {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#RecBadge {{ background: {DANGER}; color: white; border-radius: 6px; padding: 2px 8px; font-weight: 800; font-size: 12px; }}
#LiveBadge {{ background: {DANGER}; color: white; border-radius: 5px; padding: 1px 6px; font-weight: 800; font-size: 11px; }}

/* --- Ekran klavyesi --- */
#Osk {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
QPushButton#Key {{ background: {SURFACE3}; border: none; border-radius: 7px; font-size: 16px; font-weight: 600; min-height: 38px; padding: 0; }}
QPushButton#Key:pressed {{ background: {ACCENT}; color: #06201e; }}
QPushButton#KeyAlt {{ background: {SURFACE2}; border: none; border-radius: 7px; font-size: 14px; font-weight: 700; min-height: 38px; padding: 0 6px; color: {ACCENT}; }}
QPushButton#KeyAlt:pressed {{ background: {ACCENT}; color: #06201e; }}
"""


def qss():
    return scaled(_QSS)
