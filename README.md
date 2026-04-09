# rhelper agent for RHEL/Nginx 

Autonomous AI agent for diagnosing and resolving performance issues on RHEL systems running Nginx.

## Get Started

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

**Agent Run**: `reports/report_20260409_134000_d20.md`

| Workload | Baseline (rps) | After Tuning (rps) | Improvement |
|----------|----------------|--------------------| ------------|
| homepage | 456,357 | 1,306,345 | **+186%** |
| small | 426,670 | 2,086,883 | **+389%** |
| medium | 1,400 | 5,595 | **+300%** |
| large | 186 | 745 | **+300%** |
| mixed | 2,229 | 8,947 | **+301%** |

**All workloads improved >186%!**

**Token Usage**: 4,013 tokens | **Cost**: $0.04 | **Model**: claude-sonnet-4

## Root Causes Identified

| Issue | Impact | Fix |
|-------|--------|-----|
| **Wrong NIC after RHEL 9.7 migration** | 4x bandwidth loss (25G vs 100G) | Agent auto-switches to fastest NIC |
| `open_file_cache off` | Small files slow | Enable with max=10000 |
| `worker_rlimit_nofile 1024` | FD exhaustion | Increase to 65535 |
| `worker_connections 1024` | Connection limits | Increase to 16384 |
| Default TCP buffers | Network inefficiency | 64MB buffers + BBR |
| `directio 512k` used previously | **~50% degradation** on medium/large files | **Removed** - bypasses page cache when all data fits in RAM |
| No `reuseport` on listen | Accept mutex contention across 112 workers | Add `reuseport` to listen directive |
| Low NIC ring buffers (2047) | Packet drops under load | Increase to 8192 (max) |

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
| DUT (Device Under Test) | `<SUT_HOST>` | Nginx server |
| Benchmark Node | `<BENCHMARK_HOST>` | Load generator (wrk) |

## Quick Start

### Prerequisites

#### Local Machine
- Python 3.10+
- `anthropic` package: `pip install anthropic`
- Google Cloud Vertex AI access (or Anthropic API key)

#### SSH Access Setup
```bash
# 1. Copy your SSH key to both hosts
ssh-copy-id root@<SUT_HOST>
ssh-copy-id root@<BENCHMARK_HOST>

# 2. Accept host keys
ssh-keyscan <SUT_HOST> >> ~/.ssh/known_hosts
ssh-keyscan <BENCHMARK_HOST> >> ~/.ssh/known_hosts

# 3. Verify passwordless access works
ssh root@<SUT_HOST> 'hostname'
ssh root@<BENCHMARK_HOST> 'hostname'
```

#### SUT (Nginx Server) Requirements
- RHEL 9.x with Nginx installed and running
- Root SSH access (agent modifies nginx.conf, runs sysctl)
- Static files being served by Nginx

#### Benchmark Node Requirements
- `wrk` installed: `dnf install -y wrk`
- `~/benchmark.sh` script (runs wrk workloads)
- `~/hackathon-tools/*.lua` workload scripts
- `/etc/hosts` entry: `<SUT-IP> test-machine`

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
  --sut <SUT_HOST> \
  --benchmark <BENCHMARK_HOST> \
  --vertex \
  --agentic

# 3. View the generated report
cat reports/report_*.md
```

### Agent CLI Options

```bash
# Agentic mode - fully autonomous (recommended)
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --agentic

# Agentic mode with specific model
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --model sonnet --agentic

# Agentic mode with custom max iterations (default: 500)
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --agentic --max-iterations 100

# Pipeline mode (non-agentic) - single LLM call
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex

# Dry run (analyze but don't apply changes)
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --dry-run

# Use a specific model (sonnet, opus, haiku)
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --model opus

# Skip benchmarks (faster for testing)
python -m agent --sut <SUT_HOST> --benchmark <BENCHMARK_HOST> --vertex --skip-benchmark
```

**Agentic vs Pipeline Mode:**
- **Agentic** (`--agentic`): Agent autonomously explores, diagnoses, applies tunings, and verifies. Multiple LLM calls. Best for complex issues.
- **Pipeline**: Single LLM call for analysis, then applies recommendations. Faster and cheaper (~$0.04 vs ~$2-5).


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
- `worker_connections 16384`
- `sendfile on` + `tcp_nopush on` + `tcp_nodelay on`
- `open_file_cache max=10000 inactive=60s`
- `multi_accept on` + `use epoll`
- `access_log off`
- `listen 80 reuseport` (eliminates accept mutex contention)
- **NO** `directio` or `aio threads` (bypasses page cache, causes ~50% degradation when data fits in RAM)

### Systemd (`/etc/systemd/system/nginx.service.d/limits.conf`)
- `LimitNOFILE=65535`

### Kernel TCP (`/etc/sysctl.d/99-nginx-tcp-tuning.conf`)
- `net.ipv4.tcp_congestion_control = bbr`
- `net.core.rmem_max = 67108864`
- `net.core.wmem_max = 67108864`
- `net.core.somaxconn = 65535`
- `net.core.busy_poll = 50`
- `net.ipv4.tcp_fastopen = 3`
- `net.core.netdev_max_backlog = 65535`
- `vm.swappiness = 1`

### NVMe I/O
- Scheduler: `none`
- Read-ahead: `8192`

### Network
- Ring buffers: `8192` (max available)
- NIC queues: `32`
- GRO/GSO/TSO offloads enabled
- Adaptive coalescing enabled
- RPS (Receive Packet Steering) enabled

## Lessons Learned

1. **NEVER use `directio` when data fits in RAM** - Forces disk I/O, bypasses page cache, causes ~50% degradation on medium/large files. `sendfile` + page cache is vastly superior when dataset < available memory.
2. **open_file_cache max must account for worker count** - 500K × 112 workers = too many FDs
3. **Check for faster NICs** - System had 100G available, was using 25G
4. **Medium/large files are network-limited** - No nginx tuning helps at 87% bandwidth utilization
5. **`reuseport` eliminates accept mutex** - With 112 workers, accept contention is real. `reuseport` gives each worker its own socket.
6. **Ring buffers default too low** - Default 2047 causes packet drops under load; max (8192) eliminates this.
7. **Jumbo frames require switch support** - MTU 9000 broke connectivity
8. **Page cache matters** - 489GB data fits in 502GB RAM = no disk I/O

## Team

- Hackathon Team: rhelper (psap)
- Repository: [GitHub](https://github.com/MML-coder/ai-perf-hackathon)
