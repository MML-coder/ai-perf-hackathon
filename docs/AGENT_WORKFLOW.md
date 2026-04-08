# Agent Workflow

This document describes how the autonomous AI agent operates to diagnose and fix Nginx performance issues.

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI Performance Agent                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐  │
│  │  Collect  │───►│  Analyze  │───►│ Remediate │───►│  Verify   │  │
│  └───────────┘    └───────────┘    └───────────┘    └───────────┘  │
│       │                │                │                │         │
│       ▼                ▼                ▼                ▼         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     Decision Log                             │   │
│  │  (All actions, reasoning, and results are recorded)          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │                                           │
          ▼                                           ▼
    ┌───────────┐                              ┌───────────┐
    │    DUT    │                              │ Benchmark │
    │  (Nginx)  │◄────────────────────────────►│   Node    │
    └───────────┘                              └───────────┘
```

## Phase 1: Collect

### Objectives
- Establish secure connection to DUT
- Gather system configuration
- Run baseline benchmark
- Collect real-time telemetry

### Actions

```bash
# 1. Connect to DUT
ssh root@<DUT_HOST>

# 2. Collect system info
uname -a
cat /etc/redhat-release
nproc
free -h
lsblk

# 3. Collect Nginx config
cat /etc/nginx/nginx.conf
nginx -t

# 4. Collect current performance metrics
systemctl status nginx
ps aux | grep nginx
ss -s
ulimit -n

# 5. Collect kernel parameters
sysctl -a | grep -E "net.core|net.ipv4.tcp"

# 6. Run baseline benchmark (from benchmark node)
./benchmark.sh baseline
```

### Output
- System profile document
- Current nginx.conf snapshot
- Baseline benchmark results
- Initial metrics snapshot

---

## Phase 2: Analyze

### Objectives
- Compare baseline against expected performance
- Identify bottlenecks
- Determine root cause
- Prioritize issues

### Analysis Framework

```
FOR each workload (small, medium, large):
    1. Compare current vs expected performance
    2. IF degradation detected:
        a. Check nginx configuration
        b. Check kernel parameters
        c. Check resource limits
        d. Check disk I/O
        e. Check network stack
    3. Correlate symptoms with known issues
    4. Rank issues by impact
```

### Key Diagnostics

| Symptom | Diagnostic Command | Likely Cause |
|---------|-------------------|--------------|
| Low req/sec, small files | `grep worker_connections nginx.conf` | Worker limits |
| Low req/sec, medium files | `iostat -x 1` | Disk I/O |
| High latency | `ss -s`, check TIME_WAIT | Connection limits |
| Socket errors | `ulimit -n`, check limits | File descriptors |
| Timeouts | `top`, check CPU/iowait | Resource exhaustion |

### Decision Matrix

```python
def analyze_results(baseline, current):
    issues = []
    
    # Check small file performance
    if current['small']['rps'] < baseline['small']['rps'] * 0.9:
        issues.append({
            'area': 'small_files',
            'severity': 'high',
            'likely_cause': ['worker_connections', 'open_file_cache', 'file_descriptors'],
            'check': ['nginx config', 'ulimit', 'sysctl']
        })
    
    # Check medium file performance
    if current['medium']['rps'] < baseline['medium']['rps'] * 0.9:
        issues.append({
            'area': 'medium_files', 
            'severity': 'high',
            'likely_cause': ['sendfile', 'disk_io', 'buffers'],
            'check': ['nginx config', 'iostat', 'sysctl']
        })
    
    return prioritize(issues)
```

### Output
- Root cause analysis document
- Prioritized list of issues
- Recommended tunings with reasoning

---

## Phase 3: Remediate

### Objectives
- Apply tunings safely
- One change at a time
- Log all changes with reasoning
- Verify config before applying

### Safety Protocol

```bash
# 1. ALWAYS backup before changing
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup.$(date +%s)

# 2. ALWAYS test config before reload
nginx -t

# 3. ALWAYS use reload, not restart (when possible)
nginx -s reload

# 4. ALWAYS verify change took effect
grep <setting> /etc/nginx/nginx.conf
```

### Tuning Application Order

1. **Nginx Configuration** (lowest risk)
   - worker_processes
   - worker_connections
   - sendfile, tcp_nopush, tcp_nodelay
   - open_file_cache

2. **System Limits** (medium risk)
   - File descriptor limits
   - Systemd service limits

3. **Kernel Parameters** (higher risk)
   - sysctl tuning
   - I/O scheduler

4. **System Services** (highest risk)
   - tuned profile
   - Service restarts

### Logging Format

```json
{
  "timestamp": "2026-04-08T10:30:00Z",
  "action": "modify_nginx_config",
  "setting": "worker_connections",
  "old_value": "1024",
  "new_value": "4096",
  "reasoning": "Current worker_connections (1024) is below recommended for high-concurrency workload. With 16 workers and 1000 benchmark connections, each worker handles ~63 connections. Increasing to 4096 provides headroom.",
  "evidence": "Baseline shows 415955 req/sec for small files with periodic timeout errors (7 timeouts). This suggests connection queue saturation.",
  "rollback": "Set worker_connections back to 1024 in /etc/nginx/nginx.conf and run nginx -s reload"
}
```

---

## Phase 4: Verify

### Objectives
- Run benchmark after each tuning
- Compare against baseline
- Validate improvement
- Detect regressions

### Verification Process

```bash
# 1. Run quick sanity test first
wrk -t4 -c100 -d10s http://test-machine/

