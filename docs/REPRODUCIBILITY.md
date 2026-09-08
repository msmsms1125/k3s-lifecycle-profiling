# Reproducibility guide

이 저장소의 재현성은 **오프라인 코드 검증**과 **실제 클러스터 재실험**을 분리해서
판단합니다. 원래 Raspberry Pi 테스트베드는 더 이상 사용할 수 없으므로 CI 통과를
새 benchmark 결과로 해석하면 안 됩니다.

## 현재 실행 가능한 검증

아래 명령은 K3s, Netdata, 모델 파일 없이 실행할 수 있습니다.

```bash
python -m pip install -r requirements.txt
python tools/build_portfolio_summary.py --check
python tools/verify_repository.py
MPLBACKEND=Agg python -m unittest discover -s tests -v
find scripts -name '*.sh' -print0 | xargs -0 -n1 bash -n
```

| 검증 항목 | 확인하는 내용 | 확인하지 못하는 내용 |
|---|---|---|
| Portfolio evidence check | 공개 로그 60개와 추적 중인 시간 요약 CSV의 일치 | 원래 장비의 재실행 성공 |
| Repository verifier | Python 문법, 문서 링크, 17개 step 구조, 의존성 선언, prompt 구성 | 실제 클러스터 명령 성공 여부 |
| Redaction gate | 공개 로그의 사용자 홈 경로, 사설 IP, secret 형태 값 | Git 과거 commit의 완전한 이력 삭제 |
| Step17 unit tests | SSE token 판별, 요청 schedule, 분석 guard | 실제 TinyLlama 응답 품질 |
| Slow SSE integration test | 1초 응답 중에도 2 RPS dispatch가 유지되는지 | Raspberry Pi에서의 처리량과 지연시간 |
| Shell syntax | 모든 `*.sh`의 Bash 문법 | `kubectl`, `systemctl`, Netdata API의 runtime 동작 |

GitHub Actions의 `Repository quality` workflow가 pull request와 push마다 같은 검증을
실행합니다.

## Step17 재실험 시 보존해야 할 파일

새 장비에서 Step17을 실행할 경우 run별로 다음 자료가 모두 있어야 결과를
`validated`로 분류할 수 있습니다.

| 종류 | 경로 예시 | 목적 |
|---|---|---|
| 이벤트 메타데이터 | `logs/redacted/.../run_N.log` | START/READY/SCHEDULE_END/REQUESTS_DONE/END 경계 확인 |
| 요청 원본 | `logs/redacted/.../run_N_requests.csv` | dispatch, 성공률, TTFT, latency 재계산 |
| 부하 요약 | `logs/redacted/.../run_N_load_summary.json` | planned/achieved RPS와 성공 요청 수 확인 |
| 자원 원본 | `data/netdata/.../run_N/*.csv` | CPU/RAM/Disk/Network 통계 재계산 |
| 분석 결과 | `results/.../run_N/stats.csv` 및 그래프 | 원본에서 생성된 파생 산출물 |
| 환경 snapshot | K3s/OS/kernel/image digest/model checksum | 실행 환경 식별 |

원시 자료가 하나라도 빠지면 파생 통계는 독립적으로 재검산할 수 없습니다. 기존
Step17 결과가 검증 제외된 이유도 이 조건을 충족하지 못했기 때문입니다.

## 공개 로그 익명화 규칙

- 실제 사설 IP와 hostname 대신 `worker-a`, `worker-b`, `worker-c` 같은 안정적인
  alias를 사용합니다.
- 로컬 절대 경로는 `<repo-root>/...`로 바꿉니다.
- 공개 로그에는 token, password, API key를 기록하지 않습니다.
- alias는 같은 노드를 일관되게 나타내므로 run 간 배치 차이는 분석할 수 있지만,
  실제 네트워크 정보는 노출하지 않습니다.

이 검사는 현재 tree의 재노출을 막기 위한 장치입니다. 이미 공개된 Git 이력에서 값을
완전히 제거하려면 별도의 history rewrite가 필요하며, 이 작업에는 포함하지 않습니다.

## 해석 가능한 범위

- 이벤트 timestamp에서 계산한 라이프사이클 처리시간은 기술통계로 사용할 수 있습니다.
- 5초 평균 자원 시계열은 경향 관찰에만 사용합니다.
- 기존 Step17 수치는 portfolio 성과나 지속 1 RPS의 근거로 사용하지 않습니다.
- 새 장비에서 얻은 결과는 과거 결과와 섞지 않고 별도 환경으로 보고해야 합니다.

세부 결과 분류는 [Result validity and correction record](RESULT_VALIDITY.md), 수치별
출처와 허용하는 표현은 [Evidence map](EVIDENCE_MAP.md)을 참고하세요.
