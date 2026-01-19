# 한 줄 요약

- 목표: 연구실 서버(2노드)에서 K3s 라이프사이클 이벤트별 자원 사용/처리시간을 측정하고 재현 가능한 형태로 정리한다.

## 실험 목적

K3s에서 특정 작업(시작, 배포, 스케일, 삭제 등)을 할 때 CPU/메모리/디스크 사용량이 얼마나 올라가는지와 그 작업이 끝나는 데 시간이 얼마나 소요되는지 직접 측정하여 정리한다.

또한 동일 시나리오를 반복 실행하여 측정 결과의 분포(평균, 표준편차)와 재현 안정성을 확인한다.

## 질문

1. 라이프사이클 이벤트 종류에 따라 CPU/Memory/Disk 사용량의 변화 패턴(peak, mean)은 어떻게 달라지는가?
2. 각 이벤트의 소요 시간은 어느 정도이며 반복 실행 시 변동 폭(표준편차)은 얼마나 발생하는가?
3. 클러스터 비활성 상태(system idle)와 클러스터 활성 상태(cluster idle)의 기본 오버헤드는 어떻게 다른가?

## 환경 및 수집 방법

- 환경: master 1 + worker 1 (Ubuntu 20.04/22.04), Tailscale 기반 원격 접속
- 모니터링: netdata를 사용하여 CPU/Memory/Disk 지표를 5초 간격으로 수집
- 이벤트 로그: ansible 실행 로그에 이벤트 시작/종료 시간(start/end timestamp)을 함께 기록
    - 예: 배포 이벤트 종료 시각은 kubectl rollout status 완료 시점으로 정의

## 실험 과정(2노드 환경)

2노드 환경에서는 다수 worker 추가 실험의 의미가 제한적, 운영 관점 이벤트 중심으로 구성

1. **System idle(클러스터 OFF baseline)**
    1. systemctl stop k3s + (worker) systemctl stop k3s-agent
    2. 측정: 300초 고정
2. **Start master**
    1. 시작: systemctl start k3s 실행 시각
    2. 끝: kubectl get nodes에서 master가 Ready가 되는 첫 시작
    3. 측정: start ~ end + (추가 안정화 60초)
3. **Cluster idle(클러스터 ON, 워크로드 없음)**
    1. 조건: nginx 없음, 노드 Ready 상태
    2. 측정: 300초 고정
4. **Apply deployment(nginx, 가능하면 replicas = 3 유지)**
    1. start: kubectl apply 실행 시각
    2. end: kubectl rollout status deployment/nginx 성공 시각
    3. 측정: start ~ end(rollout 완료까지)
5. **Deployment idle(안정화 구간)**
    1. apply 완료 후 300초 고정
6. **Scale up/down(1 → 3 → 1)**
    1. scale down: 3 → 1
        1. start: kubectl scale —replicas=1
        2. end: rollout status 완료
        3. 측정: start ~ end
    2. scale up: 1 → 3
        1. start: kubectl scale —replicas=3
        2. end: rollout status 완료
7. **Rollout restart(재배포 이벤트)**
    1. start: kubectl rollout restart deployment/nginx 실행 시각
    2. end: kubectl rollout status deployment/nginx
8. **Rollout Restart**
    1. start: kubectl rollout restart deployment/nginx
    2. end: kubectl rollout status 성공
    3. 측정: start ~ end
    4. 예상: CPU/Memory spike
9. **Cordon/Uncordon worker(스케줄링 제한/해제) 배포 시 pending/fail 관찰**
    1. Cordon worker
        1. start: kubectl cordon worker 실행
        2. end: 즉시(명령 완료)
        3. 측정: 전후 60초씩
    2. Deploy with cordoned node
        1. nginx scale=3 시도 → pending 관찰
        2. 측정: pending 지속 시간
    3. Uncordon worker
        1. start: kubectl uncordon worker
        2. end: pending pod들이 Running 되는 시점
        3. 측정: start ~ end
10. **Stop/최종 idle**
    1. start: systemctl stop k3s (+worker stop)
    2. end: kubectl get nodes 불가 → inactive 확인 시각
    3. 측정: stop 직후 60초 정도(리소스 하강 관찰)
11. **Delete Deployment**
    1. start: kubectl delete deployment nginx
    2. end: deployment 삭제 확인
    3. 측정: start ~ end
    4. 예상: Memory 감소 

## 분석 방법 및 산출물

**이벤트별 계산**

- Peak / Mean / AUC(누적 사용량) / Duration(소요 시간)

**반복 실험**

- 동일 시나리오를 25회 반복하여 평균 및 표준편차를 산출하고 boxplot으로 분포를 비교한다.

**시각화 산출물**

- Fig1 : 전체 타임라인에 이벤트 구간을 표시하고 자원 사용 변화를 함께 시각화
- Fig2: 이벤트별 분포(평균+표준편차 또는 boxplot 비교)

## 기대 효과

배포 / 스케일 / 롤아웃 / 스케줄링 제한 등의 운영 이벤트에서 발생하는 오버헤드 패턴을 정량적으로 확인할 수 있다.

## 한계

논문과 같은 다수 worker 확장 비교는 제한적이다. 대신 2노드 환경에 적합한 운영 이벤트 중심으로 목표를 명확하게 한다.
