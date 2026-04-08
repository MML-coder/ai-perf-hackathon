"""
Reporter module - generates performance reports.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .collector import SystemMetrics, BenchmarkResult
from .analyzer import AnalysisResult, TuningRecommendation
from .remediator import RemediationAction
from .llm import ClaudeClient


@dataclass
class PerformanceReport:
    """Complete performance analysis report."""
    timestamp: str
    baseline_metrics: SystemMetrics
    baseline_results: list[BenchmarkResult]
    analysis: AnalysisResult
    actions_taken: list[RemediationAction]
    after_results: list[BenchmarkResult]
    token_usage: list[dict]
    decision_log: list[dict]

    def calculate_improvements(self) -> list[dict]:
        """Calculate improvement percentages."""
        improvements = []

        baseline_map = {r.workload: r for r in self.baseline_results}
        after_map = {r.workload: r for r in self.after_results}

        for workload in ["homepage", "small", "medium", "large", "mixed"]:
            if workload in baseline_map and workload in after_map:
                before = baseline_map[workload].requests_per_sec
                after = after_map[workload].requests_per_sec

                if before > 0:
                    pct = ((after - before) / before) * 100
                else:
                    pct = 0

                improvements.append({
                    "workload": workload,
                    "before_rps": before,
                    "after_rps": after,
                    "improvement_pct": round(pct, 1),
                })

        return improvements


class Reporter:
    """Generates performance reports."""

    def __init__(self, llm_client: Optional[ClaudeClient] = None):
        self.llm = llm_client

    def generate_markdown_report(self, report: PerformanceReport) -> str:
        """Generate a markdown report."""
        lines = [
            "# AI Performance Agent Report",
            "",
            f"**Generated**: {report.timestamp}",
            f"**Target System**: {report.baseline_metrics.hostname}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            report.analysis.summary,
            "",
            "---",
            "",
            "## Performance Results",
            "",
            "### Before vs After Comparison",
            "",
            "| Workload | Before (rps) | After (rps) | Improvement |",
            "|----------|--------------|-------------|-------------|",
        ]

        improvements = report.calculate_improvements()
        for imp in improvements:
            sign = "+" if imp["improvement_pct"] >= 0 else ""
            lines.append(
                f"| {imp['workload']} | {imp['before_rps']:,.0f} | "
                f"{imp['after_rps']:,.0f} | **{sign}{imp['improvement_pct']}%** |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Bottlenecks Identified",
            "",
        ])

        for i, bottleneck in enumerate(report.analysis.bottlenecks, 1):
            lines.append(f"{i}. {bottleneck}")

        lines.extend([
            "",
            "---",
            "",
            "## Tuning Recommendations Applied",
            "",
            "| Setting | Previous | New Value | Reason | Impact |",
            "|---------|----------|-----------|--------|--------|",
        ])

        for rec in report.analysis.recommendations:
            lines.append(
                f"| {rec.setting} | {rec.current_value} | {rec.recommended_value} | "
                f"{rec.reason[:50]}... | {rec.impact} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Decision Log",
            "",
            "The following decisions were made by the AI agent:",
            "",
            "| Decision | Data/Reason | Action Taken |",
            "|----------|-------------|--------------|",
        ])

        for action in report.actions_taken:
            rec = action.recommendation
            status = "Applied" if action.success else "Failed"
            lines.append(
                f"| {rec.setting} | {rec.reason[:40]}... | {status}: `{rec.command[:40]}...` |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Model Usage",
            "",
            "| Model | Input Tokens | Output Tokens | Total | API Calls |",
            "|-------|--------------|---------------|-------|-----------|",
        ])

        total_input = 0
        total_output = 0
        total_calls = 0

        for usage in report.token_usage:
            total = usage["input_tokens"] + usage["output_tokens"]
            lines.append(
                f"| {usage['model']} | {usage['input_tokens']:,} | "
                f"{usage['output_tokens']:,} | {total:,} | {usage['api_calls']} |"
            )
            total_input += usage["input_tokens"]
            total_output += usage["output_tokens"]
            total_calls += usage["api_calls"]

        lines.append(
            f"| **Total** | **{total_input:,}** | **{total_output:,}** | "
            f"**{total_input + total_output:,}** | **{total_calls}** |"
        )

        lines.extend([
            "",
            "---",
            "",
            "## System Configuration (Before)",
            "",
            f"- **CPU Cores**: {report.baseline_metrics.cpu_cores}",
            f"- **Memory**: {report.baseline_metrics.memory_gb} GB",
            f"- **Nginx Workers**: {report.baseline_metrics.nginx_workers}",
            f"- **Disk Scheduler**: {report.baseline_metrics.disk_scheduler}",
            "",
            "### Network Interfaces",
            "",
        ])

        for nic in report.baseline_metrics.nic_info:
            lines.append(f"- {nic['interface']}: {nic['speed']} (IP: {nic['ip']})")

        lines.extend([
            "",
            "### Key Kernel Parameters",
            "",
        ])

        for key, value in report.baseline_metrics.sysctl_params.items():
            lines.append(f"- `{key}`: {value}")

        lines.extend([
            "",
            "---",
            "",
            "## Rollback Instructions",
            "",
            "To rollback all changes:",
            "",
            "```bash",
        ])

        for action in report.actions_taken:
            if action.success and action.rollback_command:
                lines.append(f"# Rollback {action.recommendation.setting}")
                lines.append(action.rollback_command)

        lines.extend([
            "```",
            "",
            "---",
            "",
            "*Report generated by AI Performance Agent v1.0*",
        ])

        return "\n".join(lines)

    def generate_json_report(self, report: PerformanceReport) -> str:
        """Generate a JSON report."""
        data = {
            "timestamp": report.timestamp,
            "hostname": report.baseline_metrics.hostname,
            "summary": report.analysis.summary,
            "improvements": report.calculate_improvements(),
            "bottlenecks": report.analysis.bottlenecks,
            "recommendations": [r.to_dict() for r in report.analysis.recommendations],
            "actions": [a.to_dict() for a in report.actions_taken],
            "token_usage": report.token_usage,
            "decision_log": report.decision_log,
            "baseline_metrics": report.baseline_metrics.to_dict(),
            "baseline_results": [r.to_dict() for r in report.baseline_results],
            "after_results": [r.to_dict() for r in report.after_results],
        }
        return json.dumps(data, indent=2)
