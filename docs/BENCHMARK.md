# Benchmark Guide

## Overview

The benchmark suite uses `wrk` - a modern HTTP benchmarking tool capable of generating significant load.

## Workload Definitions

| Workload | Threads | Connections | Duration | File Size | File Count | Priority |
|----------|---------|-------------|----------|-----------|------------|----------|
| homepage | 16 | 1000 | 30s | N/A | 1 | Baseline |
| small | 16 | 1000 | 60s | 64 bytes | 2.5M | **HIGH** |
| medium | 16 | 300 | 60s | 2 MB | 250K | **HIGH** |
| large | 16 | 100 | 60s | 15 MB | 250 | Low |
| mixed | 16 | 100 | 60s | Mixed | Mixed | Validation |

### Workload Details

#### Homepage (Baseline)
- Simple request to `/`
- No Lua script
- Tests basic Nginx responsiveness
- **Target**: Maintain current performance

#### Small Files (Focus Area)
- Requests to 2.5 million small files (64 bytes each)
- Uses `/root/hackathon-tools/small.lua`
- Tests: file descriptor handling, connection efficiency
- **Target**: >10% improvement

#### Medium Files (Focus Area)
- Requests to 250,000 medium files (2 MB each)
- Uses `/root/hackathon-tools/medium.lua`
- Tests: disk I/O, sendfile, buffer management
- **Target**: >10% improvement

#### Large Files
- Requests to 250 large files (15 MB each)
- Uses `/root/hackathon-tools/large.lua`
- Tests: sustained throughput, TCP tuning
- **Target**: Maintain

#### Mixed (Validation)
- 70% small, 25% medium, 5% large
- Uses `/root/hackathon-tools/mixed.lua`
- Tests: real-world scenario
- **Target**: Improvement expected if small/medium improve

## Running Benchmarks

### Full Suite

```bash
# On benchmark node
cd /root
./benchmark.sh <name>

# Example
./benchmark.sh baseline
./benchmark.sh after-tuning
```

### Individual Workload

```bash
# Homepage only
wrk -t16 -c1000 -d30s --latency http://test-machine/

# Small files
wrk -t16 -c1000 -d60s --latency -s /root/hackathon-tools/small.lua http://test-machine/

# Medium files
wrk -t16 -c300 -d60s --latency -s /root/hackathon-tools/medium.lua http://test-machine/

# Large files
wrk -t16 -c100 -d60s --latency -s /root/hackathon-tools/large.lua http://test-machine/

# Mixed
wrk -t16 -c100 -d60s --latency -s /root/hackathon-tools/mixed.lua http://test-machine/
```

### Quick Sanity Test

```bash
# 10-second test to verify setup
wrk -t4 -c100 -d10s http://test-machine/
```

## Understanding Results

### Sample Output

```
Running 30s test @ http://test-machine/
  16 threads and 1000 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     2.55ms    1.81ms  43.95ms   84.92%
    Req/Sec    26.45k     2.46k   86.07k    92.10%
  Latency Distribution
     50%    2.24ms
     75%    2.97ms
     90%    4.05ms
     99%   10.07ms
  12659452 requests in 30.10s, 6.80GB read
Requests/sec: 420575.41
Transfer/sec:    231.41MB
```

### Key Metrics

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Requests/sec** | Throughput | Higher is better |
| **Latency Avg** | Mean response time | Lower is better |
| **Latency 99%** | Tail latency | Lower is better |
| **Transfer/sec** | Bandwidth | Higher is better |
| **Socket errors** | Connection issues | 0 is ideal |
| **Timeouts** | Timed-out requests | 0 is ideal |

### Interpreting Latency Distribution

```
50%    2.24ms   <- Median (half of requests faster than this)
75%    2.97ms   <- 75th percentile
90%    4.05ms   <- 90th percentile (tail latency starts here)
99%   10.07ms   <- 99th percentile (worst 1% of requests)
```

## Comparing Results

### Using compare-results.sh

```bash
./compare-results.sh <contestant-name>
```

### Output Interpretation

```
Workload   |  Baseline (rps) |   Current (rps) |   Change |   Status
----------------------------------------------------------------------
small      |          383354 |          422000 |    10.1% |   IMPROVED
medium     |            1401 |            1600 |    14.2% |   IMPROVED
```

| Status | Meaning |
|--------|---------|
| IMPROVED | >10% improvement |
| STABLE | Within +/-10% |
| DEGRADED | >10% regression |

## Baseline Results (Current State)

```
Workload   | Requests/sec | Latency (avg) | Transfer/sec
---------------------------------------------------------
homepage   |     420,575  |      2.55ms   |   231.41 MB
small      |     415,955  |      2.67ms   |   120.57 MB
medium     |       1,401  |    229.76ms   |     2.74 GB
large      |         186  |    514.67ms   |     2.74 GB
mixed      |       2,241  |    111.01ms   |     2.74 GB
```

### Observations

1. **Homepage & Small**: High throughput (~400K rps), low latency (~2.5ms)
   - These are efficient - small files fit in memory/cache

2. **Medium**: Low throughput (1,401 rps), high latency (230ms)
   - **This is the problem area**
   - 2MB files hitting disk I/O bottleneck

3. **Large**: Very low throughput (186 rps), very high latency (515ms)
   - Expected for 15MB files - bandwidth limited

4. **Mixed**: Dominated by file I/O characteristics

## Monitoring During Benchmark

### On DUT (While Benchmark Runs)

```bash
# Watch CPU usage
top -d1

# Watch disk I/O
iostat -x 1

# Watch network
sar -n DEV 1

# Watch Nginx connections
watch -n1 'ss -s'

# Watch Nginx workers
watch -n1 'ps aux | grep nginx'
```

### Key Indicators of Problems

| Symptom | Possible Cause |
|---------|----------------|
| High CPU % on nginx workers | Worker count mismatch, inefficient config |
| High iowait % | Disk I/O bottleneck, need sendfile tuning |
| Socket errors increasing | File descriptor limits, connection limits |
| Latency spikes | Buffer issues, context switching |

## Results Storage

```bash
# Results are saved to:
/root/hackathon-results/
├── <name>_homepage.json
├── <name>_small.json
├── <name>_medium.json
├── <name>_large.json
└── <name>_mixed.json

# Also raw output:
/root/hackathon-results/<name>_<workload>_<timestamp>_raw.txt
```

## Benchmark Best Practices

1. **Run multiple iterations** - Results can vary; run 3 times and average
2. **Wait between tests** - Let system stabilize (script waits 5s)
3. **Check for errors** - Socket errors or timeouts indicate problems
4. **Monitor DUT** - Watch system resources during benchmark
5. **Document changes** - Note what tuning was applied before each run
6. **Save all results** - Use descriptive names like `after-sendfile-tuning`
