from pathlib import Path

path = Path('index.html')
text = path.read_text(encoding='utf-8')
repls = {
    '🖥️ 서버 연결됨 · 출시·재발매·시세·행사·구매처·환율 6단계를 백그라운드에서 수집하고 있습니다.':
    '🖥️ 서버 연결됨 · 출시·재발매·시세·행사·구매처·환율·등급사진 7단계를 백그라운드에서 수집하고 있습니다.',
    '서버 백그라운드 6단계 수집 완료':
    '서버 백그라운드 7단계 수집 완료',
}
changed = False
for old, new in repls.items():
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif new not in text:
        raise SystemExit(f'target text not found: {old}')

path.write_text(text, encoding='utf-8')
print('patched top update UI to 7-step wording' if changed else 'top update UI already uses 7-step wording')
