# Medium File Performance Analysis

## TL;DR

**Medium files (2MB) are network-limited at 87% of 25Gbps.** No nginx/OS tuning can improve this without faster network hardware.

---

## Workload Characteristics

```lua
-- medium.lua
local COUNT = 250000  -- 250K files
-- Random access pattern
local idx = math.random(0, COUNT - 1)
```

| Property | Value |
|----------|-------|
| File count | 250,000 |
| File size | 2 MB each |
| Total data | 489 GB |
| Access pattern | Random (uniform distribution) |
| Requests in 60s | ~84,000 |
| Hit rate per file | 0.34% (84K/250K) |

---

## System Analysis

### Memory & Caching

```bash
# All 489GB of medium files fit in page cache
Mem: 502GB total, 475GB buff/cache
Cached: 492GB (includes all medium files)
```

**Finding**: Files ARE cached in RAM - disk I/O is NOT the bottleneck.

### CPU During Benchmark

```
%Cpu(s):  0.0 us,  0.9 sy,  0.0 ni, 95.3 id,  1.4 wa,  0.2 hi,  2.1 si
```

| Metric | Value | Meaning |
|--------|-------|---------|
| User | 0.0% | Minimal application CPU |
| System | 0.9% | Minimal kernel CPU |
| Idle | 95.3% | **CPU NOT saturated** |
| I/O Wait | 1.4% | **Disk NOT bottleneck** |
| Soft IRQ | 2.1% | Network interrupts |

**Finding**: CPU is 95% idle - NOT the bottleneck.

### Network Analysis

```
Transfer/sec: 2.74 GB/s = 21.9 Gbps
Network capacity: 25 Gbps
Utilization: 87.6%
```

**Finding**: Network IS the bottleneck at 87% utilization.

---

## Optimizations Attempted

### 1. Ring Buffers (Helped slightly with latency)

```bash
# Before
RX: 511, TX: 511

# After
ethtool -G eno12399np0 rx 2047 tx 2047
RX: 2047, TX: 2047
```

**Result**: Marginal improvement in latency variance.

### 2. NIC Queues (No improvement)

```bash
# Before
Combined: 8

# After
ethtool -L eno12399np0 combined 32
Combined: 32
```

**Result**: No measurable improvement (CPU wasn't the bottleneck).

### 3. Jumbo Frames MTU 9000 (FAILED)

```bash
ip link set eno12399np0 mtu 9000
```

**Result**: **Broke connectivity** - switch doesn't support jumbo frames.

**Rollback**: `ip link set eno12399np0 mtu 1500`

### 4. TCP Tuning (No improvement for medium)

```bash
# Applied BBR congestion control, 64MB buffers
net.ipv4.tcp_congestion_control = bbr
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
```

**Result**: No improvement for medium files (already network-saturated).

---

## Why Medium Files Can't Improve

### The Math

```
File size:        2 MB
Requests/sec:     1,400
Throughput:       2 MB × 1,400 = 2,800 MB/s = 2.74 GB/s
Network:          25 Gbps = 3.125 GB/s theoretical max
TCP overhead:     ~12% (headers, ACKs, etc.)
Effective max:    ~2.75 GB/s
Current:          2.74 GB/s
Utilization:      ~99% of effective max
```

### Bottleneck Hierarchy

```
1. Network bandwidth (25 Gbps)     ← BOTTLENECK
2. Disk I/O (NVMe, data cached)    ← NOT bottleneck
3. CPU (95% idle)                  ← NOT bottleneck
4. Memory (data in page cache)     ← NOT bottleneck
```

---

## What WOULD Improve Medium Files

| Change | Expected Improvement | Feasibility |
|--------|---------------------|-------------|
| 100 Gbps network | 4x throughput | Hardware upgrade |
| NIC bonding (2x 25G) | 2x throughput | Hardware/config |
| Smaller files | Proportional | Application change |
| Compression | Only if text data | Files are binary |
| HTTP/2 multiplexing | ~10-20% | Nginx config |
| HTTP/3 (QUIC) | ~10-20% | Nginx Plus only |

---

## Diagnostic Commands for Agent

```bash
# 1. Check if files are in page cache
free -h
cat /proc/meminfo | grep -E 'Cached|Buffers'

# 2. Monitor during benchmark
top -bn1 | head -15

# 3. Check network utilization
# Transfer/sec from wrk output, compare to link speed:
ethtool eno12399np0 | grep Speed

# 4. Calculate utilization
# If Transfer/sec > 80% of Speed, network is the bottleneck

# 5. Check NIC settings
ethtool -g eno12399np0  # Ring buffers
ethtool -l eno12399np0  # Queue count
ethtool -k eno12399np0  # Offloads
```

---

## Agent Decision Tree for Medium Files

```
IF medium files slow:
  1. Check Transfer/sec vs network speed
     IF > 80%: Network-limited, cannot improve via software
  
  2. Check I/O wait %
     IF > 10%: Disk bottleneck, enable sendfile/aio
  
  3. Check CPU idle %
     IF < 20%: CPU bottleneck, reduce workers or optimize
  
  4. Check page cache
     IF data < cache: Should be fast, check nginx config
     IF data > cache: Disk I/O will be factor
```

---

## Key Lessons

1. **Always calculate throughput vs network capacity first**
2. **Check if data fits in RAM before assuming disk bottleneck**
3. **Jumbo frames require switch support - test carefully**
4. **Ring buffers and NIC queues only help if packets are being dropped**
5. **TCP tuning helps latency, not throughput when network-saturated**
