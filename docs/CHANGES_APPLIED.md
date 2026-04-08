# All Changes Applied to SUT

**Date**: 2026-04-08  
**SUT**: e40-h34-000-r650.rdu2.scalelab.redhat.com  
**Benchmark Node**: e40-h37-000-r650.rdu2.scalelab.redhat.com

---

## Summary of Results

| Workload | Before | After | Change |
|----------|--------|-------|--------|
| homepage | 384,035 | 1,228,085 | **+220%** |
| small | 383,354 | 1,281,775 | **+234%** |
| medium | 1,401 | 1,400 | 0% (network-limited) |
| large | 186 | 186 | 0% (network-limited) |
| mixed | 2,265 | 2,247 | 0% (network-limited) |

---

## Changes on SUT (Nginx Server)

### 1. Nginx Configuration (`/etc/nginx/nginx.conf`)

```nginx
user nginx;
worker_processes auto;
worker_rlimit_nofile 65535;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

include /usr/share/nginx/modules/*.conf;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log off;
    
    sendfile on;
    sendfile_max_chunk 2m;
    output_buffers 4 2m;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    keepalive_requests 10000;
    types_hash_max_size 4096;
    
    client_body_buffer_size 16k;
    client_max_body_size 10m;

    aio threads;
    directio 512k;

    open_file_cache max=10000 inactive=60s;
    open_file_cache_valid 120s;
    open_file_cache_min_uses 1;
    open_file_cache_errors on;
    
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    include /etc/nginx/conf.d/*.conf;
}
```

**Key Changes from Default:**

| Setting | Default | New Value | Impact |
|---------|---------|-----------|--------|
| worker_rlimit_nofile | 1024 | 65535 | More file handles per worker |
| worker_connections | 1024 | 4096 | More concurrent connections |
| use epoll | select | epoll | Linux-optimized I/O |
| multi_accept | off | on | Accept multiple connections at once |
| access_log | on | off | Reduces I/O overhead |
| keepalive_requests | 100 | 10000 | Fewer connection setups |
| sendfile_max_chunk | 0 | 2m | Optimized for medium files |
| output_buffers | 1 32k | 4 2m | Better for large responses |
| aio | off | threads | Async I/O for large files |
| directio | off | 512k | Direct I/O for files >512k |
| open_file_cache | off | max=10000 | Cache file descriptors |

---

### 2. Systemd Service Limits

**File**: `/etc/systemd/system/nginx.service.d/limits.conf`

```ini
[Service]
LimitNOFILE=65535
```

**Apply**: 
```bash
systemctl daemon-reload
systemctl restart nginx
```

---

### 3. Kernel TCP Tuning

**File**: `/etc/sysctl.d/99-nginx-tcp-tuning.conf`

```bash
# TCP Buffer Sizes for 25Gbps
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.core.rmem_default = 1048576
net.core.wmem_default = 1048576
net.ipv4.tcp_rmem = 4096 1048576 67108864
net.ipv4.tcp_wmem = 4096 1048576 67108864

# TCP Congestion Control - BBR for high bandwidth
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

# Connection handling
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# TIME_WAIT optimization
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_tw_reuse = 1

# TCP window scaling
net.ipv4.tcp_window_scaling = 1
net.ipv4.tcp_timestamps = 1
net.ipv4.tcp_sack = 1
```

**Apply**:
```bash
sysctl -p /etc/sysctl.d/99-nginx-tcp-tuning.conf
```

---

### 4. NVMe I/O Tuning

```bash
# I/O Scheduler - none for NVMe (lowest overhead)
echo 'none' > /sys/block/nvme0n1/queue/scheduler

# Read-ahead - increased for sequential reads
blockdev --setra 8192 /dev/nvme0n1
```

**Make persistent** (add to /etc/rc.local or udev rule):
```bash
echo 'none' > /sys/block/nvme0n1/queue/scheduler
blockdev --setra 8192 /dev/nvme0n1
```

---

## Changes on Benchmark Node

### TCP Tuning

**File**: `/etc/sysctl.d/99-benchmark-tcp-tuning.conf`

```bash
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 1048576 67108864
net.ipv4.tcp_wmem = 4096 1048576 67108864
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.core.somaxconn = 65535
```

---

## What Did NOT Help (Lessons Learned)

| Change | Result | Why |
|--------|--------|-----|
| Reducing workers (112→32) | Hurt small files | Context switching not the bottleneck |
| open_file_cache max=500000 | FAILED | 500K × 112 workers = FD exhaustion |
| TCP tuning for medium files | No change | Already network-limited at 87% |

---

## Why Medium/Large Files Can't Improve

**Math:**
```
Medium file: 2 MB × 1,400 rps = 2.8 GB/s = 22.4 Gbps
Network: 25 Gbps
Utilization: 89.6%
```

**Conclusion**: We're saturating the network. Improvements require:
- 100 Gbps network
- Compression (files are binary, won't compress)
- Smaller files

---

## Rollback All Changes

```bash
# On SUT
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com '
# Restore nginx config
ls /etc/nginx/nginx.conf.backup.* | tail -1 | xargs -I{} cp {} /etc/nginx/nginx.conf

# Remove systemd override
rm -f /etc/systemd/system/nginx.service.d/limits.conf
systemctl daemon-reload

# Remove sysctl tuning
rm -f /etc/sysctl.d/99-nginx-tcp-tuning.conf
sysctl --system

# Reset NVMe
echo "mq-deadline" > /sys/block/nvme0n1/queue/scheduler
blockdev --setra 256 /dev/nvme0n1

# Restart nginx
nginx -t && systemctl restart nginx
'

# On Benchmark Node
ssh root@e40-h37-000-r650.rdu2.scalelab.redhat.com '
rm -f /etc/sysctl.d/99-benchmark-tcp-tuning.conf
sysctl --system
'
```

---

## Verification Commands

```bash
# Check nginx config
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com "nginx -T | head -100"

# Check worker count
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com "ps aux | grep 'nginx: worker' | wc -l"

# Check file limits
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com "cat /proc/\$(pgrep -o nginx)/limits | grep 'open files'"

# Check TCP settings
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com "sysctl net.ipv4.tcp_congestion_control"

# Run benchmark
ssh root@e40-h37-000-r650.rdu2.scalelab.redhat.com "./benchmark.sh test-run"
```
