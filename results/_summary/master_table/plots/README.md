## K3s Lifecycle Profiling 결과

---

### 그래프에 포함되지 않은 Step에 대한 현황 및 해석

#### 1.1 step01_system_idle (테이블/그래프에서 누락)

로그는 존재하지만 master_table 생성 과정에서 “runs not found”로 처리되어 결과에서 제외되었다. baseline 자체가 없는 게 아니라 집계 경로 규칙 불일치 또는 stats 산출물 누락으로 인해 테이블에 반영되지 않은 상태다.

---

#### 1.2 step06_scale_up_down (T_total만 존재)

duration(T_total)만 채워져 있어 CPU/RAM/Disk 비교 그래프에서는 제외된다. 의미적으로는 “시간 비용”은 비교 가능하지만, “자원 오버헤드 패턴”까지는 결론을 못 낸다.

---

#### 1.3 step08_cordon_uncordon (전체 지표 공란)

이벤트 자체 분석이 아니라 데이터 파이프라인이 아직 완성되지 않은 step에 가깝다. step08은 전후 60초 관찰처럼 관찰창이 짧고 구조가 달라 수정 예정이다.

---

#### 1.4 step09_stop_final_idle (n=1)

그래프에 표시되더라도 n=1은 분산/재현성 비교가 불가능하다. 참고값으로만 취급한다.

---

## 계획

- step01_system_idle을 master_table에 포함시키기  
- step06 자원 지표 채우기  
- step08 집계 규칙 통일  
- step09 반복 수행
