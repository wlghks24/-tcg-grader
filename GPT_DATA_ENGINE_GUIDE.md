# GPT AI Data Engine v2.5-safe

이 모듈은 ChatGPT / Code Interpreter에서 선택적으로 사용하는 진단·학습 도구입니다. 기존 TCG production collector를 자동 수정하거나 시세·출시·프로모 원본값을 임의 보간하지 않습니다.

## 원본 v2.5에서 수정한 핵심

- `train_test_split(..., test_state=42)` 오타를 `random_state=42`로 수정했습니다.
- 전체 데이터에 먼저 KNN 보간 후 train/test split 하던 데이터 누수 위험을 줄였습니다. 학습 비교는 train/test 분리 후 Pipeline 안에서 imputer를 학습합니다.
- 카드 시세, 통화, 등급, 카드번호, 출시일, 출처 URL, 지역, 언어, lineage 등 source-of-truth 컬럼은 기본 보호 대상입니다.
- IQR 이상치는 기본적으로 진단만 하며 자동 클리핑하지 않습니다. 실제 희귀 거래·급등락을 오류로 지우는 것을 방지합니다.
- 숫자/범주형 결측치 보간도 기본 OFF입니다. 사용자가 일반 분석용 컬럼에 대해 명시적으로 허용해야 실행됩니다.
- pandas/numpy/scikit-learn은 GPT 전용 선택 의존성입니다. production `requirements.txt`에는 추가하지 않아 태블릿/서버 런타임을 무겁게 만들지 않습니다.

## GPT에서 기본 사용

```python
from gpt_data_engine import run_gpt_pipeline

result = run_gpt_pipeline(data_source)
result['diagnostics']
```

기본 실행은 진단만 하고 값은 변경하지 않습니다.

## 일반 데이터에서 보간을 허용할 때

```python
from gpt_data_engine import CorrectionPolicy, run_gpt_pipeline

policy = CorrectionPolicy(
    allow_numeric_imputation=True,
    allow_categorical_imputation=True,
    allow_outlier_clipping=False,
)
result = run_gpt_pipeline(data_source, correction_policy=policy)
```

TCG source-of-truth 컬럼은 위 옵션을 켜도 자동 보정 대상에서 제외됩니다.

## 모델 학습

```python
result = run_gpt_pipeline(
    data_source,
    target_column='target',
    train_model=True,
)
print(result['optimization'])
```

회귀/분류를 자동 판정하고 동일 train/test split에서 median-imputer baseline과 KNN-imputer optimized RandomForest를 비교합니다. 결과가 좋아져도 production 모델로 자동 배포하지 않습니다.

## TCG 프로젝트 적용 원칙

이 엔진의 출력은 `진단 보조자료`로만 사용합니다. 실제 시세·출시·프로모 데이터의 수정/승격은 기존 `collection_verification_gate.py`, SELFREFINE 격리, 출처 교차검증 및 전체 회귀검사를 통과해야 합니다.
