"""Microsoft Store için MSIX paketi üretir.

    python tools/make_msix.py            # dist/ONRIPTV'den dist/ONRIPTV-<sürüm>.msix (Store'a yüklenecek, imzasız)
    python tools/make_msix.py --test     # ayrıca yerelde kurmak için test sertifikasıyla imzalı kopya

Önce exe derlenmiş olmalı: python -m PyInstaller --noconfirm ONRIPTV.spec
Store paketi kendisi imzalar; --test sertifikası (build/msix/ONRIPTV-test.pfx) yalnızca bu bilgisayarda denemek içindir.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "ONRIPTV")
STAGE = os.path.join(ROOT, "build", "msix", "root")
MANIFEST = os.path.join(ROOT, "packaging", "msix", "AppxManifest.xml")
ICON = os.path.join(ROOT, "assets", "icon_1024.png")  # tools/make_icon.py üretir


def sdk_tool(name):
    hits = sorted(glob.glob(rf"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\{name}"))
    if not hits:
        sys.exit(f"{name} bulunamadı: Windows SDK kurulu olmalı")
    return hits[-1]


def app_version():
    src = open(os.path.join(ROOT, "app", "config.py"), encoding="utf-8").read()
    v = re.search(r'APP_VERSION = "([\d.]+)"', src).group(1)
    parts = (v.split(".") + ["0", "0", "0"])[:3]
    return ".".join(parts) + ".0"  # Store: dört parça, sonuncusu 0


def publisher():
    return re.search(r'Publisher="([^"]+)"', open(MANIFEST, encoding="utf-8").read()).group(1)


def make_assets(out):
    """Başlangıç menüsü / görev çubuğu / mağaza logoları."""
    os.makedirs(out, exist_ok=True)
    src = Image.open(ICON).convert("RGBA")

    def square(size, name, pad=0.0):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = max(1, round(size * (1 - 2 * pad)))
        ic = src.resize((inner, inner), Image.LANCZOS)
        canvas.paste(ic, ((size - inner) // 2, (size - inner) // 2), ic)
        canvas.save(os.path.join(out, name))

    def wide(w, h, name):
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        s = round(h * 0.7)
        ic = src.resize((s, s), Image.LANCZOS)
        canvas.paste(ic, ((w - s) // 2, (h - s) // 2), ic)
        canvas.save(os.path.join(out, name))

    for scale in (100, 125, 150, 200, 400):
        k = scale / 100
        square(round(44 * k), f"Square44x44Logo.scale-{scale}.png")
        square(round(150 * k), f"Square150x150Logo.scale-{scale}.png", 0.18)
        square(round(310 * k), f"Square310x310Logo.scale-{scale}.png", 0.2)
        square(round(50 * k), f"StoreLogo.scale-{scale}.png")
        wide(round(310 * k), round(150 * k), f"Wide310x150Logo.scale-{scale}.png")
    for t in (16, 24, 32, 48, 256):
        square(t, f"Square44x44Logo.targetsize-{t}.png")
        square(t, f"Square44x44Logo.targetsize-{t}_altform-unplated.png")


def stage():
    if not os.path.isfile(os.path.join(DIST, "ONRIPTV.exe")):
        sys.exit("dist/ONRIPTV/ONRIPTV.exe yok; önce PyInstaller ile derleyin")
    shutil.rmtree(os.path.dirname(STAGE), ignore_errors=True)
    shutil.copytree(DIST, STAGE)
    version = app_version()
    manifest = open(MANIFEST, encoding="utf-8").read().replace("{VERSION}", version)
    open(os.path.join(STAGE, "AppxManifest.xml"), "w", encoding="utf-8").write(manifest)
    make_assets(os.path.join(STAGE, "Assets"))
    # Ölçek / boyut varyantlarını seçebilmesi için kaynak dizini (resources.pri)
    makepri = sdk_tool("makepri.exe")
    cfg = os.path.join(os.path.dirname(STAGE), "priconfig.xml")
    subprocess.run([makepri, "createconfig", "/cf", cfg, "/dq", "en-US", "/pv", "10.0.0", "/o"], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run([makepri, "new", "/pr", STAGE, "/cf", cfg, "/mn", os.path.join(STAGE, "AppxManifest.xml"),
                    "/of", os.path.join(STAGE, "resources.pri"), "/o"], check=True, stdout=subprocess.DEVNULL)
    return version


def pack(version):
    out = os.path.join(ROOT, "dist", f"ONRIPTV-{version}.msix")
    subprocess.run([sdk_tool("makeappx.exe"), "pack", "/d", STAGE, "/p", out, "/o"], check=True,
                   stdout=subprocess.DEVNULL)
    return out


def test_sign(msix):
    """Yerel deneme: Publisher ile aynı konulu, kendinden imzalı sertifika üretip kopyayı imzalar."""
    pfx = os.path.join(ROOT, "build", "msix", "ONRIPTV-test.pfx")
    cer = os.path.join(ROOT, "dist", "ONRIPTV-test.cer")
    pwd = "onriptv-test"
    ps = (f"$c = Get-ChildItem Cert:\\CurrentUser\\My | Where-Object {{ $_.Subject -eq '{publisher()}' }} | "
          f"Select-Object -First 1; if (-not $c) {{ $c = New-SelfSignedCertificate -Type Custom "
          f"-Subject '{publisher()}' -KeyUsage DigitalSignature -FriendlyName 'ONR IPTV test' "
          f"-CertStoreLocation Cert:\\CurrentUser\\My "
          f"-TextExtension @('2.5.29.37={{text}}1.3.6.1.5.5.7.3.3', '2.5.29.19={{text}}') }}; "
          f"Export-PfxCertificate -Cert $c -FilePath '{pfx}' -Password (ConvertTo-SecureString '{pwd}' -AsPlainText -Force) | Out-Null; "
          f"Export-Certificate -Cert $c -FilePath '{cer}' | Out-Null")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    signed = msix.replace(".msix", "-test.msix")
    shutil.copy(msix, signed)
    subprocess.run([sdk_tool("signtool.exe"), "sign", "/fd", "SHA256", "/f", pfx, "/p", pwd, signed], check=True,
                   stdout=subprocess.DEVNULL)
    return signed, cer


def main():
    version = stage()
    msix = pack(version)
    print(f"Store paketi: {msix} ({os.path.getsize(msix) / 1e6:.1f} MB, sürüm {version})")
    if "--test" in sys.argv:
        signed, cer = test_sign(msix)
        print(f"Test paketi: {signed}\nTest sertifikası: {cer}")


if __name__ == "__main__":
    main()
