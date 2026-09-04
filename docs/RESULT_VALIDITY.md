# Result validity and correction record

이 문서는 저장소에 보존된 결과 중 무엇을 근거로 사용할 수 있는지 명확히 구분합니다.
수치를 새로 추정하거나 재실험한 것처럼 표현하지 않는 것이 원칙입니다.

## 왜 교정 기록이 필요한가

과거 실험에 사용한 ARM64 노드는 현재 사용할 수 없고, `data/netdata/`의 원시 CSV와
step17 request CSV도 저장소에 보존되어 있지 않습니다. 따라서 새 분석 코드로 기존
resource 통계를 재생성하거나 수치가 맞다고 독립적으로 검증할 수 없습니다.

## 사용할 수 있는 결과

- 공개된 이벤트 로그의 `START_EPOCH`, `READY_EPOCH`, `END_EPOCH` 차이
- run 수와 실험 순서
- 당시 생성된 그래프를 실험 과정의 예시로 보여주는 것

처리시간은 초 단위 timestamp에 기반한 기술통계입니다. 특히 step02의 `END_EPOCH`는
Ready 이후 30초 안정화 구간을 포함하므로, master 시작시간에는 `T_READY_SEC`를
사용해야 합니다.

## 참고용으로만 사용할 결과

- 5초 평균으로 export한 CPU, RAM, Disk, Network 시계열
- 해당 시계열에서 파생된 peak, mean, AUC
- run 수가 1개뿐인 step09와 step16
- 필드가 비어 있는 master summary의 step06과 step08

5초 간격은 1~10초 내외의 lifecycle 이벤트를 표현하기에 성기므로 peak가 누락되거나
평균값이 주변 구간에 크게 좌우될 수 있습니다. AUC 단위와 chart dimension도 원본이
없으면 다시 확인할 수 없습니다.

## 검증에서 제외한 결과

`results/step17_infer_load_1rps_tinyllama_http/`의 기존 결과는 지속적인 1 RPS 부하의
증거로 사용하지 않습니다.

1. 기존 load generator가 요청을 순차 실행해 응답시간이 다음 요청 dispatch를 막았습니다.
2. 기존 summary에는 평균 client delay가 약 61~94초로 누적되어 있습니다.
3. CPU peak 100% 초과, Disk utilization 100% 초과, 음수 AUC, 대부분 0인 network 값이 있습니다.
4. 원시 Netdata/request CSV가 없어 올바른 방법으로 재계산할 수 없습니다.

파일은 연구 과정과 오류 교정의 추적성을 위해 삭제하지 않았습니다. 단, README의
성과 수치나 외부 benchmark 비교에는 사용하지 않습니다.

## 코드에서 수정한 내용

- step17 load를 concurrent open-loop dispatch로 변경
- `LOAD_END_EPOCH`를 요청 schedule 종료로, `REQUESTS_DONE_EPOCH`를 실제 완료로 분리
- first response byte가 아닌 SSE generated-text event로 TTFT 계산
- timestamp 정렬과 중복 제거 후 AUC 계산
- utilization 범위와 metric column을 검증하고 이상 시 분석 실패
- Netdata network 송수신 값을 방향이 아닌 magnitude로 분석
- 분석 실패를 `run_all.sh`에서 숨기지 않음
- 공개 로그에서 node hostname/IP/base URL 제외

## 재실험 없는 상태에서의 해석 원칙

- 교정 코드의 존재를 새 실험 결과로 표현하지 않습니다.
- 라이프사이클 시간과 5초 resource 측정의 신뢰 수준을 분리합니다.
- 숫자가 비정상이어도 임의 보정하거나 삭제하지 않고 검증 제외 사유를 기록합니다.
- 향후 다른 장비에서 실행할 경우 원시 CSV, request CSV, 소프트웨어 버전, 실험 설정을
  하나의 run artifact로 함께 보존합니다.
