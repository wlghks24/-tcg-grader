from pathlib import Path
p=Path('tcg_updater.py')
s=p.read_text(encoding='utf-8')
start="        if path=='/api/verify-grading-cert':\n"
end="        if path=='/api/grading-proxy-costs':\n"
i=s.find(start)
j=s.find(end,i+len(start)) if i>=0 else -1
if i<0:
    print('auto cert endpoint already absent')
elif j<0:
    raise SystemExit('grading proxy marker not found after auto cert endpoint')
else:
    s=s[:i]+s[j:]
    p.write_text(s,encoding='utf-8')
    print('removed /api/verify-grading-cert endpoint')

# Contract guard
s=p.read_text(encoding='utf-8')
if "if path=='/api/verify-grading-cert':" in s:
    raise SystemExit('auto cert endpoint still present')
