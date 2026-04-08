# AI Performance Agent - RHEL/Nginx Optimization

Autonomous AI agent for diagnosing and resolving performance issues on RHEL systems running Nginx.

## Solution Overview

This solution implements an **AI-powered performance tuning agent** that:

1. **Collects** metrics before and after remediation (benchmark results, system configs)
2. **Analyzes** using Claude LLM for root cause analysis
3. **Logs all decisions** with data/reasoning for each tuning applied
4. **Tracks model usage** (input/output tokens per model)
5. **Generates reports** with full audit trail

### Requirements Compliance

| Requirement | Implementation |
|-------------|----------------|
| Benchmark before/after | `collector.py` runs wrk benchmarks, stores results |
| Log decision-making | `analyzer.py` decision_log with data/reason per tuning |
| Model info (tokens) | `llm.py` TokenUsage tracks input/output per model |
| Code in repo | `agent/` directory with all source code |
| README with instructions | This file (see Quick Start below) |
| Sample report | `reports/sample_report.md` |

## Problem Statement

Customer reports performance degradation in Nginx web server for small and medium-sized files after migrating to RHEL 9.7. The agent must:

1. **Collect** - Gather real-time performance telemetry
2. **Analyze** - Perform root cause analysis (RCA)
3. **Remediate** - Automatically apply tunings
4. **Report** - Generate human-readable recommendations

## Final Results

| Workload | Baseline (rps) | After Tuning (rps) | Improvement |
|----------|----------------|--------------------| ------------|
| homepage | 384,035 | 1,551,797 | **+304%** |
| small | 383,354 | 1,860,360 | **+385%** |
| medium | 1,401 | 2,921 | **+108%** |
| large | 186 | 394 | **+111%** |
| mixed | 2,265 | 4,751 | **+110%** |

**All workloads improved >100%!**

## Root Causes Identified

| Issue | Impact | Fix |
|-------|--------|-----|
| `open_file_cache off` | Small files slow | Enable with max=10000 |
| `worker_rlimit_nofile 1024` | FD exhaustion | Increase to 65535 |
| `worker_connections 1024` | Connection limits | Increase to 4096 |
| Default TCP buffers | Network inefficiency | 64MB buffers + BBR |
| Network interface selection | 25G vs 100G available | Agent discovers faster NICs |

## Environment

| System | Hostname | Role |
|--------|----------|------|
| DUT (Device Under Test) | e40-h34-000-r650.rdu2.scalelab.redhat.com | Nginx server (112 cores, 502GB RAM) |
| Benchmark Node | e40-h37-000-r650.rdu2.scalelab.redhat.com | Load generator (wrk) |

## Quick Start

### Running the AI Agent

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key
export ANTHROPIC_API_KEY="your-api-key"

# 3. Run the agent (full autonomous mode)
python -m agent \
  --sut e40-h34-000-r650.rdu2.scalelab.redhat.com \
  --benchmark e40-h37-000-r650.rdu2.scalelab.redhat.com

# 4. View the generated report
cat reports/report_*.md
```

### Agent CLI Options

```bash
# Use a specific model (sonnet, opus, haiku)
python -m agent --sut HOST --benchmark HOST --model opus

# Dry run (analyze but don't apply changes)
python -m agent --sut HOST --benchmark HOST --dry-run

# Use existing benchmark results
python -m agent --sut HOST --benchmark HOST --baseline baseline

# Skip benchmarks (faster for testing)
python -m agent --sut HOST --benchmark HOST --skip-benchmark
```

### Manual Workflow (Alternative)

```bash
# 1. SSH to benchmark node
ssh root@e40-h37-000-r650.rdu2.scalelab.redhat.com

# 2. Run baseline benchmark
./benchmark.sh baseline

# 3. SSH to DUT (from benchmark node or directly)
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com

# 4. Apply tunings (see docs/TUNING_PLAYBOOK.md)

# 5. Re-run benchmark and compare
./benchmark.sh after-tuning
./compare-results.sh after-tuning
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/CHANGES_APPLIED.md](docs/CHANGES_APPLIED.md) | All changes made to the SUT with rollback procedures |
| [docs/TUNING_PLAYBOOK.md](docs/TUNING_PLAYBOOK.md) | Agent knowledge base - tuning strategies |
| [docs/MEDIUM_FILE_ANALYSIS.md](docs/MEDIUM_FILE_ANALYSIS.md) | Deep dive on medium file optimization |
| [docs/FINDINGS_2026-04-08.md](docs/FINDINGS_2026-04-08.md) | Detailed tuning session findings |
| [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md) | How the autonomous agent operates |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Environment setup, SSH access |
| [docs/BENCHMARK.md](docs/BENCHMARK.md) | Benchmark workloads and metrics |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |

## Key Agent Skills

