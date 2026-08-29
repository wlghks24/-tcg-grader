from pathlib import Path

ROOT=Path(__file__).resolve().parent

def patch_auto_update():
    p=ROOT/'auto_update_all.py';s=p.read_text(encoding='utf-8')
    needle='    ("원화 환산 환율", "update_exchange_rates", "exchange_rates.json"),\n)'
    repl='    ("원화 환산 환율", "update_exchange_rates", "exchange_rates.json"),\n    ("업체별 등급카드 사진 후보", "graded_photo_multi_source", "graded_photo_candidates.json"),\n)'
    if 'graded_photo_multi_source' not in s:
        if needle not in s: raise SystemExit('auto_update_all JOBS anchor missing')
        s=s.replace(needle,repl,1)
        p.write_text(s,encoding='utf-8')

def patch_updater():
    p=ROOT/'tcg_updater.py';s=p.read_text(encoding='utf-8')
    old="    'current':0,'total':6,'label':'대기 중','file':None,'message':'대기 중',"
    new="    'current':0,'total':7,'label':'대기 중','file':None,'message':'대기 중',"
    if old in s:s=s.replace(old,new,1)
    # expose read-only status API without touching calibration data
    api="        if path=='/api/graded-photo-learning': return self.json(load_json_file(os.path.join(BASE,'graded_photo_candidates.json'),{'schema_version':1,'records':[],'summary':{'total_candidates':0}}))\n"
    anchor="        if path=='/api/ebay-grader-learning': return self.json(ebay_grader_learning_status())\n"
    if '/api/graded-photo-learning' not in s:
        if anchor not in s: raise SystemExit('tcg_updater API anchor missing')
        s=s.replace(anchor,anchor+api,1)
    p.write_text(s,encoding='utf-8')

if __name__=='__main__':
    patch_auto_update();patch_updater();print('graded photo collection patch applied')
