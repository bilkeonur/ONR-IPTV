# Third-party software / Üçüncü taraf yazılımlar

ONR IPTV is licensed under the GNU General Public License v3.0 or later (see `LICENSE`).
It is distributed together with the following components:

| Component | License | Source |
|---|---|---|
| [mpv / libmpv](https://mpv.io) (`libmpv-2.dll`, built by [mpv-winbuild-cmake](https://github.com/shinchiro/mpv-winbuild-cmake), includes FFmpeg and other libraries) | GPL-2.0-or-later | https://github.com/mpv-player/mpv · https://github.com/shinchiro/mpv-winbuild-cmake |
| [FFmpeg](https://ffmpeg.org) (inside libmpv) | GPL-2.0-or-later (this build) | https://ffmpeg.org/download.html |
| [Qt for Python / PySide6](https://www.qt.io/qt-for-python) | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git |
| [Qt 6](https://www.qt.io) | LGPL-3.0 | https://code.qt.io |
| [python-mpv](https://github.com/jaseg/python-mpv) | GPL-2.0-or-later / LGPL-2.1-or-later | https://github.com/jaseg/python-mpv |
| [pychromecast](https://github.com/home-assistant-libs/pychromecast) | MIT | https://github.com/home-assistant-libs/pychromecast |
| [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) | LGPL-2.1-or-later | https://github.com/python-zeroconf/python-zeroconf |
| [Requests](https://requests.readthedocs.io) | Apache-2.0 | https://github.com/psf/requests |
| [Python](https://www.python.org) | PSF License | https://www.python.org |

Material Design icon paths are from [Google Material Icons](https://github.com/google/material-design-icons) (Apache-2.0).

The Windows build is made with PyInstaller as a folder (`_internal`), so the LGPL libraries (Qt, PySide6,
zeroconf) stay as separate files that can be replaced.

Screenshots in `docs/screenshots` use *Big Buck Bunny* © Blender Foundation, licensed under CC BY 3.0.
