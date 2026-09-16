from pathlib import Path

path = Path("tcg_updater.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor mismatch: {count}")
    text = text.replace(old, new, 1)


replace_once(
    "from grading_accuracy_v99 import valid_actual_grade\n",
    "from grading_accuracy_v99 import valid_actual_grade\nfrom runtime_sre_metrics import RUNTIME_METRICS\n",
    "runtime metrics import",
)

replace_once(
'''def _start_background_update(retry_only=False):
    global LAST_MANUAL_UPDATE
    now=time.monotonic()
    with MANUAL_UPDATE_LOCK:
        current=_job_snapshot()
        if current.get('state') in ('queued','running'):
            return None, {'ok':False,'error':'이미 업데이트가 진행 중입니다','job':current}, 409
        wait=MANUAL_UPDATE_COOLDOWN_SECONDS-(now-LAST_MANUAL_UPDATE)
        if wait>0:
            return None, {'ok':False,'error':'업데이트 요청이 너무 빠릅니다','retry_after_seconds':round(wait,1)}, 429
        LAST_MANUAL_UPDATE=now
        job_id=f"{int(time.time())}-{os.getpid()}"
        total_jobs=_full_update_job_count()
        _job_set(id=job_id,state='queued',trigger='retry-failed' if retry_only else 'manual',
                 started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),finished_at=None,current=0,total=0 if retry_only else total_jobs,
                 label='대기 중',file=None,message='업데이트 작업 준비 중',error=None,report=None,retry_only=retry_only)
    target=_background_retry_failed if retry_only else _background_full_update
    threading.Thread(target=target,args=(job_id,),daemon=True).start()
    return job_id, {'ok':True,'accepted':True,'job_id':job_id,'job':_job_snapshot()}, 202
''',
'''def _start_background_update(retry_only=False):
    """Start one bounded update worker or join the same in-flight operation.

    Repeated clicks/retries must not create request-thread or worker-thread storms.
    A request for a different update kind remains a conflict so full and retry-only
    semantics cannot be silently mixed.
    """
    global LAST_MANUAL_UPDATE
    now=time.monotonic()
    with MANUAL_UPDATE_LOCK:
        current=_job_snapshot()
        if current.get('state') in ('queued','running'):
            same_kind=bool(current.get('retry_only'))==bool(retry_only)
            if same_kind:
                RUNTIME_METRICS.update_request_joined()
                current_id=current.get('id')
                return current_id, {
                    'ok':True,'accepted':True,'joined_existing':True,
                    'job_id':current_id,'job':current,
                    'message':'동일 업데이트가 이미 진행 중이어서 기존 작업에 연결했습니다.',
                }, 202
            RUNTIME_METRICS.update_request_conflicted()
            return None, {'ok':False,'error':'다른 종류의 업데이트가 이미 진행 중입니다','job':current}, 409
        wait=MANUAL_UPDATE_COOLDOWN_SECONDS-(now-LAST_MANUAL_UPDATE)
        if wait>0:
            RUNTIME_METRICS.update_request_rate_limited()
            return None, {'ok':False,'error':'업데이트 요청이 너무 빠릅니다','retry_after_seconds':round(wait,1)}, 429
        LAST_MANUAL_UPDATE=now
        job_id=f"{int(time.time())}-{os.getpid()}"
        total_jobs=_full_update_job_count()
        _job_set(id=job_id,state='queued',trigger='retry-failed' if retry_only else 'manual',
                 started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),finished_at=None,current=0,total=0 if retry_only else total_jobs,
                 label='대기 중',file=None,message='업데이트 작업 준비 중',error=None,report=None,retry_only=retry_only)
    target=_background_retry_failed if retry_only else _background_full_update
    try:
        threading.Thread(
            target=target,args=(job_id,),name=f'tcg-update-{job_id}',daemon=True
        ).start()
    except RuntimeError as exc:
        _job_set(state='failed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                 error=f'{type(exc).__name__}: background-thread-start-failed',
                 message='업데이트 작업 스레드를 시작하지 못했습니다.')
        _collection_mark_failure('retry-failed' if retry_only else 'manual',exc)
        return None, {'ok':False,'error':'업데이트 작업을 시작하지 못했습니다','job':_job_snapshot()}, 500
    RUNTIME_METRICS.update_job_started()
    return job_id, {'ok':True,'accepted':True,'joined_existing':False,'job_id':job_id,'job':_job_snapshot()}, 202
''',
    "background update singleflight",
)

