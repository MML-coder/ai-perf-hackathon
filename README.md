# AI Performance Agent - RHEL/Nginx Optimization

Autonomous AI agent for diagnosing and resolving performance issues on RHEL systems running Nginx.

## Problem Statement

Customer reports performance degradation in Nginx web server for small and medium-sized files after migrating to RHEL 9.7. The agent must:

1. **Collect** - Gather real-time performance telemetry
2. **Analyze** - Perform root cause analysis (RCA)
3. **Remediate** - Automatically apply tunings
4. **Report** - Generate human-readable recommendations

## Environment

| System | Hostname | Role |
|--------|----------|------|
| DUT (Device Under Test) | e40-h34-000-r650.rdu2.scalelab.redhat.com | Nginx server |
| Benchmark Node | e40-h37-000-r650.rdu2.scalelab.redhat.com | Load generator |

## Quick Start

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

## Results Achieved

| Workload | Before (rps) | After (rps) | Change |
|----------|--------------|-------------|--------|
| homepage | 384,035 | 1,228,085 | **+220%** |
| small | 383,354 | 1,281,775 | **+234%** |
| medium | 1,401 | 1,400 | Network-limited |
| large | 186 | 186 | Network-limited |
| mixed | 2,265 | 2,247 | Network-limited |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Environment setup, SSH access, system details |
| [docs/BENCHMARK.md](docs/BENCHMARK.md) | Benchmark workloads, metrics, how to run |
| [docs/TUNING_PLAYBOOK.md](docs/TUNING_PLAYBOOK.md) | Nginx & RHEL tuning strategies (agent knowledge base) |
| [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md) | How the autonomous agent operates |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [docs/FINDINGS_2026-04-08.md](docs/FINDINGS_2026-04-08.md) | Detailed tuning session findings |

## Project Structure

```
ai-perf-hackathon/
├── README.md                 # This file
├── docs/                     # Documentation
│   ├── ENVIRONMENT.md        # Environment setup
│   ├── BENCHMARK.md          # Benchmark details
│   ├── TUNING_PLAYBOOK.md    # Tuning knowledge base
│   ├── AGENT_WORKFLOW.md     # Agent operation guide
│   ├── FINDINGS_2026-04-08.md # Session findings
│   └── TROUBLESHOOTING.md    # Common issues
├── agent/                    # Agent code
├── tools/                    # Helper scripts
├── config/                   # Configuration files
└── reports/                  # Generated reports
    └── sample_report.md      # Sample output report
```

## Key Findings

1. **open_file_cache** is critical for small files (2.5M files)
2. **worker_rlimit_nofile** must match systemd LimitNOFILE
3. **Medium files** are network-limited (87% of 25Gbps)
4. Cache max must account for worker count (10K × 112 workers = 1.12M)

## Team

- Hackathon Team: PSAP
- Repository: [GitHub](https://github.com/MML-coder/ai-perf-hackathon)
