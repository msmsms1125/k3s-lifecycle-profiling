# Monitoring Setup

## Netdata Installation

Date: 2026-01-19
Version: v2.8.0-237-nightly

### Installation
```bash
wget -O /tmp/netdata-kickstart.sh https://get.netdata.cloud/kickstart.sh
sh /tmp/netdata-kickstart.sh --non-interactive
```

Installation successful.

### Configuration

Service status: running
Memory usage: ~150MB
CPU overhead: ~1%

Config file: /etc/netdata/netdata.conf
Listen address: 0.0.0.0:19999 (all interfaces)
Sampling interval: 1 second (default)

Note: 논문에서는 5초 간격 사용. 실험 시 API로 5초 간격 데이터 추출 예정.

### Access

Dashboard: http://[MASTER_IP]:19999
API endpoint: http://[MASTER_IP]:19999/api/v1/

### Metrics Available

System:
- CPU usage (per core and total)
- Memory usage (total, used, available, cached)
- Disk I/O (read/write MB/s)
- Network traffic (in/out)

K8s integration:
- Pod CPU/memory via cgroups
- Container monitoring
- Network interfaces (flannel, cni0, etc.)

### Data Collection for Experiments

API usage example:
```bash
curl "http://localhost:19999/api/v1/data?chart=system.cpu&after=-300&format=csv"
```

Parameters:
- chart: metric name
- after: seconds from now (negative = past)
- format: json, csv, ssv

## Next Steps

1. Create data collection scripts
2. Test baseline measurement
3. Automate experiment runs
