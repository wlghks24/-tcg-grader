#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch_index():
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    marker = '<link rel="stylesheet" href="ui_polish_v121.css?v=121">'
    if marker not in text:
        if "</head>" not in text:
            raise RuntimeError("index.html </head> marker missing")
        text = text.replace("</head>", marker + "\n</head>", 1)
        path.write_text(text, encoding="utf-8")


def patch_server():
    path = ROOT / "tcg_updater.py"
    text = path.read_text(encoding="utf-8")
    if "'ui_polish_v121.css'" not in text:
        needle = "'image_quality_guard.js'"
        if needle not in text:
            raise RuntimeError("PUBLIC_STATIC_FILES insertion marker missing")
        text = text.replace(needle, needle + ",'ui_polish_v121.css'", 1)
        path.write_text(text, encoding="utf-8")


def patch_sw():
    path = ROOT / "sw.js"
    text = path.read_text(encoding="utf-8")
    text = text.replace("// v118: high-contrast game selector labels + representative category illustrations.",
                        "// v121: polished responsive UI + high-contrast game selector labels.", 1)
    text = text.replace("const CACHE='tcg-v118-game-selector-visual-fix';", "const CACHE='tcg-v121-ui-polish';", 1)
    if "'./ui_polish_v121.css'" not in text:
        needle = "'./index.html'"
        if needle not in text:
            raise RuntimeError("service worker CORE marker missing")
        text = text.replace(needle, needle + ",'./ui_polish_v121.css'", 1)
    path.write_text(text, encoding="utf-8")


def main():
    patch_index()
    patch_server()
    patch_sw()
    print("ui polish v121 integration applied")


if __name__ == "__main__":
    main()
