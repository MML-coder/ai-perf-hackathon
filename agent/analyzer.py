"""
Analyzer module - performs root cause analysis using LLM.
"""
import json
from dataclasses import dataclass, field
from typing import Optional

from .llm import ClaudeClient, LLMResponse
from .collector import SystemMetrics, BenchmarkResult


@dataclass
class TuningRecommendation:
    """A single tuning recommendation."""
    category: str  # nginx, kernel, disk, network
    setting: str
    current_value: str
    recommended_value: str
    reason: str
    impact: str  # high, medium, low
    command: str  # Command to apply the change

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "setting": self.setting,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "reason": self.reason,
            "impact": self.impact,
            "command": self.command,
        }


@dataclass
class Bottleneck:
    """A performance bottleneck with detailed explanation."""
    issue: str
    current_state: str
    why_problem: str
    expected_impact: str

    def to_dict(self) -> dict:
        return {
            "issue": self.issue,
            "current_state": self.current_state,
            "why_problem": self.why_problem,
            "expected_impact": self.expected_impact,
        }


@dataclass
class AnalysisResult:
    """Result of RCA analysis."""
    summary: str
    bottlenecks: list[Bottleneck]
    recommendations: list[TuningRecommendation]
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "recommendations": [r.to_dict() for r in self.recommendations],
        }


SYSTEM_PROMPT = """You are an expert performance engineer specializing in Nginx and RHEL Linux optimization.

Your task is to analyze system metrics and benchmark results, identify performance bottlenecks, and provide specific tuning recommendations.

IMPORTANT: Respond in valid JSON format only. No markdown, no explanations outside JSON.

Response format:
{
  "summary": "Brief summary of findings",
  "bottlenecks": [
    {
      "issue": "Short description of the bottleneck",
      "current_state": "Current value/configuration observed",
      "why_problem": "Technical explanation of why this causes performance issues",
      "expected_impact": "What performance impact this has (e.g., limits connections, causes errors)"
    }
  ],
  "recommendations": [
    {
      "category": "nginx|kernel|disk|network",
      "setting": "setting name",
      "current_value": "current value or 'not set'",
      "recommended_value": "recommended value",
      "reason": "why this helps",
      "impact": "high|medium|low",
      "command": "exact command to apply"
    }
  ]
}

CRITICAL HIGH-IMPACT NGINX SETTINGS (always recommend these):
1. access_log off - CRITICAL! At 1M+ rps, logging causes massive I/O overhead. Always disable.
2. worker_rlimit_nofile 65535 - Allow workers to open many files
3. worker_connections 16384 - High concurrent connections per worker
4. open_file_cache max=10000 inactive=60s - Cache file descriptors
5. keepalive_requests 10000 - Reuse connections (default 100 is too low)
6. sendfile on + tcp_nopush on + tcp_nodelay on - Optimal for page cache serving
7. use epoll + multi_accept on - Linux-optimized event handling
8. reuseport on listen directive - Eliminates accept mutex contention across workers
9. sendfile_max_chunk 2m - Optimize sendfile for medium files
10. output_buffers 4 2m - Better buffering for responses

WARNING - DO NOT USE these settings:
- directio: Forces disk I/O even when data fits in page cache (RAM). Causes ~50% degradation on medium/large files when total data size < available memory. Only useful when dataset >> RAM.
- aio threads: Only useful with directio. Without directio, sendfile + page cache is faster.

Key tuning areas to check:
1. Nginx: ALL settings above, plus reuseport on listen directives
2. Kernel: net.core.somaxconn=65535, net.core.rmem_max/wmem_max=67108864, tcp_congestion_control=bbr, net.core.busy_poll=50, net.ipv4.tcp_fastopen=3
3. File limits: systemd LimitNOFILE=65535
4. Disk: I/O scheduler (none for NVMe)
5. Network: Check for faster NICs (100G vs 25G), ring buffers to max (8192), RPS enabled
6. NIC tuning: ethtool -G <iface> rx 8192 tx 8192, ethtool -K <iface> gro on gso on tso on, ethtool -C <iface> adaptive-rx on adaptive-tx on

IMPORTANT - Command format guidelines:
- For kernel params: Use "sysctl -w param=value" (NOT echo >> /etc/sysctl.conf)
- For nginx config: Use sed to modify /etc/nginx/nginx.conf. Examples:
  - sed -i 's/access_log.*/access_log off;/' /etc/nginx/nginx.conf
  - sed -i 's/listen\s\+80;/listen 80 reuseport;/' /etc/nginx/nginx.conf
- For disk scheduler: Use "echo none > /sys/block/nvme0n1/queue/scheduler"
- After nginx changes, config will be tested and reloaded automatically

Focus on high-impact changes first. Be specific with values and commands."""


