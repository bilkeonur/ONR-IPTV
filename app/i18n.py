"""Arayüz dilleri.

Kaynak metinler Türkçe yazılır ve anahtar olarak kullanılır; app/lang/<kod>.json dosyaları bunların
çevirisini tutar. Yeni dil eklemek için tr.json'u kopyalayıp değerleri çevirmek yeterlidir. Kullanıcı
veri klasöründeki lang/ altına konan dosyalar da listelenir (exe'yi yeniden derlemeden dil eklemek için).
"""
import json
import os
import sys

from .config import DATA_DIR

DEFAULT = "tr"
_strings = {}
_code = DEFAULT


def _dirs():
    base = getattr(sys, "_MEIPASS", None)
    bundled = os.path.join(base, "app", "lang") if base else os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")
    return [bundled, os.path.join(DATA_DIR, "lang")]


def _read(code):
    for d in reversed(_dirs()):
        try:
            with open(os.path.join(d, f"{code}.json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return None


def available():
    """[(kod, görünen ad)] — bulunan tüm dil dosyaları."""
    out = {}
    for d in _dirs():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            code, ext = os.path.splitext(fn)
            if ext != ".json" or code in out:
                continue
            data = _read(code) or {}
            out[code] = (data.get("_meta") or {}).get("name") or code
    out.setdefault(DEFAULT, "Türkçe")
    return sorted(out.items(), key=lambda kv: (kv[0] != DEFAULT, kv[1]))


def system_language():
    """İşletim sisteminin arayüz dili Türkçe ise 'tr', değilse 'en'."""
    try:
        if sys.platform.startswith("win"):
            import ctypes  # noqa: PLC0415
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "tr" if (lang_id & 0x3FF) == 0x1F else "en"  # 0x1F = LANG_TURKISH
        import locale  # noqa: PLC0415
        loc = os.environ.get("LANGUAGE") or os.environ.get("LC_ALL") or os.environ.get("LANG") \
            or (locale.getlocale()[0] or "")
        return "tr" if loc.lower().startswith("tr") else "en"
    except Exception:  # noqa: BLE001
        return "en"


def resolve(setting):
    """Ayar değerinden ('auto' ya da dil kodu) yüklenecek dil kodu."""
    return system_language() if not setting or setting == "auto" else setting


def load(code):
    global _code, _strings
    data = _read(code or DEFAULT)
    if data is None:
        code, data = DEFAULT, _read(DEFAULT) or {}
    _code = code or DEFAULT
    _strings = {k: v for k, v in (data.get("strings") or {}).items() if v}


def current():
    return _code


def tr(text, **kw):
    """Metnin etkin dildeki karşılığı; {ad} yer tutucuları kw ile doldurulur."""
    s = _strings.get(text, text)
    return s.format(**kw) if kw else s


_ = tr


def N_(text):
    """Modül düzeyindeki sabit metinleri çeviri dosyasına almak için işaretler; çeviri kullanımda _() ile yapılır."""
    return text


DAYS = [N_("Pazartesi"), N_("Salı"), N_("Çarşamba"), N_("Perşembe"), N_("Cuma"), N_("Cumartesi"), N_("Pazar")]
MONTHS = [N_("Ocak"), N_("Şubat"), N_("Mart"), N_("Nisan"), N_("Mayıs"), N_("Haziran"), N_("Temmuz"),
          N_("Ağustos"), N_("Eylül"), N_("Ekim"), N_("Kasım"), N_("Aralık")]


def day_name(tm):
    """time.struct_time için etkin dilde gün adı (strftime'ın %A'sı sistem yereline bağlı)."""
    return tr(DAYS[tm.tm_wday])


def month_name(tm):
    return tr(MONTHS[tm.tm_mon - 1])
