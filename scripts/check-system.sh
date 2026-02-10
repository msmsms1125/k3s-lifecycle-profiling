# - 시스템 환경(OS/Kernel/CPU/Memory/Disk/Network)과 주요 소프트웨어(k3s/kubectl/containerd/netdata) 상태 출력 점검 스크립트
# - 성능 측정용 run 스크립트 아님. 실험 환경 스냅샷/검증 목적
#
# Artifacts:
# - stdout로만 출력
#
# Env variables:
# - (없음)
#
# Epoch definition:
# - (해당 없음) START/READY/END epoch 기록 안 함
# ============================================================
echo "==================================="
echo "    System Information Check"
echo "==================================="
echo ""

echo ">> OS Information"
cat /etc/os-release | grep -E "PRETTY_NAME|VERSION_ID"
echo "Kernel: $(uname -r)"
echo ""

echo ">> CPU Information"
echo "Model: $(lscpu | grep 'Model name' | cut -d: -f2 | xargs)"
echo "Cores: $(nproc)"
echo "Architecture: $(uname -m)"
echo ""

echo ">> Memory Information"
echo "Total: $(free -h | awk 'NR==2{print $2}')"
echo "Used: $(free -h | awk 'NR==2{print $3}')"
echo "Available: $(free -h | awk 'NR==2{print $7}')"
echo ""

echo ">> Disk Information"
df -h / | awk 'NR==1; NR==2{printf "Total: %s\nUsed: %s (%s)\nAvailable: %s\n", $2, $3, $5, $4}'
echo ""

echo ">> Network Information"
echo "Hostname: $(hostname)"
echo "IP Addresses:"
ip -4 addr show | grep inet | grep -v 127.0.0.1 | awk '{print "  " $NF ": " $2}'
echo ""

echo "==================================="
echo "    Software Check"
echo "==================================="
echo ""

# K3s
if command -v k3s &> /dev/null; then
    echo "✓ K3s: $(k3s --version | head -1)"
else
    echo "✗ K3s: Not installed"
fi

# kubectl
if command -v kubectl &> /dev/null; then
    echo "✓ kubectl: Installed"
else
    echo "✗ kubectl: Not installed"
fi

# containerd
if command -v containerd &> /dev/null; then
    echo "✓ containerd: $(containerd --version | awk '{print $3}')"
else
    echo "✗ containerd: Not installed"
fi

# netdata
if systemctl is-active --quiet netdata 2>/dev/null; then
    echo "✓ netdata: Running"
elif command -v netdata &> /dev/null; then
    echo "△ netdata: Installed but not running"
else
    echo "✗ netdata: Not installed"
fi

echo ""
echo "==================================="
