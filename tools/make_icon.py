"""Uygulama ikonunu (PNG + ICO) üretir."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.qt import QApplication, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRectF, Qt  # noqa: E402

app = QApplication([])
from app.ui.icons import pixmap  # noqa: E402

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def render(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#1b1f23"))
    g.setColorAt(1, QColor("#0e1012"))
    p.fillPath(path, g)
    p.setPen(QColor("#30d5c8"))
    pm = pixmap("live", "#30d5c8", int(size * 0.62))
    off = int(size * 0.19)
    p.drawPixmap(off, off, pm)
    p.end()
    return img


render(256).save(os.path.join(out, "icon.png"))
# Store logoları (1240 piksele kadar) için büyük kaynak; vektörden çizildiği için her boyutta keskin
render(1024).save(os.path.join(out, "icon_1024.png"))
# Çok boyutlu ICO (16-256): Windows her yerde doğru boyutu seçer
from PIL import Image  # noqa: E402
Image.open(os.path.join(out, "icon_1024.png")).save(os.path.join(out, "icon.ico"),
                                                    sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)],
                                                    bitmap_format="bmp")  # PNG'yi küçük boyutlarda her Windows bileşeni okumuyor
print("ok", os.listdir(out))