### 1. Nginx Configuration Analysis
```bash
# Check for common misconfigurations
grep -E "open_file_cache|worker_rlimit|sendfile" /etc/nginx/nginx.conf
```

### 2. System Resource Discovery
```bash
# CPU cores, memory, file limits
nproc && free -h && ulimit -n
```

### 3. Network Interface Discovery (Critical!)
```bash
# Find all NICs and speeds - agent must check for faster options
for iface in $(ls /sys/class/net/ | grep -v lo); do
  speed=$(ethtool $iface 2>/dev/null | grep Speed | awk '{print $2}')
  [ -n "$speed" ] && echo "$iface: $speed"
done
```

### 4. Performance Monitoring
```bash
# During benchmark
top -bn1 | head -15  # CPU/memory
iostat -x 1 3        # Disk I/O
```

## Project Structure

```
ai-perf-hackathon/
├── README.md                      # This file
├── requirements.txt               # Python dependencies
├── setup.py                       # Package setup
│
├── agent/                         # AI Agent Code
│   ├── __init__.py
│   ├── __main__.py                # Entry point (python -m agent)
│   ├── main.py                    # CLI and orchestration
│   ├── llm.py                     # Claude API + token tracking
│   ├── ssh_client.py              # SSH command execution
│   ├── collector.py               # Metric/benchmark collection
│   ├── analyzer.py                # LLM-based RCA
│   ├── remediator.py              # Apply tunings
│   └── reporter.py                # Generate reports
│
├── config/
│   ├── settings.yaml              # Agent configuration
│   └── tuning_rules.yaml          # Tuning knowledge base
│
├── reports/
│   └── sample_report.md           # Sample output report
│
└── docs/
    ├── CHANGES_APPLIED.md         # All SUT changes with rollback
    ├── TUNING_PLAYBOOK.md         # Agent knowledge base
    ├── MEDIUM_FILE_ANALYSIS.md    # Medium file deep dive
    ├── FINDINGS_2026-04-08.md     # Session findings
    ├── AGENT_WORKFLOW.md          # Agent operation guide
    ├── ENVIRONMENT.md             # Environment setup
    ├── BENCHMARK.md               # Benchmark details
    └── TROUBLESHOOTING.md         # Common issues
```

## How the Agent Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Performance Agent                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. COLLECT        2. ANALYZE         3. REMEDIATE    4. REPORT │
│  ┌──────────┐     ┌──────────┐      ┌──────────┐    ┌─────────┐│
│  │ SSH to   │     │ Claude   │      │ Apply    │    │Generate ││
│  │ SUT/Bench│────▶│ LLM RCA  │─────▶│ Tunings  │───▶│ Report  ││
│  │ Collect  │     │ Decisions│      │ via SSH  │    │ + Tokens││
│  │ Metrics  │     │ + Reasons│      │          │    │         ││
│  └──────────┘     └──────────┘      └──────────┘    └─────────┘│
│       │                │                  │              │      │
│       ▼                ▼                  ▼              ▼      │
│  [baseline.json]  [decision_log]   [actions_log]  [report.md]  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Collector** gathers nginx config, sysctl params, benchmarks via SSH
2. **Analyzer** sends data to Claude, receives recommendations with reasoning
3. **Remediator** applies changes via SSH, logs each action
4. **Reporter** generates markdown/JSON with before/after, decisions, tokens

## Tunings Applied

### Nginx (`/etc/nginx/nginx.conf`)
- `worker_processes auto` (112 workers)
- `worker_rlimit_nofile 65535`
- `worker_connections 4096`
- `sendfile on` + `tcp_nopush on` + `tcp_nodelay on`
- `open_file_cache max=10000 inactive=60s`
- `aio threads` + `directio 512k`
- `access_log off`

### Systemd (`/etc/systemd/system/nginx.service.d/limits.conf`)
- `LimitNOFILE=65535`

### Kernel TCP (`/etc/sysctl.d/99-nginx-tcp-tuning.conf`)
- `net.ipv4.tcp_congestion_control = bbr`
- `net.core.rmem_max = 67108864`
- `net.core.wmem_max = 67108864`
- `net.core.somaxconn = 65535`

### NVMe I/O
- Scheduler: `none`
- Read-ahead: `8192`

### Network
- Ring buffers: `2047`
- NIC queues: `32`

## Lessons Learned

1. **open_file_cache max must account for worker count** - 500K × 112 workers = too many FDs
2. **Check for faster NICs** - System had 100G available, was using 25G
3. **Medium/large files are network-limited** - No nginx tuning helps at 87% bandwidth utilization
4. **Jumbo frames require switch support** - MTU 9000 broke connectivity
5. **Page cache matters** - 489GB data fits in 502GB RAM = no disk I/O

## Team

- Hackathon Team: PSAP
- Repository: [GitHub](https://github.com/MML-coder/ai-perf-hackathon)
