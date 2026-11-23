"""Reviewed official notices omitted by the old snapshot; no invented TCG rewards.

Facts reviewed 2026-11-23. Runtime must still recheck each source. These are
specific announcements, not evidence that any country/game feed is complete.
"""

REVIEWED_EVENTS = (
    dict(game='나루토 카드', region='JP', category='event',
         name_ko='나루토 SHINOBI-ZATO 크리스마스 행사 2026',
         name_native='SHINOBI-ZATO Christmas Fes 2026',
         start_date='2026-11-20', end_date='2026-12-27', date_precision='day',
         reward='크리스마스 장식·한정 상품 안내. TCG 프로모 카드 배포는 확인되지 않았습니다.',
         condition='일본 니지겐노모리 행사. 별도 입장권 필요. 나루토 인사는 12월 토·일 14시이며 날씨 등에 따라 취소될 수 있습니다.',
         location='일본 아와지 니지겐노모리 SHINOBI-ZATO',
         source='https://naruto-official.com/en/news/01_2716',
         source_grade='official', announcement_date='2026-11-14',
         required_evidence=['Christmas Fes 2026', 'November 20th', 'December 27th']),
    dict(game='나루토 카드', region='JP', category='promo',
         name_ko='나루토 SHINOBI-ZATO 2026년 11월 생일 기념 카드',
         name_native='SHINOBI-ZATO Character Birthday Event',
         start_date='2026-11-01', end_date='2026-11-30', date_precision='day',
         reward='공식 안내의 생일 기념 카드. 나루토 TCG 플레이용 카드라는 근거는 없습니다.',
         condition='일본 현장 스태프에게 해당 인물의 생일 축하 방문임을 알려야 합니다. 재고 소진 시 종료. 입장권·연령별 요금은 공식 안내 확인.',
         location='일본 아와지 니지겐노모리 SHINOBI-ZATO',
         source='https://naruto-official.com/en/news/01_2712',
         source_grade='official', announcement_date='2026-11-02',
         required_evidence=['Birthday Card', 'November 1st', 'November 30th']),
    dict(game='포켓몬 카드', region='KR', category='tournament',
         name_ko='메가엘레이드 ex SAR GET BATTLE',
         name_native='메가엘레이드 ex SAR GET BATTLE',
         start_date='2026-10-31', end_date='2026-11-22', date_precision='day',
         reward='3승 또는 대상자 가위바위보 우승 조건의 메가엘레이드 ex 프로모. 참가상은 공식 경품 안내 확인.',
         condition='한국 지정 카드샵·공식 인증샵의 개별 일정 적용. 스톰에메랄다 15팩 구입 22,500원. 예약·현장 접수 방식은 매장 유형별로 다릅니다.',
         location='대한민국 지정 포켓몬 카드샵·공식 인증샵',
         source='https://pokemonkorea.co.kr/PCG_Getbattle_M6/menu830',
         source_grade='official',
         required_evidence=['메가엘레이드', '2026년 10월 31일', '11월 22일']),
)
