# 등급완료 파일 학습함

이미 PSA/BGS/CGC/TAG/BRG 등급을 받은 카드 사진 또는 RAW 예측 결과 파일을 넣는 폴더입니다.

## 가장 쉬운 사용법

- 포켓몬 등급완료 사진 → `drop/pokemon/`
- 원피스 등급완료 사진 → `drop/onepiece/`
- 나루토 등급완료 사진 → `drop/naruto/`
- 지원 사진: JPG, JPEG, PNG

그 뒤 저장소 루트에서:

```bash
bash START_GRADED_FILE_LEARNING.sh
```

프로그램은 사진의 슬랩 라벨을 OCR로 읽고 등급사·등급·인증번호를 추출한 뒤 공식 인증조회가 일치할 때만 검증 레퍼런스로 반영합니다. 공식 조회가 차단되거나 안전 대기시간이 필요한 경우 삭제하지 않고 다음 실행에서 이어서 처리합니다.

## OCR이 못 읽는 사진

사진과 같은 이름의 JSON 보조파일을 만들 수 있습니다.

예: `pikachu01.jpg` + `pikachu01.json`

```json
{
  "game": "pokemon",
  "company": "PSA",
  "grade": 10,
  "certification_id": "12345678",
  "card_name": "Pikachu",
  "card_number": "025/165"
}
```

## 실제 RAW 등급 보정학습까지 반영하려면

슬랩 사진만으로는 RAW 카드 등급 보정값을 직접 학습하지 않습니다. 슬랩 라벨에 정답이 노출되어 있어 모델 오염이 생길 수 있기 때문입니다.

등급 받기 전에 프로그램이 해당 RAW 카드에 대해 계산했던 독립 예측값이 있으면 보조 JSON에 `raw_pred`를 추가하세요.

```json
{
  "game": "pokemon",
  "company": "PSA",
  "grade": 10,
  "certification_id": "12345678",
  "raw_pred": 9.5
}
```

이 경우 공식 인증번호와 실제 등급이 일치한 뒤 RAW 보정학습에도 반영됩니다.

## JSON/CSV 결과 파일 직접 넣기

다음 필드가 들어 있는 JSON/JSONL/CSV도 `drop/` 아래에 넣을 수 있습니다.

- `company` 또는 `grader`
- `certification_id` 또는 `cert_no`
- `actual_grade` 또는 `actual` 또는 `grade`
- `raw_pred` 또는 `predicted_raw`
- 선택: `game`, `card_id`, `card_key`, `pred`, `vision`

예:

```json
{
  "samples": [
    {
      "game": "pokemon",
      "company": "PSA",
      "certification_id": "12345678",
      "actual_grade": 10,
      "raw_pred": 9.5
    }
  ]
}
```

수동 입력값만으로는 학습하지 않으며 공식 인증조회 또는 기존 검증 레지스트리의 정확한 회사+인증번호+등급 일치가 필요합니다.