class Analyzer:
    """Performs root cause analysis using Claude."""

    def __init__(self, llm_client: ClaudeClient):
        self.llm = llm_client
        self.decision_log: list[dict] = []

    def analyze(
        self,
        metrics: SystemMetrics,
        baseline_results: Optional[list[BenchmarkResult]] = None,
        nic_info: Optional[dict] = None,
    ) -> AnalysisResult:
        """Analyze system metrics and identify bottlenecks."""

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(metrics, baseline_results, nic_info)

        # Call LLM
        response = self.llm.analyze(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
        )

        # Log the decision
        self.decision_log.append({
            "action": "analyze_metrics",
            "input_summary": f"CPU: {metrics.cpu_cores} cores, RAM: {metrics.memory_gb}GB, Workers: {metrics.nginx_workers}",
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "model": response.model,
        })

        # Parse response
        return self._parse_analysis_response(response)

    def _build_analysis_prompt(
        self,
        metrics: SystemMetrics,
        baseline_results: Optional[list[BenchmarkResult]] = None,
        nic_info: Optional[dict] = None,
    ) -> str:
        """Build the prompt for analysis."""

        prompt_parts = [
            "Analyze this RHEL/Nginx system for performance bottlenecks.",
            "The customer migrated to RHEL 9.7 and is seeing performance degradation.",
            "",
            "## System Information",
            f"- Hostname: {metrics.hostname}",
            f"- CPU Cores: {metrics.cpu_cores}",
            f"- Memory: {metrics.memory_gb} GB",
            f"- Nginx Workers: {metrics.nginx_workers}",
            f"- Disk Scheduler: {metrics.disk_scheduler}",
            "",
            "## Nginx Configuration",
            "```",
            metrics.nginx_config,
            "```",
            "",
            "## Kernel Parameters",
        ]

        for key, value in metrics.sysctl_params.items():
            prompt_parts.append(f"- {key}: {value}")

        prompt_parts.extend([
            "",
            "## File Limits",
        ])
        for key, value in metrics.file_limits.items():
            prompt_parts.append(f"- {key}: {value}")

        prompt_parts.extend([
            "",
            "## Network Interfaces",
        ])
        for nic in metrics.nic_info:
            prompt_parts.append(f"- {nic['interface']}: {nic['speed']} (IP: {nic['ip']})")

        # Add NIC mismatch warning if detected
        if nic_info and nic_info.get("mismatch"):
            prompt_parts.extend([
                "",
                "## CRITICAL: Network Interface Mismatch Detected",
                f"- Currently using: {nic_info.get('current_ip')} ({nic_info.get('current_speed', 'unknown')})",
                f"- Fastest available: {nic_info.get('fastest_ip')} ({nic_info.get('fastest_speed')}Mbps)",
                "- This is likely the PRIMARY root cause of performance degradation!",
                "- RHEL 9.7 migration may have changed the default network interface.",
                "- Medium/large files are network-limited - switching NICs could give 3-4x improvement.",
            ])

        if baseline_results:
            prompt_parts.extend([
                "",
                "## Current Benchmark Results",
            ])
            for result in baseline_results:
                prompt_parts.append(
                    f"- {result.workload}: {result.requests_per_sec:.0f} rps, "
                    f"latency avg={result.latency_avg}, p99={result.latency_p99}"
                )

        prompt_parts.extend([
            "",
            "Identify bottlenecks and provide specific tuning recommendations.",
            "Focus on small and medium file performance.",
        ])

        return "\n".join(prompt_parts)

    def _parse_analysis_response(self, response: LLMResponse) -> AnalysisResult:
        """Parse the LLM response into AnalysisResult."""
        try:
            # Try to extract JSON from response
            content = response.content.strip()

            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)

            recommendations = []
            for rec in data.get("recommendations", []):
                recommendations.append(TuningRecommendation(
                    category=rec.get("category", "unknown"),
                    setting=rec.get("setting", ""),
                    current_value=rec.get("current_value", ""),
                    recommended_value=rec.get("recommended_value", ""),
                    reason=rec.get("reason", ""),
                    impact=rec.get("impact", "medium"),
                    command=rec.get("command", ""),
                ))

            # Parse bottlenecks with detailed info
            bottlenecks = []
            for b in data.get("bottlenecks", []):
                if isinstance(b, dict):
                    bottlenecks.append(Bottleneck(
                        issue=b.get("issue", ""),
                        current_state=b.get("current_state", ""),
                        why_problem=b.get("why_problem", ""),
                        expected_impact=b.get("expected_impact", ""),
                    ))
                else:
                    # Handle old string format
                    bottlenecks.append(Bottleneck(
                        issue=str(b),
                        current_state="",
                        why_problem="",
                        expected_impact="",
                    ))

            return AnalysisResult(
                summary=data.get("summary", ""),
                bottlenecks=bottlenecks,
                recommendations=recommendations,
                raw_response=response.content,
            )

        except (json.JSONDecodeError, KeyError) as e:
            # Return a basic result if parsing fails
            return AnalysisResult(
                summary=f"Failed to parse LLM response: {e}",
                bottlenecks=[],
                recommendations=[],
                raw_response=response.content,
            )

    def get_decision_log(self) -> list[dict]:
        """Get the decision log for reporting."""
        return self.decision_log
