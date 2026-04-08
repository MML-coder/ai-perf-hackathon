# Nginx & RHEL Tuning Playbook

This document serves as the **agent knowledge base** for performance tuning. It contains proven tuning strategies that the autonomous agent can apply.

## Tuning Philosophy

1. **Measure First** - Always benchmark before and after
2. **One Change at a Time** - Isolate the impact of each tuning
3. **Document Everything** - Log what was changed and why
4. **Rollback Ready** - Know how to undo every change

---

## Priority Tuning Areas (Based on Problem Statement)

The customer reports degradation for **small and medium files**. Focus areas:

| Priority | Area | Impact on Small/Medium |
|----------|------|------------------------|
| 1 | Nginx Worker Configuration | High |
| 2 | sendfile & tcp_nopush | High |
| 3 | Kernel Network Tuning | High |
| 4 | File Descriptor Limits | Medium |
| 5 | Buffer Tuning | Medium |
| 6 | Disk I/O Tuning | Medium (for medium files) |

---

## 1. Nginx Worker Configuration

### Diagnostic Commands

```bash
# Check current worker config
grep -E "worker_processes|worker_connections" /etc/nginx/nginx.conf

# Check CPU cores available
nproc

# Check current worker processes
ps aux | grep nginx | grep worker | wc -l
```

### Tuning: Worker Processes

**File**: `/etc/nginx/nginx.conf`

```nginx
# Set to number of CPU cores (or 'auto')
worker_processes auto;

# Alternative: explicit count
worker_processes 16;  # for 16-core system
```

**Why**: Each worker handles connections independently. Too few = CPU underutilized. Too many = context switching overhead.

### Tuning: Worker Connections

```nginx
events {
    worker_connections 4096;  # or higher
    use epoll;                # Linux-optimized
    multi_accept on;          # Accept multiple connections at once
}
```

**Why**: 
- `worker_connections` limits concurrent connections per worker
- `epoll` is more efficient than `select/poll` on Linux
- `multi_accept` reduces syscalls

### Apply & Verify

```bash
# Test config
nginx -t

# Reload without downtime
nginx -s reload

# Verify workers
ps aux | grep nginx
```

---

## 2. sendfile & TCP Optimizations

### Diagnostic Commands

```bash
# Check current sendfile setting
grep -E "sendfile|tcp_nopush|tcp_nodelay" /etc/nginx/nginx.conf
```

### Tuning: sendfile

**File**: `/etc/nginx/nginx.conf` (in `http` block)

```nginx
http {
    sendfile on;           # Use kernel sendfile() - CRITICAL
    tcp_nopush on;         # Send headers in one packet
    tcp_nodelay on;        # Disable Nagle's algorithm
    
    # Increase sendfile chunk size for medium/large files
    sendfile_max_chunk 512k;
}
```

**Why**:
- `sendfile`: Transfers files directly from disk to network socket in kernel space (zero-copy)
- `tcp_nopush`: Combines headers with first data chunk
- `tcp_nodelay`: Reduces latency for small packets

### Tuning: AIO for Large Files

```nginx
http {
    aio threads;
    directio 512k;        # Use direct I/O for files > 512k
    output_buffers 2 1m;  # Buffer size for large files
}
```

**Why**: For medium/large files, async I/O prevents worker blocking.

---

## 3. Kernel Network Tuning

### Diagnostic Commands

```bash
# Check current kernel params
sysctl net.core.somaxconn
sysctl net.core.netdev_max_backlog
sysctl net.ipv4.tcp_max_syn_backlog
sysctl net.ipv4.tcp_fin_timeout
```

### Tuning: sysctl Parameters

**File**: `/etc/sysctl.d/99-nginx-tuning.conf`

```bash
# Connection backlog
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# TCP memory and buffers
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# TCP keepalive (reduce idle connection overhead)
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 6

# TIME_WAIT handling
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_tw_reuse = 1

# SYN flood protection (but allow more connections)
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_tw_buckets = 400000
```

### Apply Kernel Parameters

