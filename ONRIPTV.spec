# -*- mode: python ; coding: utf-8 -*-
# Windows derlemesi:  pyinstaller --noconfirm ONRIPTV.spec
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
# Chromecast: pychromecast ve zeroconf alt modülleri dinamik yüklenir
HIDDEN = collect_submodules("pychromecast") + collect_submodules("zeroconf")

EXCLUDES = [
    "PyQt5", "PyQt6", "PySide2", "tkinter", "unittest", "pydoc_data",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtNetworkAuth", "PySide6.QtGraphs",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[("lib/libmpv-2.dll", "lib")],
    datas=[("assets/icon.png", "assets"), ("app/lang/*.json", "app/lang")],
    hiddenimports=HIDDEN,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ONRIPTV",
    console=False,
    icon="assets/icon.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ONRIPTV")
