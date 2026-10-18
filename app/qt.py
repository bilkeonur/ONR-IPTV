"""Qt bağlama katmanı: önce PySide6, yoksa PyQt6 kullanılır.

Raspberry Pi OS'ta pip ile PySide6 kurulamazsa apt ile gelen PyQt6 da çalışır.
"""
import os as _os

try:
    if (_os.environ.get("ONRIPTV_QT") or _os.environ.get("TURKUAZTV_QT")) == "pyqt6":
        raise ImportError("PyQt6 zorlandı")
    from PySide6.QtCore import *  # noqa: F401,F403
    from PySide6.QtGui import *  # noqa: F401,F403
    from PySide6.QtWidgets import *  # noqa: F401,F403
    from PySide6.QtSvg import QSvgRenderer  # noqa: F401
    from PySide6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from PySide6.QtCore import Signal, Slot  # noqa: F401

    QT_API = "pyside6"
except ImportError:  # pragma: no cover - Pi fallback
    from PyQt6.QtCore import *  # noqa: F401,F403
    from PyQt6.QtGui import *  # noqa: F401,F403
    from PyQt6.QtWidgets import *  # noqa: F401,F403
    from PyQt6.QtSvg import QSvgRenderer  # noqa: F401
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from PyQt6.QtCore import pyqtSignal as Signal, pyqtSlot as Slot  # noqa: F401

    QT_API = "pyqt6"
