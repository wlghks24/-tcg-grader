"""Two review modes: Git global scan plus current-folder code reviewer."""
from __future__ import annotations
import datetime,queue,threading,tkinter as tk
import webbrowser
from tkinter import filedialog,messagebox,ttk
from pathlib import Path
from full_repo_engine import run_global
from local_review import review

class App:
    def __init__(self,root):
        self.root=root;self.q=queue.Queue(maxsize=300);self.finished=None;self.running=False;self.result_page=None
        self.root.title('TCG PC 코드 검토 통합 프로그램 v0.10.0');self.root.geometry('1000x680')
        self.source=tk.StringVar(value=str(Path.home()/'TCG_Grader'))
        self.out=tk.StringVar(value=str(Path.home()/'Documents'/('TCG_AUDIT_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))))
        self.use_ruff=tk.BooleanVar(value=False);self.run_tests=tk.BooleanVar(value=False)
        self.status=tk.StringVar(value='대기: 원본 보존, 보고서는 독립 폴더')
        f=ttk.Frame(root,padding=14);f.pack(fill='both',expand=True)
        ttk.Label(f,text='TCG Grader PC 통합 코드 검토',font=('Malgun Gothic',17,'bold')).pack(anchor='w')
        ttk.Label(f,text='전체 Git 이력·코드지도 / 현재 파일 오류·미구현 후보·격리 패치 (원본 수정 금지)').pack(anchor='w',pady=(4,14))
        for label,var in [('검사할 코드 폴더',self.source),('새 보고서 폴더',self.out)]:
            r=ttk.Frame(f);r.pack(fill='x',pady=4)
            ttk.Label(r,text=label,width=18).pack(side='left')
            ttk.Entry(r,textvariable=var).pack(side='left',fill='x',expand=True)
            ttk.Button(r,text='선택',command=lambda v=var:self.choose(v)).pack(side='left')
        r=ttk.Frame(f);r.pack(anchor='w',pady=7)
        ttk.Checkbutton(r,text='Ruff 정적 검사(설치된 경우만)',variable=self.use_ruff).pack(side='left',padx=(0,18))
        ttk.Checkbutton(r,text='프로젝트 unittest 실행(신뢰된 코드만; PC 권한으로 실행)',variable=self.run_tests).pack(side='left')
        self.local_btn=ttk.Button(f,text='현재 코드 심층 검사 · 코드지도/중복/보완 작업표',command=lambda:self.start('local'))
        self.local_btn.pack(anchor='w',pady=(2,7))
        self.git_btn=ttk.Button(f,text='전체 Git 코드·이력 2회 재현성 검사',command=lambda:self.start('git'))
        self.git_btn.pack(anchor='w',pady=(2,7))
        self.open_btn=ttk.Button(f,text='완료된 보고서 열기',command=self.open_report,state='disabled')
        self.open_btn.pack(anchor='w',pady=4)
        ttk.Label(f,text='결과 HOLD는 결함 확정이나 자동 수정 완료를 뜻하지 않습니다.',foreground='#a05200').pack(anchor='w')
        ttk.Label(f,textvariable=self.status).pack(anchor='w',pady=(10,5))
        self.log=tk.Text(f,height=22);self.log.pack(fill='both',expand=True)
        self.root.after(100,self.poll)
    def open_report(self):
        if self.result_page and self.result_page.is_file():
            webbrowser.open(self.result_page.resolve().as_uri())
    def choose(self,v):
        p=filedialog.askdirectory(title='폴더 선택')
        if p:v.set(str(Path(p)/('TCG_AUDIT_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))) if v==self.out else p)
    def msg(self,value):
        try:self.q.put_nowait(str(value)[:3000])
        except queue.Full:pass
    def append(self,s):
        self.log.insert('end',s+'\n')
        lines=int(self.log.index('end-1c').split('.')[0])
        if lines>1000:self.log.delete('1.0',f'{lines-999}.0')
        self.log.see('end')
    def start(self,mode):
        if self.running:return
        source=self.source.get().strip().strip('"');out=self.out.get().strip().strip('"')
        if not source or not out:messagebox.showerror('경로 누락','검사 폴더와 새 보고서 폴더를 선택하세요.');return
        if mode=='local' and self.run_tests.get():
            if not messagebox.askyesno('테스트 코드 실행 확인','프로젝트 테스트는 격리된 샌드박스가 아닙니다. PC 사용자 권한으로 실행합니다. 신뢰할 수 있는 코드가 맞나요?'):return
        self.result_page=None;self.open_btn.configure(state='disabled')
        self.running=True;self.local_btn.configure(state='disabled');self.git_btn.configure(state='disabled')
        self.status.set('검사 진행 중 - 원본 무수정')
        kw={'use_ruff':self.use_ruff.get(),'execute_tests':self.run_tests.get()}
        try:threading.Thread(target=self.worker,args=(mode,Path(source),Path(out),kw),daemon=True).start()
        except Exception as ex:self.finished='[HOLD] 작업 시작 실패: '+repr(ex)
    def worker(self,mode,src,out,kw):
        try:
            if mode=='local':
                r=review(src,out,callback=self.msg,**kw)
                self.result_page=out/'review.html'
                answer=f"[HOLD] 현재 코드 {r['scanned_files']}파일 / 검토 필요 {r['review_required_count']}개 / 참고 정보 {r['informational_count']}개 / 격리 후보 {len(r['proposals'])}개 / 제외 {len(r['skipped'])}개. 보고서 {out}/review.html"
            else:
                r=run_global(src,out,self.msg)
                answer=f"[HOLD] Git 코드/이력 분석 2회 재현성 일치. 파일 {r['gate']['tracked_files']}개, 단서 {r['gate']['risk_hints']}개. 보고서 {out}"
        except Exception as ex:answer='[HOLD] 검사 중 오류: '+repr(ex)+' / 새 보고서 폴더를 사용해 재검사하세요.'
        self.finished=answer
    def poll(self):
        for _ in range(60):
            try:v=self.q.get_nowait()
            except queue.Empty:break
            self.append(v)
        if self.finished is not None:
            s=self.finished;self.finished=None;self.running=False
            self.status.set('완료: 정적 검토 HOLD (승인 아님)');self.append(s)
            if self.result_page:self.open_btn.configure(state='normal')
            self.local_btn.configure(state='normal');self.git_btn.configure(state='normal')
        try:self.root.after(100,self.poll)
        except (RuntimeError,tk.TclError):pass
if __name__=='__main__':
    r=tk.Tk();App(r);r.mainloop()
