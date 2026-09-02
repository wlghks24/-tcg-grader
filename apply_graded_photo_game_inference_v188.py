#!/usr/bin/env python3
from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{label}: patch anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_once(
        "graded_photo_multi_source.py",
        """GAME_PATTERNS={\n 'pokemon':re.compile(r'pokemon|pokémon|포켓몬|ポケモン',re.I),\n 'onepiece':re.compile(r'one\\s*piece|원피스|ワンピース',re.I),\n 'naruto':re.compile(r'naruto|나루토|ナルト',re.I),\n}\nDIRECT_GRADE_RE=""",
        """GAME_PATTERNS={\n 'pokemon':re.compile(r'pokemon|pokémon|포켓몬|ポケモン',re.I),\n 'onepiece':re.compile(r'one\\s*piece|원피스|ワンピース',re.I),\n 'naruto':re.compile(r'naruto|나루토|ナルト',re.I),\n}\nCARD_IDENTITY_CATALOG=ROOT/'card_identity_reference_catalog.json'\nONEPIECE_CARD_CODE_RE=re.compile(r'(?<![A-Z0-9])(?:OP|EB|PRB)\\d{2}[\\s_-]*\\d{3}(?![A-Z0-9])',re.I)\n_GAME_REFERENCE_CACHE=None\nDIRECT_GRADE_RE=""",
        "v188 constants",
    )

    patch_once(
        "graded_photo_multi_source.py",
        """def _game(text:str,expected:str='')->str:\n for g,p in GAME_PATTERNS.items():\n  if p.search(text or ''):return g\n return expected if expected in GAMES else 'unknown'\n\ndef _cert(text:str)->str:\n""",
        """def _game(text:str,expected:str='')->str:\n matches=[g for g,p in GAME_PATTERNS.items() if p.search(text or '')]\n if len(matches)==1:return matches[0]\n return expected if expected in GAMES else 'unknown'\n\ndef _compact_identity_text(value:Any)->str:\n return re.sub(r'[^A-Z0-9가-힣ぁ-んァ-ヶ一-龯]', '', str(value or '').upper())[:6000]\n\ndef _reviewed_game_reference_rows()->list[dict]:\n global _GAME_REFERENCE_CACHE\n if _GAME_REFERENCE_CACHE is not None:return _GAME_REFERENCE_CACHE\n data=_load(CARD_IDENTITY_CATALOG,{})\n rows=[]\n for item in data.get('cards',[]) if isinstance(data,dict) else []:\n  if not isinstance(item,dict):continue\n  game=str(item.get('game') or '').lower()\n  if game not in GAMES:continue\n  number=_compact_identity_text(item.get('card_number'))\n  if len(number)<4:continue\n  aliases=[]\n  for value in [item.get('card_name'),*(item.get('aliases') or [])]:\n   alias=_compact_identity_text(value)\n   if len(alias)>=4 and alias not in aliases:aliases.append(alias)\n  if aliases:rows.append({'game':game,'card_number':number,'aliases':aliases})\n _GAME_REFERENCE_CACHE=rows\n return rows\n\ndef _game_signal_map(text:Any)->dict[str,set[str]]:\n raw=str(text or '')[:12000]\n signals={game:set() for game in GAMES}\n for game,pattern in GAME_PATTERNS.items():\n  if pattern.search(raw):signals[game].add('explicit_game_token')\n if ONEPIECE_CARD_CODE_RE.search(raw):signals['onepiece'].add('onepiece_card_code')\n compact=_compact_identity_text(raw)\n if compact:\n  for ref in _reviewed_game_reference_rows():\n   if ref['card_number'] not in compact:continue\n   if any(alias in compact for alias in ref['aliases']):\n    signals[ref['game']].add('reviewed_card_name_number_pair')\n return {game:reasons for game,reasons in signals.items() if reasons}\n\ndef _recover_candidate_game(item:dict)->tuple[dict,bool]:\n current=str(item.get('game') or '').lower()\n if current in GAMES:return item,False\n fields=('title','snippet','ocr_label_text','source_asset_name','card_name','card_number','product_name','official_title','url')\n text=' | '.join(str(item.get(field) or '')[:1800] for field in fields if item.get(field))\n signals=_game_signal_map(text)\n if len(signals)!=1:\n  if len(signals)>1:\n   item=dict(item);item['game_inference_conflict']=sorted(signals)\n  return item,False\n game=next(iter(signals));reasons=sorted(signals[game])\n confidence=0.995 if 'explicit_game_token' in reasons else (0.985 if 'reviewed_card_name_number_pair' in reasons else 0.98)\n item=dict(item);item['game']=game\n item['game_inference_source']='+'.join(reasons)[:120]\n item['game_inference_confidence']=confidence\n item['game_inference_evidence']=reasons[:4]\n item.pop('game_inference_conflict',None)\n return item,True\n\ndef _recover_unknown_games(rows:list[dict])->tuple[list[dict],dict]:\n out=[];recovered=0;conflicts=0;by_game={game:0 for game in GAMES}\n for source in rows:\n  item=dict(source)\n  item,changed=_recover_candidate_game(item)\n  if changed:\n   recovered+=1;by_game[str(item.get('game'))]+=1\n  if item.get('game_inference_conflict'):conflicts+=1\n  out.append(item)\n remaining=sum(str(item.get('game') or '').lower() not in GAMES for item in out)\n return out,{'recovered':recovered,'conflicts':conflicts,'remaining_unknown':remaining,'by_game':by_game,\n             'policy':'existing_game_first; unique_strong_signal_only; no_grade_or_official_promotion'}\n\ndef _cert(text:str)->str:\n""",
        "v188 conservative inference helpers",
    )

    patch_once(
        "graded_photo_multi_source.py",
        """ try:probe_limit=int(os.environ.get('TCG_GRADED_IMAGE_PROBE_LIMIT','6' if is_android else '12'))\n except (TypeError,ValueError,OverflowError):probe_limit=6 if is_android else 12\n rows,image_stats=enrich_rows(rows,limit=max(0,min(probe_limit,24)),workers=2 if is_android else 4)\n image_stats['prevalidated_library']=sum(x.get('image_evidence_source')=='prevalidated_library_photo' for x in rows)\n rows,official_stats=_official_verify_rows(rows,registry,max_live=5 if is_android else 10)\n""",
        """ rows,game_inference_pre_stats=_recover_unknown_games(rows)\n try:probe_limit=int(os.environ.get('TCG_GRADED_IMAGE_PROBE_LIMIT','6' if is_android else '12'))\n except (TypeError,ValueError,OverflowError):probe_limit=6 if is_android else 12\n rows,image_stats=enrich_rows(rows,limit=max(0,min(probe_limit,24)),workers=2 if is_android else 4)\n rows,game_inference_post_stats=_recover_unknown_games(rows)\n game_inference_stats={\n  'recovered':int(game_inference_pre_stats.get('recovered',0))+int(game_inference_post_stats.get('recovered',0)),\n  'before_ocr_recovered':int(game_inference_pre_stats.get('recovered',0)),\n  'after_ocr_recovered':int(game_inference_post_stats.get('recovered',0)),\n  'conflicts':int(game_inference_post_stats.get('conflicts',0)),\n  'remaining_unknown':int(game_inference_post_stats.get('remaining_unknown',0)),\n  'by_game':{game:int(game_inference_pre_stats.get('by_game',{}).get(game,0))+int(game_inference_post_stats.get('by_game',{}).get(game,0)) for game in GAMES},\n  'policy':game_inference_post_stats.get('policy'),\n }\n image_stats['prevalidated_library']=sum(x.get('image_evidence_source')=='prevalidated_library_photo' for x in rows)\n rows,official_stats=_official_verify_rows(rows,registry,max_live=5 if is_android else 10)\n""",
        "v188 pre/post OCR inference",
    )

    patch_once(
        "graded_photo_multi_source.py",
        """          'image_probe_stats':image_stats,'official_verification_stats':official_stats,'quarantine_cleanup_stats':cleanup_stats,\n""",
        """          'image_probe_stats':image_stats,'game_inference_stats':game_inference_stats,'official_verification_stats':official_stats,'quarantine_cleanup_stats':cleanup_stats,\n""",
        "v188 expose inference stats",
    )
    print('[OK] v188 graded-photo game inference patch prepared')


if __name__ == '__main__':
    main()