```bash
# Apply immediately
sysctl -p /etc/sysctl.d/99-nginx-tuning.conf

# Or apply all
sysctl --system

# Verify
sysctl net.core.somaxconn
```

---

## 4. File Descriptor Limits

### Diagnostic Commands

```bash
# Check current limits
ulimit -n

# Check nginx process limits
cat /proc/$(pgrep -o nginx)/limits | grep "open files"

# Check system-wide limit
cat /proc/sys/fs/file-max
```

### Tuning: Increase Limits

**File**: `/etc/security/limits.conf`

```bash
# Add these lines
root soft nofile 65535
root hard nofile 65535
nginx soft nofile 65535
nginx hard nofile 65535
* soft nofile 65535
* hard nofile 65535
```

**File**: `/etc/systemd/system/nginx.service.d/limits.conf`

```ini
[Service]
LimitNOFILE=65535
```

**File**: `/etc/nginx/nginx.conf`

```nginx
worker_rlimit_nofile 65535;
```

### Apply

```bash
# Reload systemd
systemctl daemon-reload

# Restart nginx
systemctl restart nginx

# Verify
cat /proc/$(pgrep -o nginx)/limits | grep "open files"
```

---

## 5. Nginx Buffer Tuning

### Diagnostic Commands

```bash
grep -E "buffer|timeout" /etc/nginx/nginx.conf
```

### Tuning: Buffers for Small/Medium Files

**File**: `/etc/nginx/nginx.conf`

```nginx
http {
    # Client body (upload) buffers
    client_body_buffer_size 16k;
    client_max_body_size 10m;
    
    # Header buffers
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;
    
    # Response buffers
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
    
    # Timeouts
    client_body_timeout 12;
    client_header_timeout 12;
    send_timeout 10;
    keepalive_timeout 65;
    keepalive_requests 1000;
}
```

---

## 6. Disk I/O Tuning (For Medium Files)

### Diagnostic Commands

```bash
# Check current I/O scheduler
cat /sys/block/sda/queue/scheduler

# Check read-ahead
blockdev --getra /dev/sda

# Monitor I/O during benchmark
iostat -x 1
```

### Tuning: I/O Scheduler

```bash
# Set deadline or none (for NVMe)
echo "mq-deadline" > /sys/block/sda/queue/scheduler

# For NVMe
echo "none" > /sys/block/nvme0n1/queue/scheduler
```

### Tuning: Read-Ahead

```bash
# Increase read-ahead (good for sequential reads)
blockdev --setra 4096 /dev/sda
```

### Tuning: Persistent via Tuned

```bash
# Use tuned profile
tuned-adm profile throughput-performance

# Or network-latency for low latency
tuned-adm profile network-latency
```

---

## 7. Open File Cache (Critical for Many Small Files)

### Tuning

**File**: `/etc/nginx/nginx.conf`

```nginx
http {
    # Cache file descriptors and metadata
    open_file_cache max=200000 inactive=20s;
    open_file_cache_valid 30s;
    open_file_cache_min_uses 2;
    open_file_cache_errors on;
}
```

**Why**: With 2.5M small files, caching file descriptors drastically reduces syscalls.

---

## 8. Gzip Compression (Trade CPU for Bandwidth)

### Tuning

```nginx
http {
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript;
    gzip_min_length 256;
}
```

**Note**: For small files (64 bytes), compression overhead may not be worth it. Test both ways.

---

## Rollback Procedures

### Nginx Config Rollback

```bash
# Before making changes, backup
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup.$(date +%Y%m%d%H%M%S)

# To rollback
cp /etc/nginx/nginx.conf.backup.<timestamp> /etc/nginx/nginx.conf
nginx -t && nginx -s reload
```

### Sysctl Rollback

```bash
# Remove the tuning file
rm /etc/sysctl.d/99-nginx-tuning.conf
sysctl --system
```

### Limits Rollback

```bash
# Remove added lines from /etc/security/limits.conf
# Remove /etc/systemd/system/nginx.service.d/limits.conf
systemctl daemon-reload
systemctl restart nginx
```

---

## Quick Tuning Checklist

Run these diagnostics first:

