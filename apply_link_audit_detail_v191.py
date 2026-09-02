#!/usr/bin/env python3
from pathlib import Path

p=Path('auto_update_all.py')
text=p.read_text(encoding='utf-8')
old="""        warning=f'미보정 깨진 링크 {unresolved_broken}개' if unresolved_broken else ''\n        transient_notice=f'일시 확인불가 {transient}개 · 기존 링크 유지 · 다음 업데이트 재확인' if transient else ''\n        return {\"ok\":True,\"degraded\":degraded,\"warning\":warning,\"reachable_count\":reachable_count,\n                \"transient_deferred\":bool(transient),\"transient_notice\":transient_notice,\n                \"unresolved_broken\":unresolved_broken,**lr}\n"""
new="""        unresolved_details=lr.get('unresolved_details') if isinstance(lr.get('unresolved_details'),list) else []\n        detail_parts=[]\n        for item in unresolved_details[:3]:\n            if not isinstance(item,dict):\n                continue\n            url=str(item.get('url') or '').strip()[:220]\n            refs=item.get('references') if isinstance(item.get('references'),list) else []\n            locations=[]\n            for ref in refs[:3]:\n                if not isinstance(ref,dict):\n                    continue\n                fn=str(ref.get('file') or '').strip()\n                field=str(ref.get('field') or '').strip()\n                if fn or field:\n                    locations.append(f\"{fn}:{field}\".strip(':'))\n            location=', '.join(locations)\n            if url and location:\n                detail_parts.append(f'{url} [{location}]')\n            elif url:\n                detail_parts.append(url)\n        warning=f'미보정 깨진 링크 {unresolved_broken}개' if unresolved_broken else ''\n        if warning and detail_parts:\n            warning += ' · ' + ' | '.join(detail_parts)\n        transient_notice=f'일시 확인불가 {transient}개 · 기존 링크 유지 · 다음 업데이트 재확인' if transient else ''\n        return {\"ok\":True,\"degraded\":degraded,\"warning\":warning,\"reachable_count\":reachable_count,\n                \"transient_deferred\":bool(transient),\"transient_notice\":transient_notice,\n                \"unresolved_broken\":unresolved_broken,\"unresolved_summary\":detail_parts,**lr}\n"""
if new in text:
    print('v191 already applied')
elif old not in text:
    raise SystemExit('v191 target block not found')
else:
    p.write_text(text.replace(old,new,1),encoding='utf-8')
    print('v191 applied')
