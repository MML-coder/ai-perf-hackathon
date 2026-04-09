"""
Collector module - gathers system metrics and configurations.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .ssh_client import SSHClient


@dataclass
class SystemMetrics:
    """Collected system metrics."""
    timestamp: str
    hostname: str
    cpu_cores: int = 0
    memory_gb: float = 0
    nginx_config: str = ""
    nginx_workers: int = 0
    sysctl_params: dict = field(default_factory=dict)
    file_limits: dict = field(default_factory=dict)
    disk_scheduler: str = ""
    nic_info: list = field(default_factory=list)
    raw_commands: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "hostname": self.hostname,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "nginx_workers": self.nginx_workers,
            "sysctl_params": self.sysctl_params,
            "file_limits": self.file_limits,
            "disk_scheduler": self.disk_scheduler,
            "nic_info": self.nic_info,
        }


@dataclass
class BenchmarkResult:
    """Benchmark result for a workload."""
    workload: str
    requests_per_sec: float
    transfer_per_sec: str
    latency_avg: str
    latency_p99: str
    errors: dict = field(default_factory=dict)
    raw_output: str = ""

    def to_dict(self) -> dict:
        return {
            "workload": self.workload,
            "requests_per_sec": self.requests_per_sec,
            "transfer_per_sec": self.transfer_per_sec,
            "latency_avg": self.latency_avg,
            "latency_p99": self.latency_p99,
            "errors": self.errors,
        }


class Collector:
    """Collects system metrics and benchmark results."""

    def __init__(self, sut_host: str, benchmark_host: str):
        self.sut = SSHClient(sut_host)
        self.benchmark = SSHClient(benchmark_host)

    def collect_system_metrics(self) -> SystemMetrics:
        """Collect all system metrics from SUT."""
        metrics = SystemMetrics(
            timestamp=datetime.utcnow().isoformat(),
            hostname=self.sut.host
        )

        # CPU cores
        result = self.sut.run("nproc")
        if result.success:
            metrics.cpu_cores = int(result.stdout.strip())
            metrics.raw_commands["nproc"] = result.stdout

        # Memory
        result = self.sut.run("free -g | grep Mem | awk '{print $2}'")
        if result.success:
            metrics.memory_gb = float(result.stdout.strip())
            metrics.raw_commands["free"] = result.stdout

        # Nginx config
        result = self.sut.run("cat /etc/nginx/nginx.conf")
        if result.success:
            metrics.nginx_config = result.stdout
            metrics.raw_commands["nginx_conf"] = result.stdout

        # Nginx workers
        result = self.sut.run("ps aux | grep 'nginx: worker' | grep -v grep | wc -l")
        if result.success:
            metrics.nginx_workers = int(result.stdout.strip())

        # Key sysctl params
        sysctl_keys = [
            "net.core.somaxconn",
            "net.core.rmem_max",
            "net.core.wmem_max",
            "net.ipv4.tcp_congestion_control",
            "net.ipv4.tcp_max_syn_backlog",
        ]
        for key in sysctl_keys:
            result = self.sut.run(f"sysctl -n {key} 2>/dev/null")
            if result.success:
                metrics.sysctl_params[key] = result.stdout.strip()

        # File limits
        result = self.sut.run("ulimit -n")
        if result.success:
            metrics.file_limits["ulimit_n"] = result.stdout.strip()

        result = self.sut.run("cat /proc/$(pgrep -o nginx)/limits 2>/dev/null | grep 'open files' | awk '{print $4}'")
        if result.success and result.stdout.strip():
            metrics.file_limits["nginx_nofile"] = result.stdout.strip()

        # Disk scheduler
        result = self.sut.run("cat /sys/block/nvme0n1/queue/scheduler 2>/dev/null || cat /sys/block/sda/queue/scheduler 2>/dev/null")
        if result.success:
            metrics.disk_scheduler = result.stdout.strip()

        # NIC info
        result = self.sut.run("""
for iface in $(ls /sys/class/net/ | grep -v lo); do
  speed=$(ethtool $iface 2>/dev/null | grep Speed | awk '{print $2}')
  ip=$(ip addr show $iface 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
  [ -n "$speed" ] && [ "$speed" != "Unknown!" ] && echo "$iface|$speed|${ip:-none}"
done
""")
        if result.success:
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        metrics.nic_info.append({
                            "interface": parts[0],
                            "speed": parts[1],
                            "ip": parts[2] if len(parts) > 2 else "none"
                        })

        return metrics

    def run_all_benchmarks(self, contestant: str = "agent") -> list[BenchmarkResult]:
        """Run all benchmark workloads using benchmark.sh and return results."""
        # Run the full benchmark script (runs all 5 workloads, ~5 min)
        result = self.benchmark.run(f"./benchmark.sh {contestant}", timeout=420)

        # Get results from saved JSON files (benchmark.sh saves them)
        return self.get_latest_results(contestant)

    def get_latest_results(self, contestant: str) -> list[BenchmarkResult]:
        """Get latest benchmark results for a contestant."""
        results = []
        workloads = ["homepage", "small", "medium", "large", "mixed"]

        for workload in workloads:
            result = self.benchmark.run(
                f"cat ~/hackathon-results/{contestant}_{workload}.json 2>/dev/null"
            )
            if result.success:
                try:
                    data = json.loads(result.stdout)
                    res = data.get("results", {})
                    results.append(BenchmarkResult(
                        workload=workload,
                        requests_per_sec=res.get("requests", {}).get("per_sec", 0),
                        transfer_per_sec=res.get("transfer", {}).get("human", ""),
                        latency_avg=res.get("latency", {}).get("avg", ""),
                        latency_p99=res.get("latency", {}).get("percentiles", {}).get("p99", ""),
                        raw_output=result.stdout
                    ))
                except json.JSONDecodeError:
                    pass

        return results

    def _parse_benchmark_output(self, workload: str, output: str) -> BenchmarkResult:
        """Parse wrk benchmark output."""
        result = BenchmarkResult(workload=workload, raw_output=output,
                                  requests_per_sec=0, transfer_per_sec="",
                                  latency_avg="", latency_p99="")

        # Parse requests/sec
        match = re.search(r"Requests/sec:\s+([\d.]+)", output)
        if match:
            result.requests_per_sec = float(match.group(1))

        # Parse transfer/sec
        match = re.search(r"Transfer/sec:\s+(\S+)", output)
        if match:
            result.transfer_per_sec = match.group(1)

        # Parse latency avg
        match = re.search(r"Latency\s+([\d.]+\w+)", output)
        if match:
            result.latency_avg = match.group(1)

        # Parse p99 latency
        match = re.search(r"99%\s+([\d.]+\w+)", output)
        if match:
            result.latency_p99 = match.group(1)

        # Parse errors
        for error_type in ["connect", "read", "write", "timeout"]:
            match = re.search(rf"{error_type}:\s+(\d+)", output, re.IGNORECASE)
            if match:
                result.errors[error_type] = int(match.group(1))

        return result
