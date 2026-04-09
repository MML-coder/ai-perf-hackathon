# AI Performance Agent - RHEL/Nginx Optimization

Autonomous AI agent for diagnosing and resolving performance issues on RHEL systems running Nginx.

## Get Started in 20 Seconds

```bash
# 1. Clone and install
git clone https://github.com/MML-coder/ai-perf-hackathon.git
cd ai-perf-hackathon
pip install -r requirements.txt

# 2. Configure Vertex AI credentials
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id"
gcloud auth application-default login  # If not already authenticated

# 3. Run the agent
python -m agent \
  --sut <nginx-server-host> \
  --benchmark <benchmark-host> \
  --vertex \
  --agentic
```

**That's it!** The agent will autonomously:
1. Collect baseline metrics
2. Analyze with Claude LLM  
3. Apply tunings
4. Verify improvement
5. Generate report with decisions + token costs

---

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

**Agent Run**: `reports/report_20260409_020608.md`

| Workload | Baseline (rps) | After Tuning (rps) | Improvement |
|----------|----------------|--------------------| ------------|
| homepage | 383,656 | 1,553,017 | **+305%** |
| small | 369,756 | 1,917,031 | **+419%** |
| medium | 1,400 | 2,925 | **+109%** |
| large | 186 | 398 | **+114%** |
| mixed | 2,244 | 4,802 | **+114%** |

**All workloads improved >100%!**

**Token Usage**: 4,013 tokens | **Cost**: $0.04 | **Model**: claude-sonnet-4

## Root Causes Identified

| Issue | Impact | Fix |
|-------|--------|-----|
| **Wrong NIC after RHEL 9.7 migration** | 4x bandwidth loss (25G vs 100G) | Agent auto-switches to fastest NIC |
| `open_file_cache off` | Small files slow | Enable with max=10000 |
| `worker_rlimit_nofile 1024` | FD exhaustion | Increase to 65535 |
| `worker_connections 1024` | Connection limits | Increase to 4096 |
| Default TCP buffers | Network inefficiency | 64MB buffers + BBR |

### Primary Root Cause: NIC Selection Changed During Migration

**Hypothesis**: RHEL 9.7 migration changed the default network interface from 100Gbps to 25Gbps.

**Evidence**:
- System has both 25G (`eno*`) and 100G (`ens2f*`) NICs
- After migration, `/etc/hosts` or default route pointed to 25G NIC
- Medium/large file performance was network-limited at 25G (89% utilization)
- Switching to 100G NIC doubled medium/large file throughput

**Why this happens**:
- RHEL 9 uses predictable network interface names (`ens*` vs `eth*`)
- NetworkManager may pick different "best" interface after upgrade
- systemd-networkd has different default gateway selection logic

## Environment

| System | Hostname | Role |
|--------|----------|------|
| DUT (Device Under Test) | e40-h34-000-r650.rdu2.scalelab.redhat.com | Nginx server (112 cores, 502GB RAM) |
| Benchmark Node | e40-h37-000-r650.rdu2.scalelab.redhat.com | Load generator (wrk) |

## Quick Start

### Prerequisites

- Python 3.10+
- SSH access to SUT and benchmark nodes
- Google Cloud Vertex AI access (for Claude API)

### Vertex AI Setup

```bash
# 1. Install gcloud CLI and authenticate
gcloud auth application-default login

# 2. Set your project ID
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id"
```

### Running the AI Agent

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the agent with Vertex AI
python -m agent \
  --sut e40-h34-000-r650.rdu2.scalelab.redhat.com \
  --benchmark e40-h37-000-r650.rdu2.scalelab.redhat.com \
  --vertex \
  --agentic

# 3. View the generated report
cat reports/report_*.md
```

### Agent CLI Options

```bash
# Dry run (analyze but don't apply changes)
python -m agent --sut HOST --benchmark HOST --vertex --dry-run

# Use a specific model (sonnet, opus, haiku)
python -m agent --sut HOST --benchmark HOST --vertex --model opus

# Analyze only, no benchmark
python -m agent --sut HOST --benchmark HOST --dry-run

# Use existing benchmark results
python -m agent --sut HOST --benchmark HOST --baseline baseline

# Skip benchmarks (faster for testing)
python -m agent --sut HOST --benchmark HOST --skip-benchmark
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

- Hackathon Team: rhelper (psap)
- Repository: [GitHub](https://github.com/MML-coder/ai-perf-hackathon)
