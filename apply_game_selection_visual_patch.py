#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"

OLD_CSS = ".simple-game-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.simple-game{padding:16px 8px;border:2px solid #e2e8f0;border-radius:16px;background:#fff;font-weight:900;font-size:1.05rem}.simple-game.active{border-color:#2563eb;background:#eff6ff;box-shadow:0 0 0 3px rgba(37,99,235,.08)}"
NEW_CSS = ".simple-game-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.simple-game{padding:14px 10px;border:2px solid #e2e8f0;border-radius:16px;background:#fff;color:#0f172a!important;font-weight:900;font-size:1.05rem;min-height:92px;display:flex;align-items:center;justify-content:center;gap:12px;text-shadow:none!important}.simple-game .game-visual{width:54px;height:54px;flex:0 0 54px;display:grid;place-items:center;border-radius:14px}.simple-game .game-visual svg{width:46px;height:46px;display:block}.simple-game .game-label{display:block;color:#0f172a!important;font-size:1.18rem;font-weight:950;line-height:1.15;letter-spacing:-.02em}.simple-game[data-simple-game=\"pokemon\"]{border-color:#93c5fd;background:#eff6ff}.simple-game[data-simple-game=\"pokemon\"] .game-visual{background:#dbeafe}.simple-game[data-simple-game=\"onepiece\"]{border-color:#fca5a5;background:#fff7f7}.simple-game[data-simple-game=\"onepiece\"] .game-visual{background:#fee2e2}.simple-game[data-simple-game=\"naruto\"]{border-color:#fdba74;background:#fffaf2}.simple-game[data-simple-game=\"naruto\"] .game-visual{background:#ffedd5}.simple-game.active{border-width:3px;border-color:#2563eb!important;background:#eff6ff;box-shadow:0 0 0 3px rgba(37,99,235,.10)}"

OLD_HTML = '''  <div class="simple-game-grid">\n    <button class="simple-game active" data-simple-game="pokemon">🟦 포켓몬</button>\n    <button class="simple-game" data-simple-game="onepiece">🟥 원피스</button>\n    <button class="simple-game" data-simple-game="naruto">🟧 나루토</button>\n  </div>'''

NEW_HTML = '''  <div class="simple-game-grid" aria-label="카드게임 선택">\n    <button class="simple-game active" data-simple-game="pokemon" type="button" aria-label="포켓몬 카드 선택">\n      <span class="game-visual" aria-hidden="true">\n        <svg viewBox="0 0 64 64" role="img"><rect x="10" y="8" width="44" height="48" rx="8" fill="#fff" stroke="#2563eb" stroke-width="3"/><circle cx="32" cy="32" r="12" fill="#facc15" stroke="#0f172a" stroke-width="3"/><path d="M37 12 30 27h9l-12 24 5-17h-9z" fill="#f59e0b" stroke="#0f172a" stroke-width="1.8"/></svg>\n      </span><span class="game-label">포켓몬</span>\n    </button>\n    <button class="simple-game" data-simple-game="onepiece" type="button" aria-label="원피스 카드 선택">\n      <span class="game-visual" aria-hidden="true">\n        <svg viewBox="0 0 64 64" role="img"><ellipse cx="32" cy="39" rx="24" ry="8" fill="#f59e0b" stroke="#7f1d1d" stroke-width="3"/><path d="M19 38c1-17 5-25 13-25s12 8 13 25z" fill="#fbbf24" stroke="#7f1d1d" stroke-width="3"/><rect x="18" y="30" width="28" height="7" rx="3" fill="#dc2626"/></svg>\n      </span><span class="game-label">원피스</span>\n    </button>\n    <button class="simple-game" data-simple-game="naruto" type="button" aria-label="나루토 카드 선택">\n      <span class="game-visual" aria-hidden="true">\n        <svg viewBox="0 0 64 64" role="img"><path d="M8 24h48v22H8z" rx="6" fill="#475569"/><rect x="15" y="19" width="34" height="30" rx="7" fill="#cbd5e1" stroke="#0f172a" stroke-width="3"/><path d="M38 29c-7-6-17-1-15 7 2 7 13 6 14 0 1-5-7-7-9-2" fill="none" stroke="#f97316" stroke-width="4" stroke-linecap="round"/><path d="M8 28 2 23v24l6-5M56 28l6-5v24l-6-5" fill="#334155"/></svg>\n      </span><span class="game-label">나루토</span>\n    </button>\n  </div>'''


def main():
    text = INDEX.read_text(encoding="utf-8")
    changed = False
    if OLD_CSS in text:
        text = text.replace(OLD_CSS, NEW_CSS, 1)
        changed = True
    elif NEW_CSS not in text:
        raise SystemExit("[ERROR] simple-game CSS target not found")

    if OLD_HTML in text:
        text = text.replace(OLD_HTML, NEW_HTML, 1)
        changed = True
    elif 'class="game-visual"' not in text:
        raise SystemExit("[ERROR] simple-game HTML target not found")

    if changed:
        INDEX.write_text(text, encoding="utf-8")
        print("[OK] game selection visual patch applied")
    else:
        print("[OK] game selection visual patch already applied")

    required = [
        'color:#0f172a!important',
        'class="game-visual"',
        '<span class="game-label">포켓몬</span>',
        '<span class="game-label">원피스</span>',
        '<span class="game-label">나루토</span>',
    ]
    missing = [x for x in required if x not in text]
    if missing:
        raise SystemExit(f"[ERROR] visual patch validation failed: {missing}")
    print("[PASS] labels are dark and representative SVG icons are present")


if __name__ == "__main__":
    main()