# 2. If sanity passes, run full benchmark
./benchmark.sh after-<tuning-name>

# 3. Compare results
./compare-results.sh after-<tuning-name>

# 4. Log results
cat >> /root/hackathon-results/tuning_log.json << EOF
{
  "tuning": "<tuning-name>",
  "timestamp": "$(date -Iseconds)",
  "results": {
    "small_rps": <value>,
    "medium_rps": <value>,
    "change_pct": <value>
  },
  "verdict": "IMPROVED|STABLE|DEGRADED"
}
EOF
```

### Decision After Verification

```
IF improvement > 10%:
    → Keep change
    → Proceed to next tuning
    
IF -10% < change < 10%:
    → Keep change (may help in combination)
    → Proceed to next tuning
    
IF degradation > 10%:
    → Rollback immediately
    → Investigate why
    → Try alternative approach
```

---

## Iteration Loop

```
WHILE not_meeting_target:
    1. Analyze current state
    2. Select highest-priority tuning
    3. Apply tuning
    4. Verify impact
    5. IF degraded: rollback
    6. Log decision and results
    7. Update knowledge base
```

---

## Agent Outputs

### 1. Decision Log (decisions.json)

```json
{
  "session_id": "uuid",
  "start_time": "2026-04-08T10:00:00Z",
  "model": "claude-3-opus",
  "decisions": [
    {
      "step": 1,
      "action": "collect_baseline",
      "reasoning": "Need baseline metrics before tuning",
      "result": "Baseline captured: small=415955 rps, medium=1401 rps"
    },
    {
      "step": 2,
      "action": "analyze_config",
      "reasoning": "Check nginx.conf for common misconfigurations",
      "finding": "worker_connections=1024, sendfile=off",
      "recommendation": "Enable sendfile, increase worker_connections"
    }
  ],
  "token_usage": {
    "input": 12500,
    "output": 3200
  }
}
```

### 2. Tuning Report (report.md)

```markdown
# Performance Tuning Report

## Summary
- Initial: small=415955 rps, medium=1401 rps
- Final: small=520000 rps, medium=1800 rps
- Improvement: small=+25%, medium=+28%

## Tunings Applied
1. sendfile enabled (+15% medium files)
2. worker_connections increased (+5% overall)
3. open_file_cache enabled (+8% small files)

## Evidence
[Charts and detailed metrics]
```

### 3. Rollback Script (rollback.sh)

```bash
#!/bin/bash
# Auto-generated rollback script
cp /etc/nginx/nginx.conf.backup.1712567890 /etc/nginx/nginx.conf
rm /etc/sysctl.d/99-nginx-tuning.conf
sysctl --system
nginx -t && systemctl restart nginx
echo "Rollback complete"
```

---

## Model Information Tracking

```python
# Track token usage per action
token_log = {
    "model": "claude-3-opus",
    "session_id": "uuid",
    "actions": [
        {
            "action": "analyze_config",
            "input_tokens": 1500,
            "output_tokens": 400
        },
        {
            "action": "recommend_tuning",
            "input_tokens": 2000,
            "output_tokens": 600
        }
    ],
    "total_input": 12500,
    "total_output": 3200
}
```

---

## Error Handling

### Connection Failures

```bash
# Retry with backoff
for i in 1 2 3; do
    ssh root@$DUT_HOST "echo ok" && break
    sleep $((i * 5))
done
```

### Config Syntax Errors

```bash
# Always test before applying
nginx -t 2>&1
if [ $? -ne 0 ]; then
    echo "Config error, rolling back"
    cp $BACKUP_FILE /etc/nginx/nginx.conf
fi
```

### Benchmark Failures

```bash
# Check if benchmark completed
if [ $? -ne 0 ]; then
    echo "Benchmark failed, collecting diagnostics"
    dmesg | tail -50
    journalctl -u nginx --since "5 minutes ago"
fi
```

---

## Autonomous Operation Checklist

- [ ] Agent can SSH to both systems without interaction
- [ ] Agent has decision log template ready
- [ ] Agent has rollback scripts ready
- [ ] Agent knows baseline metrics
- [ ] Agent has tuning playbook loaded
- [ ] Agent can run benchmarks automatically
- [ ] Agent can detect improvement/degradation
- [ ] Agent can generate final report