```bash
# 1. Check nginx config
nginx -t
cat /etc/nginx/nginx.conf

# 2. Check worker processes
ps aux | grep nginx
nproc

# 3. Check file limits
ulimit -n
cat /proc/$(pgrep -o nginx)/limits

# 4. Check kernel params
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog

# 5. Check disk I/O
iostat -x 1 5
```

Then apply tunings in this order:

1. [ ] worker_processes = auto (or CPU count)
2. [ ] worker_connections = 4096+
3. [ ] sendfile = on
4. [ ] tcp_nopush = on
5. [ ] tcp_nodelay = on
6. [ ] open_file_cache enabled
7. [ ] File descriptor limits increased
8. [ ] Kernel sysctl tuning applied
9. [ ] Tuned profile set (throughput-performance)

---

## Agent Decision Tree

```
IF requests/sec low for small files:
  → Check worker_connections
  → Enable open_file_cache
  → Increase file descriptor limits

IF requests/sec low for medium files:
  → Check sendfile enabled
  → Check disk I/O (iostat)
  → Enable aio threads
  → Tune sysctl buffers

IF high latency:
  → Check tcp_nodelay
  → Check buffer sizes
  → Check keepalive settings

IF socket errors:
  → Increase somaxconn
  → Increase backlog
  → Increase file descriptors

IF timeouts:
  → Check worker_processes
  → Check I/O wait
  → Increase timeout values
```

---

## Lessons Learned

> **Add entries here as you discover what works/doesn't work**

| Date | Tuning | Result | Notes |
|------|--------|--------|-------|
| 2026-04-08 | open_file_cache max=500000 | **FAILED** | Caused "Too many open files" - with 112 workers, total FDs exceeded system limits |
| 2026-04-08 | open_file_cache max=10000 | **SUCCESS** | 10K per worker * 112 workers = 1.12M max FDs, within limits. Small files: 424K → 1.28M rps (+202%) |
| 2026-04-08 | worker_rlimit_nofile 65535 | **REQUIRED** | Must set per-worker limit AND systemd LimitNOFILE |
| 2026-04-08 | access_log off | **SUCCESS** | Reduces I/O overhead, significant for high-throughput |
| 2026-04-08 | keepalive_requests 10000 | **SUCCESS** | Reduces connection overhead for benchmark |
| 2026-04-08 | aio threads + directio 512k | **APPLIED** | For medium files (2MB) |
| 2026-04-08 | NVMe scheduler=none | **APPLIED** | Lowest overhead for NVMe |
| 2026-04-08 | Read-ahead 8192 | **APPLIED** | Better for 2MB files |

### Network Bandwidth Analysis (Critical Finding)

**Medium files are NETWORK-LIMITED, not Nginx-limited:**

```
Medium file size: 2MB
Requests/sec: 1,400
Throughput: 2MB × 1,400 = 2.8 GB/s = 22.4 Gbps
Network capacity: 25 Gbps
Utilization: 22.4 / 25 = 89.6%
```

**Conclusion**: Medium file rps cannot improve significantly without:
- Faster network (100Gbps)
- Compression (if files are compressible)
- Smaller file responses

This is NOT a misconfiguration - it's physics.

### Critical Findings

**open_file_cache Calculation:**
```
max_cache_entries = worker_rlimit_nofile / 2  # Leave room for connections
total_max = max_cache_entries * num_workers
```

For 112-core system with ulimit 65535:
- Safe per-worker: ~10,000-30,000
- Total capacity: 1.1M - 3.3M cached files

**Symptom → Cause Mapping:**
| Symptom | Likely Cause |
|---------|--------------|
| "Too many open files" in error.log | open_file_cache max too high OR ulimit too low |
| Non-2xx responses during benchmark | File descriptor exhaustion |
| Homepage fast, small files slow | Missing open_file_cache |
| Medium files timeout | Disk I/O bottleneck (not yet solved) |

---

## References

- [Nginx Performance Tuning](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [Linux Kernel Network Tuning](https://www.kernel.org/doc/Documentation/sysctl/net.txt)
- [RHEL Performance Tuning Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/monitoring_and_managing_system_status_and_performance)
