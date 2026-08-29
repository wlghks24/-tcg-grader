#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch_index():
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    marker = '<link rel="stylesheet" href="ui_tablet_refine_v122.css?v=122">'
    if marker not in text:
        if "</head>" not in text:
            raise RuntimeError("index.html </head> marker missing")
        text = text.replace("</head>", marker + "\n</head>", 1)
        path.write_text(text, encoding="utf-8")


def patch_server():
    path = ROOT / "tcg_updater.py"
    text = path.read_text(encoding="utf-8")
    if "'ui_tablet_refine_v122.css'" not in text:
        needle = "'ui_polish_v121.css'"
        if needle not in text:
            raise RuntimeError("v121 CSS static-file marker missing")
        text = text.replace(needle, needle + ",'ui_tablet_refine_v122.css'", 1)
        path.write_text(text, encoding="utf-8")


def patch_sw():
    path = ROOT / "sw.js"
    text = path.read_text(encoding="utf-8")
    text = text.replace("const CACHE='tcg-v121-ui-polish';", "const CACHE='tcg-v122-tablet-refine';", 1)
    if "'./ui_tablet_refine_v122.css'" not in text:
        needle = "'./ui_polish_v121.css'"
        if needle not in text:
            raise RuntimeError("service worker v121 CSS marker missing")
        text = text.replace(needle, needle + ",'./ui_tablet_refine_v122.css'", 1)
    path.write_text(text, encoding="utf-8")


def main():
    patch_index()
    patch_server()
    patch_sw()
    print("tablet UI refine v122 integration applied")


if __name__ == "__main__":
    main()