replace_once(
'''    def _manual_update(self):
        global LAST_MANUAL_UPDATE
        if not self._require_mutation_origin():
            return
        now=time.monotonic()
        with MANUAL_UPDATE_LOCK:
            wait=MANUAL_UPDATE_COOLDOWN_SECONDS-(now-LAST_MANUAL_UPDATE)
            if wait>0:
                return self.json({'ok':False,'error':'업데이트 요청이 너무 빠릅니다','retry_after_seconds':round(wait,1)},429)
            LAST_MANUAL_UPDATE=now
        try:
            data=update_cycle('manual')
            report=load_json_file(AUTO_REPORT,{'ok':False,'results':[]})
            issues=load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]})
            return self.json({
                'ok':bool(report.get('ok',True)),
                'auto_update':data.get('auto_update',{}),
                'updated_at':data.get('updated_at'),
                'report':report,
                'issues':issues,
                'message':'최신자료 확인 → 변경 비교 → 검증 → 정상자료 전체 반영을 한 번에 완료했습니다.'
            })
        except Exception as exc:
            _collection_mark_failure('manual',exc)
            return self.json({'ok':False,'error':'통합 업데이트 실행 오류'},500)
''',
'''    def _manual_update(self):
        """Compatibility endpoint: never hold an HTTP worker for a full collection cycle."""
        if not self._require_mutation_origin():
            return
        _job_id,payload,status=_start_background_update(False)
        body=dict(payload)
        body['legacy_route']=True
        body['execution_mode']='background-singleflight'
        if status==202 and not body.get('message'):
            body['message']='업데이트를 백그라운드에서 시작했습니다. 작업 상태 API로 진행률을 확인하세요.'
        return self.json(body,status)
''',
    "legacy manual update",
)

replace_once(
'''        if path=='/api/health':
            return self.json({'ok':True,'service':SERVICE_NAME,'platform':PLATFORM,'port':PORT,'api_version':3,'integrated_version':INTEGRATED_VERSION,'learning_version':'v123-verified-multisource-photo-collection','collection_health':collection_health_status(),'collection_neural':collection_neural_status()})
        if path=='/api/collection-health': return self.json(collection_health_status())
''',
'''        if path=='/api/health':
            return self.json({'ok':True,'service':SERVICE_NAME,'platform':PLATFORM,'port':PORT,'api_version':3,'integrated_version':INTEGRATED_VERSION,'learning_version':'v123-verified-multisource-photo-collection','collection_health':collection_health_status(),'collection_neural':collection_neural_status()})
        if path=='/api/runtime-metrics':
            return self.json({
                'ok':True,
                'server':{
                    'max_request_threads':QuietThreadingHTTPServer.max_request_threads,
                    'request_queue_size':QuietThreadingHTTPServer.request_queue_size,
                },
                'metrics':RUNTIME_METRICS.snapshot(),
                'update_job':_job_snapshot(),
            })
        if path=='/api/collection-health': return self.json(collection_health_status())
''',
    "runtime metrics endpoint",
)

replace_once(
'''class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Bounded local HTTP worker pool with quiet normal disconnect handling."""
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    request_queue_size = 32
    max_request_threads = env_int('TCG_HTTP_MAX_THREADS', 32, 8, 128)

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(self.max_request_threads)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b'HTTP/1.1 503 Service Unavailable\\r\\n'
                    b'Connection: close\\r\\nRetry-After: 1\\r\\nContent-Length: 0\\r\\n\\r\\n'
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def handle_error(self, request, client_address):
        exc=sys.exc_info()[1]
        if isinstance(exc,(BrokenPipeError,ConnectionResetError)):
            return
        return super().handle_error(request,client_address)
''',
'''class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Bounded local HTTP worker pool with overload shedding and fixed metrics."""
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    request_queue_size = 32
    max_request_threads = env_int('TCG_HTTP_MAX_THREADS', 32, 8, 128)

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(self.max_request_threads)
        self._request_started_lock = threading.Lock()
        self._request_started = {}
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            RUNTIME_METRICS.overload_rejected()
            body=b'{"ok":false,"error":"server_overloaded","retry_after_seconds":1}'
            try:
                request.sendall(
                    b'HTTP/1.1 503 Service Unavailable\\r\\n'
                    b'Content-Type: application/json; charset=utf-8\\r\\n'
                    b'Connection: close\\r\\nRetry-After: 1\\r\\n'
                    + f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode('ascii')
                    + body
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        started=RUNTIME_METRICS.request_started()
        request_key=id(request)
        with self._request_started_lock:
            self._request_started[request_key]=started
        try:
            super().process_request(request, client_address)
        except BaseException:
            with self._request_started_lock:
                started=self._request_started.pop(request_key,None)
            RUNTIME_METRICS.request_finished(started)
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        request_key=id(request)
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._request_started_lock:
                started=self._request_started.pop(request_key,None)
            RUNTIME_METRICS.request_finished(started)
            self._request_slots.release()

    def handle_error(self, request, client_address):
        exc=sys.exc_info()[1]
        if isinstance(exc,(BrokenPipeError,ConnectionResetError)):
            return
        RUNTIME_METRICS.uncaught_request_error()
        return super().handle_error(request,client_address)
''',
    "bounded server metrics",
)

path.write_text(text, encoding="utf-8")
