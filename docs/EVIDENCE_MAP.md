# Evidence map

이 문서는 포트폴리오에 사용한 주장과 저장소 안의 근거를 연결합니다. 같은 파일이
있다는 사실만으로 결과가 유효하다고 간주하지 않으며, 재계산 가능성에 따라 등급을
나눕니다.

## 증거 등급

| 등급 | 의미 | 포트폴리오 사용 원칙 |
|---|---|---|
| A | 공개 이벤트 로그에서 직접 재계산 가능 | 관측 환경과 표본 수를 붙여 수치 제시 가능 |
| B | 당시 생성된 파생 결과만 있고 원시 metric CSV는 없음 | 과정 예시 또는 정성적 참고로만 사용 |
| X | 측정 방법의 결함이나 데이터 이상을 확인함 | benchmark 주장에 사용하지 않음 |

## 수치 주장

| 주장 | 등급 | 근거 | 허용하는 표현 |
|---|:---:|---|---|
| K3s master Ready 평균 13.7초 | A | [step02 로그](../logs/redacted/step02_start_master/)의 `T_READY_SEC`, 10회 | 이 홈랩에서 관측된 초 단위 기술통계 |
| Nginx apply 완료 평균 6.8초 | A | [step04 로그](../logs/redacted/step04_apply_deployment/)의 `T_total`, 10회 | rollout 완료 이벤트의 관측 분포 |
| Nginx scale down/up 평균 5.3초 | A | [step06 로그](../logs/redacted/step06_scale_up_down/)의 `T_total`, 10회 | 두 동작을 합한 관측 시간 |
| Nginx rollout restart 평균 9.1초 | A | [step07 로그](../logs/redacted/step07_rollout_restart/)의 `T_total`, 10회 | rollout 완료 이벤트의 관측 분포 |
| TinyLlama 1→3 scale-up Ready 평균 43.6초 | A | [step14 로그](../logs/redacted/step14_scale_up_down_tinyllama_http/)의 `T_scale_up`, 10회 | Phase B 환경의 pod Ready 관측 시간 |
| TinyLlama 3→1 scale-down 평균 23.6초 | A | [step14 로그](../logs/redacted/step14_scale_up_down_tinyllama_http/)의 `T_scale_down`, 10회 | Phase B 환경의 종료 완료 관측 시간 |
| TinyLlama rollout restart Ready 평균 37.8초 | A | [step15 로그](../logs/redacted/step15_rollout_restart_tinyllama_http/)의 `T_READY_SEC`, 10회 | Phase B 환경의 pod Ready 관측 시간 |

위 통계는 [집계 스크립트](../tools/build_portfolio_summary.py)가 60개 로그에서 70개
시간 값을 다시 계산하며, 결과는
[CSV](../results/_summary/portfolio_event_timings.csv)로 보존합니다. Phase A와 B는
노드 수와 workload가 다르므로 두 phase 사이의 차이를 인과적 성능 비교로 표현하지
않습니다.

## 엔지니어링 주장

| 주장 | 근거 |
|---|---|
| Ready 이후 안정화 시간을 lifecycle 시간과 분리 | [step02 실행 스크립트](../scripts/step02_start_master/run_experiment.sh), [유효성 기록](RESULT_VALIDITY.md) |
| Step17을 wall-clock open-loop dispatch로 교정 | [load generator](../scripts/step17_infer_load_1rps_tinyllama_http/load_1rps.py), [회귀 테스트](../tests/test_load_generator.py) |
| 잘못된 metric과 AUC의 결과 저장을 차단 | [분석 코드](../analysis/plot_step17_tinyllama_infer_load.py), [guard 테스트](../tests/test_step17_analysis_guards.py) |
| 공개 산출물의 개인정보·환경 식별자 재유입 방지 | [repository verifier](../tools/verify_repository.py), [CI workflow](../.github/workflows/repository-quality.yml) |

## 참고 및 제외 항목

- CPU, RAM, Disk, Network 그래프와 통계는 **B 등급**입니다. 5초 집계의 한계가 있고
  원시 Netdata CSV가 없어 현재 코드로 재계산할 수 없습니다.
- 기존 Step17 summary는 **X 등급**입니다. 순차 요청으로 인해 계획한 1 RPS가
  유지되지 않았고, 비정상 resource 값도 발견되었습니다.
- 자세한 사유와 허용 범위는 [결과 유효성 문서](RESULT_VALIDITY.md)에 기록했습니다.
