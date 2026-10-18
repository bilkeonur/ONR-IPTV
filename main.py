"""ONR IPTV - Xtream / M3U / Stalker IPTV oynatıcı."""
import os
import sys


def _prepare_libmpv():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for d in (os.path.join(base, "lib"), base):
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass


def main():
    _prepare_libmpv()
    # Pi'de Wayland/X11 fark etmeksizin OpenGL ES ile çalışır
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from app.qt import QApplication, QFont, Qt, QIcon
    from app import config

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_NAME)

    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")  # libmpv bunu gerektirir

    from app.ui import theme
    from app.ui.icons import icon
    f = QFont(theme.FONT)
    f.setPixelSize(13)
    app.setFont(f)
    app.setStyleSheet(theme.QSS)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(base, "assets", "icon.png")
    app.setWindowIcon(QIcon(ico) if os.path.exists(ico) else icon("live", theme.ACCENT, theme.ACCENT, 64))

    settings = config.Settings()
    try:
        from app.ui.main_window import MainWindow
        win = MainWindow(settings)
    except OSError as e:
        from app.qt import QMessageBox
        QMessageBox.critical(None, config.APP_NAME,
                             f"Video motoru (libmpv) yüklenemedi:\n{e}\n\n"
                             "Windows: lib/libmpv-2.dll dosyasının olduğundan emin olun.\n"
                             "Raspberry Pi: sudo apt install libmpv2")
        return 1

    screen = app.primaryScreen().availableGeometry()
    if settings.get("start_fullscreen") or (screen.width() <= 1024 and screen.height() <= 600):
        win.showFullScreen()
    else:
        win.resize(min(1280, screen.width() - 80), min(780, screen.height() - 80))
        win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
