from pathlib import Path

path = Path('tcg_updater.py')
text = path.read_text(encoding='utf-8')
old = "print('1 출시일 · 2 판매/재발매 · 3 거래시세 · 4 프로모/콜라보 · 5 구매처/링크 · 6 환율',flush=True)"
new = "print('1 출시일 · 2 판매/재발매 · 3 거래시세 · 4 프로모/콜라보 · 5 구매처/링크 · 6 환율 · 7 업체별 등급카드 사진',flush=True)"
if old not in text:
    raise SystemExit('target startup display line not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('patched tcg_updater.py startup display to 7 steps')
