"""Conservative local image quotas and pixel-preserving storage optimization."""
from __future__ import annotations
import io
import math
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

PERIOD_SECONDS=6*3600
RUN_IMAGES=36
DAY_IMAGES=144
PROVIDER_DAY_IMAGES=24
RUN_REQUESTS=80
DAY_REQUESTS=320
PROVIDER_DAY_REQUESTS=80
RUN_BYTES=24*1024*1024
DAY_BYTES=96*1024*1024
REQUEST_SPACING=2.0
RUN_SECONDS=180
MAX_PIXELS=12_000_000


class Deferred(ValueError):
    pass


class Budget:
    def __init__(self,state,save,*,clock=time.time,timer=time.monotonic):
        self.state,self.save,self.clock,self.timer=state,save,clock,timer
        self.started=timer();self.events=[];self.last_request=None;self.provider=''
        rows=state.get('image_budget_events',[])
        if not isinstance(rows,list) or len(rows)>1200:raise Deferred('수집 예산 상태 형식 오류')
        now=clock()
        kept=[]
        for row in rows:
            if (not isinstance(row,dict) or row.get('kind') not in ('request','image')
                or not isinstance(row.get('provider'),str) or len(row['provider'])>40
                or type(row.get('at')) not in (int,float) or not math.isfinite(row['at'])
                or row['at']>now+300 or type(row.get('bytes')) is not int or row['bytes']<0):
                raise Deferred('수집 예산 이력 검증 실패')
            if now-row['at']<86400:kept.append(row)
        state['image_budget_events']=kept
        prior_requests=[r['at'] for r in kept if r['kind']=='request']
        if prior_requests:self.last_request=timer()-(now-max(prior_requests))
        cooldown=state.setdefault('image_provider_cooldowns',{})
        if (not isinstance(cooldown,dict) or len(cooldown)>30 or any(not isinstance(k,str) or
            type(v) not in (int,float) or not math.isfinite(v) or v<0 for k,v in cooldown.items())):
            raise Deferred('출처 대기 상태 검증 실패')

    def _day(self):
        now=self.clock()
        return [r for r in self.state['image_budget_events'] if now-r['at']<86400]

    def _count(self,rows,kind,provider=None):
        return sum(r['kind']==kind and (provider is None or r['provider']==provider) for r in rows)

    def remaining_seconds(self):
        return max(0,RUN_SECONDS-(self.timer()-self.started))

    def can_save(self,provider):
        if self.state['image_provider_cooldowns'].get(provider,0)>self.clock():
            raise Deferred('출처 대기기간 · 재요청 보류')
        day=self._day()
        if (self.remaining_seconds()<=0 or self._count(self.events,'image')>=RUN_IMAGES or
            self._count(day,'image')>=DAY_IMAGES or self._count(day,'image',provider)>=PROVIDER_DAY_IMAGES):
            raise Deferred('이미지 수집 수량/실행시간 예산 도달')

    def reserve_request(self,provider,sleeper=time.sleep):
        self.provider=provider;day=self._day()
        if self.state['image_provider_cooldowns'].get(provider,0)>self.clock():
            raise Deferred('출처 대기기간 · 재요청 보류')
        if (self._count(self.events,'request')>=RUN_REQUESTS or self._count(day,'request')>=DAY_REQUESTS or
            self._count(day,'request',provider)>=PROVIDER_DAY_REQUESTS):
            raise Deferred('출처 요청 예산 도달')
        delay=0 if self.last_request is None else max(0,REQUEST_SPACING-(self.timer()-self.last_request))
        if self.remaining_seconds()<=delay:raise Deferred('실행시간 예산 도달')
        if delay:sleeper(delay)
        if self.remaining_seconds()<=0:raise Deferred('실행시간 예산 도달')
        row={'at':self.clock(),'kind':'request','provider':provider,'bytes':0}
        self.events.append(row);self.state['image_budget_events'].append(row)
        self.last_request=self.timer();self.save()
        return row

    def byte_allowance(self):
        return max(0,min(RUN_BYTES-sum(r['bytes'] for r in self.events if r['kind']=='request'),
                         DAY_BYTES-sum(r['bytes'] for r in self._day() if r['kind']=='request')))

    def add_bytes(self,row,size):
        if type(size) is not int or size<0 or size>self.byte_allowance():raise Deferred('다운로드 용량 예산 도달')
        row['bytes']+=size;self.save()

    def record_image(self,provider,size):
        if type(size) is not int or size<0:raise Deferred("저장 크기 형식 오류")
        row={'at':self.clock(),'kind':'image','provider':provider,'bytes':size}
        self.events.append(row);self.state['image_budget_events'].append(row);self.save()

    def block(self,provider,code,retry_after=None):
        delay=6*3600 if code==403 else 3600
        if isinstance(retry_after,str):
            try:
                if retry_after.isdecimal():delay=max(delay,int(retry_after))
                else:delay=max(delay,parsedate_to_datetime(retry_after).astimezone(timezone.utc).timestamp()-self.clock())
            except (ValueError,TypeError,OverflowError):pass
        self.state['image_provider_cooldowns'][provider]=self.clock()+delay;self.save()

    def snapshot(self):
        rows=self._day()
        return {'period_seconds':PERIOD_SECONDS,'per_run_limit':RUN_IMAGES,'daily_limit':DAY_IMAGES,
                'saved_last_24h':self._count(rows,'image'),'stored_bytes_last_24h':sum(r['bytes'] for r in rows if r['kind']=='image'),'requests_last_24h':self._count(rows,'request'),
                'daily_request_limit':DAY_REQUESTS,'request_spacing_seconds':REQUEST_SPACING,
                'provider_daily_image_limit':PROVIDER_DAY_IMAGES,'provider_daily_request_limit':PROVIDER_DAY_REQUESTS,
                'aggregate_limit_requires_provider_diversity':True,'run_seconds_limit':RUN_SECONDS,
                'daily_bytes_limit':DAY_BYTES,'bytes_last_24h':sum(r['bytes'] for r in rows if r['kind']=='request')}


def lossless_storage(data):
    """Only new automatic catalog images; never rewrite an existing/manual photo.

    Same displayed pixels/dimensions, verified after encoding. Keep the source
    bytes when lossless WebP is larger or the codec is unavailable.
    """
    from PIL import Image,ImageOps,features
    with Image.open(io.BytesIO(data)) as source:
        if source.width*source.height>MAX_PIXELS or getattr(source,'n_frames',1)!=1:
            raise ValueError('이미지 픽셀/프레임 제한 초과')
        source.load()
        normalized=ImageOps.exif_transpose(source).convert('RGBA')
        report={'source_bytes':len(data),'stored_bytes':len(data),'width':normalized.width,
                'height':normalized.height,'lossless':True,'resized':False,'encoding':'source',
                'readability_review_required':min(normalized.size)<400}
        if source.mode not in ('RGB','RGBA','P','L','LA','1') or not features.check('webp'):
            return data,report
        output=io.BytesIO()
        options={'lossless':True,'quality':100,'method':4,'exact':True}
        if source.info.get('icc_profile'):options['icc_profile']=source.info['icc_profile']
        normalized.save(output,format='WEBP',**options)
        candidate=output.getvalue()
        if len(candidate)>=len(data):return data,report
        with Image.open(io.BytesIO(candidate)) as verified:
            if verified.size!=normalized.size or verified.convert('RGBA').tobytes()!=normalized.tobytes():
                raise ValueError('무손실 압축 픽셀 검증 실패')
        report.update(stored_bytes=len(candidate),encoding='webp-lossless')
        return candidate,report
