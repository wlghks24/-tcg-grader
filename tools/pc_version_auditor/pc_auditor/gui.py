"""Optional desktop UI for the offline read-only TCG PC version auditor."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from audit import AuditError
from double_review import run_double_review


class AuditGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TCG Grader · V1~현재 누락·보완·전후 교차검증 강제·이중 전체 재검수 v0.6")
        self.geometry("840x540")
        self.minsize(650, 450)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.repo = tk.StringVar(value=str(Path.home() / "tcg-grader"))
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "TCG_PC_AUDIT"))
        self.latest = tk.StringVar(value="")
        self.auto_review = tk.BooleanVar(value=True)
        self.repeat = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="준비됨 · 원본 소스 및 GitHub에 쓰지 않습니다 · 수정안 정적검사만")
        self._build()
        self.after(120, self._poll)

    def _build(self):
        root = ttk.Frame(self, padding=16)
        root.pack(expand=True, fill="both")
        ttk.Label(root, text="TCG Grader PC 버전 조사기", font=("Malgun Gothic", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="V1~현재 / 100개 구간 조사→보완→전후 재검증→독립 2차 전체 실행→HOLD / 이어하기").pack(anchor="w", pady=(3, 12))
        for label, var, browse in (("Git 원본 폴더", self.repo, True), ("보고서 저장 폴더", self.output, True)):
            row = ttk.Frame(root)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=20).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", expand=True, fill="x")
            ttk.Button(row, text="선택", command=lambda v=var: self._browse(v)).pack(side="left", padx=(5, 0))
        row = ttk.Frame(root)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="마지막 V번호", width=20).pack(side="left")
        ttk.Entry(row, textvariable=self.latest, width=15).pack(side="left")
        ttk.Label(row, text="공란 = 저장소 기록의 최대 번호(실제 최신 릴리스 보증 아님)").pack(side="left", padx=7)
        choices = ttk.Frame(root)
        choices.pack(fill="x", pady=7)
        ttk.Label(choices, text="엄격 구간별 보완·재검증: 항상 사용 (해제 불가)").pack(side="left")
        ttk.Checkbutton(choices, text="6시간마다 자동 재검사(이 창을 켜둔 경우)",
                        variable=self.repeat).pack(side="left", padx=10)
        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=12)
        self.start_btn = ttk.Button(bar, text="전체 검수→독립 2차 재검수", command=lambda: self._start(True))
        self.start_btn.pack(side="left")
        self.resume_btn = ttk.Button(bar, text="이어하기 / 재검사", command=lambda: self._start(True))
        self.resume_btn.pack(side="left", padx=7)
        self.stop_btn = ttk.Button(bar, text="현재 구간 후 중지", state="disabled", command=self.stop.set)
        self.stop_btn.pack(side="left")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", pady=5)
        ttk.Label(root, textvariable=self.status, wraplength=740).pack(anchor="w", pady=(0, 8))
        frame = ttk.Frame(root)
        frame.pack(expand=True, fill="both")
        self.log = tk.Text(frame, wrap="word", height=14, state="disabled")
        self.log.pack(side="left", expand=True, fill="both")
        scroller = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scroller.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroller.set)
        ttk.Label(root, text="안전: Git 원본 수정 없음 · 자동 수정 후보는 별도 폴더에만 생성 · 테스트 승인/병합/설치/학습 없음",
                  foreground="#815b20", wraplength=760).pack(anchor="w", pady=(10, 0))

    def _browse(self, var):
        p = filedialog.askdirectory(title="폴더 선택")
        if p:
            var.set(p)

    def _line(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self, resume):
        if self.worker and self.worker.is_alive():
            return
        value = self.latest.get().strip()
        if value and (not value.isdecimal() or not 1 <= int(value) <= 9999):
            messagebox.showerror("입력 오류", "마지막 V번호는 1~9999 사이 정수여야 합니다")
            return
        self.stop.clear()
        self.start_btn.configure(state="disabled")
        self.resume_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start()
        self.status.set("1차·2차 독립 실행과 3단계 의심 교차검증 중…")
        repo, output, latest = Path(self.repo.get()), Path(self.output.get()), int(value) if value else None

        def work():
            try:
                result = run_double_review(repo, output, latest, stop_event=self.stop,
                                          callback=lambda text: self.events.put(("log", text)))
                self.events.put(("done", result))
            except (AuditError, OSError, UnicodeError, ValueError) as exc:
                self.events.put(("error", str(exc)))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _repeat_if_enabled(self):
        if self.repeat.get() and (not self.worker or not self.worker.is_alive()):
            self._start(True)

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self._line(data)
                else:
                    self.progress.stop()
                    self.start_btn.configure(state="normal")
                    self.resume_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    if kind == "done":
                        self.status.set(f"HOLD: V1~V{min(100, data['latest'])} 누락·수정 후 재검증 부족 / 다음 100개 차단")
                        self._line("[HOLD] 전체 프로그램 1차+2차 독립 재검수 결과 일치. 기능·원본 버전 증거가 없으면 다음 구간 진행 금지.")
                        if self.repeat.get():
                            self.after(6 * 60 * 60 * 1000, self._repeat_if_enabled)
                    else:
                        self.status.set("HOLD: " + data)
                        self._line("[HOLD] " + data)
        except queue.Empty:
            pass
        self.after(120, self._poll)


if __name__ == "__main__":
    AuditGUI().mainloop()
