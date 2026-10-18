@echo off
rem Windows exe derlemesi. Gereken: python -m pip install -r requirements.txt pyinstaller
rem lib\libmpv-2.dll dosyası bulunmalı (https://github.com/shinchiro/mpv-winbuild-cmake/releases - mpv-dev-x86_64)
cd /d "%~dp0"
python -m PyInstaller --noconfirm ONRIPTV.spec
echo.
echo Hazir: dist\ONRIPTV\ONRIPTV.exe
pause
