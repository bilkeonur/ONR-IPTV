"""Çeviri anahtarlarını kaynak koddan toplar ve dil dosyalarını günceller.

    python tools/i18n_extract.py           # app/lang/tr.json'u yeniden yazar, diğer dillerde eksikleri listeler
    python tools/i18n_extract.py --check   # _() ile sarılmamış, arayüzde görünebilecek metinleri listeler

_("...") ve N_("...") çağrılarındaki metinler anahtardır. tr.json kaynak dilin kendisidir (anahtar = değer)
ve yeni dil eklerken şablon olarak kopyalanır.
"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT, "app", "lang")
SOURCES = [os.path.join(ROOT, "main.py")]
for d, _dirs, files in os.walk(os.path.join(ROOT, "app")):
    SOURCES += [os.path.join(d, f) for f in files if f.endswith(".py")]

# Arayüze metin veren Qt çağrıları (--check için)
UI_CALLS = {"setText", "setToolTip", "setPlaceholderText", "setWindowTitle", "addAction", "addItem", "addRow",
            "QLabel", "QPushButton", "QCheckBox", "toast", "show_toast", "question", "warning", "information",
            "critical", "empty", "loading", "error", "card", "QListWidgetItem", "getText"}


def _name(func):
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def keys():
    out = {}
    for path in sorted(SOURCES):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node.func) in ("_", "N_", "tr") and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.setdefault(a.value, os.path.relpath(path, ROOT))
    return out


def check():
    found = 0
    for path in sorted(SOURCES):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        wrapped = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node.func) in ("_", "N_", "tr"):
                wrapped.update(id(n) for n in ast.walk(node))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _name(node.func) in UI_CALLS):
                continue
            for a in node.args:
                for c in ast.walk(a):
                    if id(c) in wrapped:
                        continue
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and any(ch.isalpha() for ch in c.value) \
                            and c.value.strip() not in ("PIN", "1x", "16:9", "4:3", "21:9", "A → Z", "Z → A"):
                        print(f"{os.path.relpath(path, ROOT)}:{c.lineno}: {c.value!r}")
                        found += 1
    print(f"{found} şüpheli metin")


def main():
    if "--check" in sys.argv:
        check()
        return
    ks = keys()
    os.makedirs(LANG_DIR, exist_ok=True)
    src = {"_meta": {"name": "Türkçe", "code": "tr"}, "strings": {k: k for k in sorted(ks)}}
    with open(os.path.join(LANG_DIR, "tr.json"), "w", encoding="utf-8") as f:
        json.dump(src, f, ensure_ascii=False, indent=1)
    print(f"tr.json: {len(ks)} metin")
    for fn in sorted(os.listdir(LANG_DIR)):
        if fn == "tr.json" or not fn.endswith(".json"):
            continue
        data = json.load(open(os.path.join(LANG_DIR, fn), encoding="utf-8"))
        strings = data.get("strings", {})
        missing = [k for k in ks if not strings.get(k)]
        unused = [k for k in strings if k not in ks]
        print(f"{fn}: {len(missing)} eksik, {len(unused)} kullanılmayan")
        for k in missing:
            print("  eksik:", repr(k), "←", ks[k])


if __name__ == "__main__":
    main()
