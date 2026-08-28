import time
import verify_all
orig=verify_all.check
def verbose(name,fn,rows):
    print('START',name,flush=True)
    t=time.time();orig(name,fn,rows);row=rows[-1]
    print('END',name,'OK' if row.get('ok') else 'FAIL',f'{time.time()-t:.2f}s',row.get('detail'),flush=True)
verify_all.check=verbose
verify_all.main()
