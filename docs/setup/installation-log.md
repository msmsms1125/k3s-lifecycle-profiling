# K3s Installation Log

## Master Node Installation

Date: 2026-01-19 18:39:02 KST
Hostname: [MASTER_NODE]
K3s Version: v1.34.3+k3s1

### Installation
```bash
curl -sfL https://get.k3s.io | sh -
```

Installation completed successfully.
Service status: running
Memory usage at startup: 1.4GB

### Connection Information

Master IP: [REDACTED - Tailscale VPN]
Port: 6443

Note: Token stored in `/var/lib/rancher/k3s/server/node-token` on master node.

### Worker Installation

SSH to worker node and run:
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://[MASTER_IP]:6443 \
  K3S_TOKEN=[REDACTED] \
  sh -
```

## Next Steps

1. Install worker node
2. Verify cluster (both nodes ready)
3. Install netdata for monitoring
4. Run baseline system test

## Worker Node Installation

Date: 2026-01-19
Hostname: [WORKER_NODE]
Status: Connected successfully

Cluster Status:
```
NAME            STATUS   ROLES           AGE     VERSION
master-node     Ready    control-plane   10m     v1.34.3+k3s1
worker-node     Ready    <none>          3m      v1.34.3+k3s1
```

Total Pods Running: 8
System pods operational (coredns, traefik, metrics-server, etc.)
