# Portfolio review guide

이 문서는 채용 담당자나 면접관이 저장소를 짧게 검토할 때 볼 순서와, 프로젝트를
설명할 때 지켜야 할 증거 범위를 정리합니다. 새 Raspberry Pi 실험을 했다는 인상을
주지 않는 것이 가장 중요한 원칙입니다.

## 5분 저장소 리뷰 동선

| 시간 | 확인할 내용 | 보여주는 역량 |
|---:|---|---|
| 0~1분 | [README](../README.md)의 1분 요약과 lifecycle 그래프 | 문제 정의와 결과 전달 |
| 1~2분 | [Case study](PORTFOLIO_CASE_STUDY.md)의 측정 오류 교정 과정 | 실험 설계와 비판적 검증 |
| 2~3분 | [Evidence map](EVIDENCE_MAP.md)의 A/B/X 등급 | 주장과 근거의 추적성 |
| 3~4분 | [Step17 load generator](../scripts/step17_infer_load_1rps_tinyllama_http/load_1rps.py)와 [tests](../tests/) | open-loop 부하 설계와 회귀 테스트 |
| 4~5분 | [재현성 문서](REPRODUCIBILITY.md)와 [품질 검사 진입점](../tools/run_offline_checks.py) | 제약이 있는 환경에서의 품질 관리 |

## 30초 소개

Raspberry Pi 기반 ARM64 K3s 클러스터에서 시작, 배포, 스케일, 재시작, 삭제와
TinyLlama workload를 17개 시나리오로 자동화한 프로젝트입니다. 프로젝트를 다시
감사하면서 안정화 대기시간이 처리시간에 섞인 문제와 실제 1 RPS를 만들지 못한
순차 부하 생성기를 발견했습니다. 장비가 없어진 뒤에는 새 결과를 주장하지 않고,
공개 로그에서 재계산 가능한 7개 시간 지표만 포트폴리오 수치로 남기고 테스트와
CI로 근거의 일관성을 검증했습니다.

## 이력서용 문장 예시

- ARM64 K3s 홈랩의 17개 lifecycle/workload 시나리오를 shell과 Python으로
  자동화하고 반복 실행 산출물 구조를 설계
- 공개 이벤트 로그 60개에서 7개 지표, 70개 시간 관측값을 재집계하고 주장별
  evidence grade와 CI 회귀 검사를 구축
- lifecycle 완료시간과 안정화 대기시간의 혼입, 순차 요청 기반 1 RPS 부하의
  방법론 오류를 식별하고 open-loop dispatch와 분석 guard로 교정

위 문장은 **교정 코드가 실제 Raspberry Pi에서 재실행되었다고 표현하지 않습니다.**
처리량 개선률, 자원 사용량 절감률, Step17 성능값은 근거가 없어 추가하면 안 됩니다.

## 면접에서 설명할 핵심 결정

### 왜 평균 하나 대신 전체 점·중앙값·범위를 보여줬나?

각 지표의 표본이 10회로 작고 일부 run의 편차가 큽니다. 예를 들어 Nginx apply는
중앙값 3.5초와 평균 6.8초가 다르므로 평균만 제시하면 분포를 오해할 수 있습니다.
그래프에는 각 run, 범위, 중앙값과 평균을 함께 표시했습니다.

### 왜 Phase A와 Phase B를 비교하지 않았나?

노드 수와 workload가 동시에 달라졌기 때문에 차이를 특정 원인에 귀속할 수 없습니다.
따라서 각 phase 내부의 기술통계로만 보고하고 통제된 성능 비교라는 표현을 피했습니다.

### 왜 과거 Step17 결과를 삭제하지 않았나?

측정 실패도 연구 과정의 일부이며 오류의 원인과 교정 내용을 추적할 수 있어야 합니다.
파일은 보존하되 [결과 유효성 기록](RESULT_VALIDITY.md)에서 X 등급으로 분리해 성과
수치로 사용하지 않습니다.

### 하드웨어 없이 무엇을 검증했나?

로그 기반 시간 재계산, 문서 링크와 익명화, Python 문법, mock SSE를 이용한 요청
schedule, 분석 guard, shell 문법을 검증합니다. 이는 저장소와 교정 코드의 일관성을
보장하지만 실제 K3s/TinyLlama 성능을 보장하지 않습니다.

## 한 명령으로 확인하기

의존성을 설치한 뒤 다음 명령을 실행합니다.

```bash
python tools/run_offline_checks.py
```

이 명령은 저장소 검사, 증거 요약 drift 검사, 단위 테스트와 shell 문법 검사를
순서대로 실행합니다. Bash가 없는 환경에서는 shell 검사를 건너뛰며, CI에서는
`--require-shell-syntax`로 Bash가 없을 때도 실패하도록 실행합니다.

## 주장 전 최종 체크

- 수치가 [Evidence map](EVIDENCE_MAP.md)의 A 등급인가?
- 표본 수, 관측 환경과 1초 timestamp 해상도를 함께 밝혔는가?
- Phase 사이 차이를 인과관계나 일반 성능으로 표현하지 않았는가?
- 교정 코드를 새 하드웨어 결과처럼 표현하지 않았는가?
- CPU/RAM/Disk/Network와 Step17 과거 수치를 성과에서 제외했는가?
