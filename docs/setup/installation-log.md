# K3s Installation Log

## Master Node Installation

Date: 2026-01-19 18:39:02 KST
Hostname: yhgwpi
K3s Version: v1.34.3+k3s1

### Installation
```bash
curl -sfL https://get.k3s.io | sh -
```

Installation completed successfully.
Service status: running
Memory usage at startup: 1.4GB

### Connection Information

Master IP (Tailscale): 100.125.64.56
Port: 6443

Note: Token stored in `/var/lib/rancher/k3s/server/node-token` on master node.

### Worker Installation

SSH to worker node and run:
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://100.125.64.56:6443 \
  K3S_TOKEN=$(cat /var/lib/rancher/k3s/server/node-token) \
  sh -
```

Or manually with token from master.

## Next Steps

1. Install worker node
2. Verify cluster (both nodes ready)
3. Install netdata for monitoring
4. Run baseline system test

## Worker Node Installation

Date: 2026-01-19
Hostname: yhsensorpi
Status: Connected successfully

Cluster Status:
```
NAME         STATUS   ROLES           AGE     VERSION
yhgwpi       Ready    control-plane   10m     v1.34.3+k3s1
yhsensorpi   Ready    <none>          3m      v1.34.3+k3s1
```

Total Pods Running: 8
- coredns: 1
- traefik: 1 + 2 svclb
- metrics-server: 1
- local-path-provisioner: 1
- helm jobs: 2 (completed)
