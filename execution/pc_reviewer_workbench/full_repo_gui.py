"""Korean Tk GUI for a read-only whole-repository two-pass review."""
from __future__ import annotations

import datetime
import queue
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
from full_repo_engine import ReviewHold,run_global

MAX_UI_LOG_LINES=800
MAX_LOG_MESSAGE_BYTES=5000
MAX_PENDING_MESSAGES=300
MAX_DRAIN_PER_TICK=60


class App:
    def __init__(self,root:tk.Tk):
        self.root=root
        self._queue=queue.Queue(maxsize=MAX_PENDING_MESSAGES)
        self._suppressed=0
        self._done=None
        self._running=False
        self.root.title('TCG Grader PC - 전체 저장소 통합 정밀검사 v0.8.1 (2회 독립검증)')
        self.root.geometry('930x650')
        self.repo=tk.StringVar(value=str(Path.home()/'TCG_Grader'))
        self.output=tk.StringVar(value=str(Path.home()/'Documents'/('TCG_Global_Audit_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))))
        self.status=tk.StringVar(value='준비됨: 원본은 읽기 전용, 보고서는 별도 폴더에 저장')
        wrap=ttk.Frame(root,padding=14);wrap.pack(fill='both',expand=True)
        ttk.Label(wrap,text='TCG Grader - 전체 저장소 통합 검수',font=('Malgun Gothic',17,'bold')).pack(anchor='w')
        ttk.Label(wrap,text='모든 현재 추적 파일 + 접근 가능한 모든 Git 커밋 이력 + 코드 지도 + 위험 후보 → 독립 2회 검사',font=('Malgun Gothic',10)).pack(anchor='w',pady=(4,14))
        for caption,variable in (('Git 원본 폴더',self.repo),('새 보고서 폴더',self.output)):
            line=ttk.Frame(wrap);line.pack(fill='x',pady=5)
            ttk.Label(line,text=caption,width=16).pack(side='left')
            ttk.Entry(line,textvariable=variable).pack(side='left',fill='x',expand=True)
            ttk.Button(line,text='선택',command=lambda v=variable:self.choose(v)).pack(side='left',padx=(8,0))
        ttk.Label(wrap,text='※ 100개 단위 강제 중단 없음. 단, 번호 힌트≠실제 발매 버전 / 정적검사≠회귀검증 / 수정 자동승인 금지',foreground='#8f4500').pack(anchor='w',pady=(7,8))
        self.go=ttk.Button(wrap,text='전체 저장소 검사 → 독립 2차 전체 재검사',command=self.run)
        self.go.pack(anchor='w',pady=5)
        ttk.Label(wrap,textvariable=self.status).pack(anchor='w',pady=(10,4))
        self.log=tk.Text(wrap,height=23,wrap='word');self.log.pack(fill='both',expand=True)
        self._message('기존 V1~V100 HOLD 보고서는 보존합니다. 미구현 단서와 수정 과제는 자동 수정/승인을 의미하지 않습니다.')
        self.root.after(100,self._drain)
    def choose(self,v):
        if v==self.repo: p=filedialog.askdirectory(title='검사할 Git 저장소 선택')
        else: p=filedialog.askdirectory(title='새 보고서 폴더의 부모 선택')
        if p:
            if v==self.output:v.set(str(Path(p)/('TCG_GLOBAL_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))))
            else:v.set(p)
    def _message(self,s):
        # Limit BOTH per-message size and cumulative retained log lines.
        s=str(s)[:MAX_LOG_MESSAGE_BYTES]
        self.log.insert('end',s+'\n')
        lines=int(self.log.index('end-1c').split('.')[0])
        if lines>MAX_UI_LOG_LINES:
            self.log.delete('1.0',f'{lines-MAX_UI_LOG_LINES+1}.0')
        self.log.see('end')

    def _thread_message(self,s):
        # Worker thread never invokes tkinter directly.
        try:self._queue.put_nowait(str(s)[:MAX_LOG_MESSAGE_BYTES])
        except queue.Full:self._suppressed+=1

    def _drain(self):
        try:
            for _ in range(MAX_DRAIN_PER_TICK):
                try:message=self._queue.get_nowait()
                except queue.Empty:break
                self._message(message)
            if self._done is not None:
                # Deliver final status even if routine log events were dropped.
                finished=self._done;self._done=None
                self._finish(finished)
            if self._suppressed and self._queue.empty() and not self._running:
                self._message(f'[NOTE] UI 로그 {self._suppressed}건 생략됨 (메모리 보호); 검사 보고서 결과가 우선입니다.')
                self._suppressed=0
        finally:
            try:self.root.after(100,self._drain)
            except (RuntimeError,tk.TclError):pass

    def run(self):
        repo=self.repo.get().strip().strip('"');out=self.output.get().strip().strip('"')
        if self._running:return
        if not repo or not out:
            messagebox.showwarning('입력 누락','Git 원본 폴더와 새 보고서 폴더를 선택하세요.');return
        self._running=True
        self.go.configure(state='disabled');self.status.set('전체 정적검사 진행 중 (두 번 독립 실행)')
        self._message('시작. 원본 Git은 변경하지 않습니다. 결과가 완료돼도 기능·설치 승인은 HOLD입니다.')
        try:threading.Thread(target=self._worker,args=(repo,out),daemon=True).start()
        except Exception as exc:
            self._running=False
            self._finish('[HOLD] 검사 작업 시작 실패: '+repr(exc))
    def _worker(self,repo,out):
        try:
            r=run_global(Path(repo),Path(out),self._thread_message)
            gate=r['gate']
            msg=(f"[HOLD] 전체 추적파일 {gate['tracked_files']}개 / 분석소스 "
                 f"{gate['source_files_analyzed']}개 / 커밋 {gate['history_commits_read']}개 / "
                 f"검토 단서 {gate['risk_hints']}개 / 미구현 검토 단서 "
                 f"{gate['placeholder_or_unimplemented_hints']}개. 독립 결과 일치 PASS.\n보고서: {out}")
        except Exception as exc:
            # Even unexpected worker failures must restore the GUI button.
            msg='[HOLD] 검사가 중단됐습니다: '+repr(exc)+'\n기존 보고서와 Git 원본은 보존됩니다. 새 보고서 폴더로 재검사하세요.'
        self._done=msg
    def _finish(self,msg):
        self._running=False
        self.status.set('검증 상태: HOLD (실제 기능·역사적 버전별 검증 필요)')
        self._message(msg);self.go.configure(state='normal')

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
