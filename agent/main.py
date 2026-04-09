#!/usr/bin/env python3
"""
AI Performance Agent - Main CLI

Autonomous agent for diagnosing and resolving Nginx performance issues on RHEL.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .llm import ClaudeClient
from .ssh_client import SSHClient
from .collector import Collector
from .analyzer import Analyzer
from .remediator import Remediator
from .reporter import Reporter, PerformanceReport
from .agentic import AgenticRunner


# Available models
MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
    # Legacy names
    "claude-3-sonnet": "claude-sonnet-4-20250514",
    "claude-3-opus": "claude-opus-4-20250514",
}


def get_model_id(model_name: str) -> str:
    """Convert model name to full model ID."""
    if model_name in MODELS:
        return MODELS[model_name]
    # Assume it's already a full model ID
    return model_name


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="AI Performance Agent for RHEL/Nginx optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with Vertex AI (uses ANTHROPIC_VERTEX_PROJECT_ID env var)
  python -m agent --sut host1 --benchmark host2 --vertex

  # Run with Vertex AI and explicit project
  python -m agent --sut host1 --benchmark host2 --vertex --vertex-project-id my-project

  # Run with direct Anthropic API
  python -m agent --sut host1 --benchmark host2 --api-key sk-ant-...

  # Use a specific model
  python -m agent --sut host1 --benchmark host2 --vertex --model opus

  # Dry run (no changes applied)
  python -m agent --sut host1 --benchmark host2 --vertex --dry-run

  # Only collect metrics, no LLM needed
  python -m agent --sut host1 --benchmark host2 --collect-only

Available models: sonnet, opus, haiku (or full model IDs)
        """
    )

    parser.add_argument(
        "--sut", "-s",
        required=True,
        help="SUT (System Under Test) hostname or IP"
    )
    parser.add_argument(
        "--benchmark", "-b",
        required=True,
        help="Benchmark node hostname or IP"
    )
    parser.add_argument(
        "--model", "-m",
        default="sonnet",
        help="LLM model to use (sonnet, opus, haiku, or full model ID)"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ANTHROPIC_API_KEY"),
        help="Anthropic API key (default: ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--vertex",
        action="store_true",
        help="Use Google Cloud Vertex AI instead of direct Anthropic API"
    )
    parser.add_argument(
        "--vertex-project-id",
        default=os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"),
        help="Vertex AI project ID (default: ANTHROPIC_VERTEX_PROJECT_ID env var)"
    )
    parser.add_argument(
        "--vertex-region",
        default="us-east5",
        help="Vertex AI region (default: us-east5)"
    )
    parser.add_argument(
        "--agentic",
        action="store_true",
        help="Run in fully autonomous mode - agent explores, decides, and applies changes"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=20,
        help="Max iterations for agentic mode (default: 20)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Don't apply changes, just analyze and show recommendations"
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect metrics, skip analysis and remediation"
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip running benchmarks (use existing results)"
    )
    parser.add_argument(
        "--contestant",
        default="agent",
        help="Contestant name for benchmark results"
    )
    parser.add_argument(
        "--baseline",
        help="Baseline contestant name to compare against"
    )
    parser.add_argument(
        "--output", "-o",
        default="reports",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "both"],
        default="both",
        help="Output format for reports"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    return parser


def print_header(msg: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def print_step(msg: str):
    """Print a step message."""
    print(f">> {msg}")


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Validate API key or Vertex
    if not args.collect_only:
        if args.vertex:
            if not args.vertex_project_id:
                print("Error: Vertex project ID required. Use --vertex-project-id or set ANTHROPIC_VERTEX_PROJECT_ID.")
                sys.exit(1)
        elif not args.api_key:
            print("Error: ANTHROPIC_API_KEY not set. Use --api-key, set environment variable, or use --vertex for Vertex AI.")
            print("       Or use --collect-only to skip LLM analysis.")
            sys.exit(1)

    # Initialize components
    print_header("AI Performance Agent v1.0")
    print(f"Target SUT: {args.sut}")
    print(f"Benchmark Node: {args.benchmark}")
    print(f"Model: {get_model_id(args.model)}")
    print(f"Backend: {'Vertex AI' if args.vertex else 'Anthropic API'}")
    print(f"Dry Run: {args.dry_run}")

    # Test SSH connectivity
    print_step("Testing SSH connectivity...")
    sut_client = SSHClient(args.sut)
    benchmark_client = SSHClient(args.benchmark)

    if not sut_client.test_connection():
        print(f"Error: Cannot connect to SUT ({args.sut})")
        sys.exit(1)
    print(f"  SUT ({args.sut}): OK")

    if not benchmark_client.test_connection():
        print(f"Error: Cannot connect to benchmark node ({args.benchmark})")
        sys.exit(1)
    print(f"  Benchmark ({args.benchmark}): OK")

    # Agentic mode - fully autonomous
    if args.agentic:
        print_header("Running in AGENTIC MODE")
        print("The agent will autonomously explore, diagnose, and fix issues.")

        if args.vertex:
            llm = ClaudeClient(
                model=get_model_id(args.model),
                use_vertex=True,
                vertex_project_id=args.vertex_project_id,
                vertex_region=args.vertex_region,
            )
        else:
            llm = ClaudeClient(api_key=args.api_key, model=get_model_id(args.model))

        runner = AgenticRunner(
            sut_host=args.sut,
            benchmark_host=args.benchmark,
            llm_client=llm,
            max_iterations=args.max_iterations,
        )

        state = runner.run()

        print_header("Agent Complete")
        print(f"Success: {state.success}")
        print(f"Iterations: {state.iteration}")
        print(f"Summary: {state.summary}")

        print("\nBaseline RPS:", state.baseline_rps)
        print("Final RPS:", state.current_rps)

        print("\nToken Usage:")
        print(llm.get_usage_report())

        print("\nDecision Log:")
        for entry in runner.get_decision_log():
            print(f"  [{entry['iteration']}] {entry['tool']}: {entry.get('inputs', {})}")

        # Save report
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        report_data = {
            "mode": "agentic",
            "success": state.success,
            "summary": state.summary,
            "iterations": state.iteration,
            "baseline_rps": state.baseline_rps,
            "final_rps": state.current_rps,
            "actions": state.actions_taken,
            "decision_log": runner.get_decision_log(),
            "token_usage": llm.get_total_usage(),
        }

        report_path = output_dir / f"agentic_report_{timestamp}.json"
        report_path.write_text(json.dumps(report_data, indent=2))
        print(f"\nReport saved: {report_path}")

        return

    # Initialize collector
    collector = Collector(args.sut, args.benchmark)

    # Step 1: Collect baseline metrics
    print_header("Step 1: Collecting System Metrics")
    print_step("Gathering system configuration from SUT...")
    metrics = collector.collect_system_metrics()

    print(f"  CPU Cores: {metrics.cpu_cores}")
    print(f"  Memory: {metrics.memory_gb} GB")
    print(f"  Nginx Workers: {metrics.nginx_workers}")
    print(f"  NICs: {len(metrics.nic_info)}")

    if args.verbose:
        print("\nNginx Config Preview:")
        for line in metrics.nginx_config.split("\n")[:20]:
            print(f"  {line}")

    # Discover NIC info (for analysis, but don't switch yet)
    fastest_nic = None
    current_nic_ip = None
    nic_mismatch = False
    if not args.skip_benchmark:
        print_step("Discovering NICs on SUT...")
        fastest_nic = collector.discover_fastest_nic()
        current_nic_ip = collector.get_current_test_machine_ip()
        if fastest_nic and current_nic_ip:
            print(f"  Current NIC: {current_nic_ip}")
            print(f"  Fastest NIC available: {fastest_nic['interface']} @ {fastest_nic['speed_mbps']}Mbps (IP: {fastest_nic['ip']})")
            if current_nic_ip != fastest_nic["ip"]:
                nic_mismatch = True
                print(f"  *** Using slower NIC - will recommend switch after analysis ***")

    # Step 2: Collect baseline benchmark results (on current NIC, before tuning)
    print_header("Step 2: Collecting Baseline Benchmark Results")

    baseline_results = []
    if args.baseline:
        print_step(f"Using existing results from '{args.baseline}'...")
        baseline_results = collector.get_latest_results(args.baseline)
    elif not args.skip_benchmark:
        print_step("Running baseline benchmarks (this takes ~5 minutes)...")
        baseline_results = collector.run_all_benchmarks(f"{args.contestant}-baseline")
    else:
        print_step("Skipping benchmarks (--skip-benchmark)")

    if baseline_results:
        print("\nBaseline Results:")
        for result in baseline_results:
            print(f"  {result.workload}: {result.requests_per_sec:,.0f} rps")

    if args.collect_only:
        print_header("Collection Complete (--collect-only)")
        print(json.dumps(metrics.to_dict(), indent=2))
        return

    # Step 3: Analyze with LLM
    print_header("Step 3: Analyzing with AI")

    if args.vertex:
        llm = ClaudeClient(
            model=get_model_id(args.model),
            use_vertex=True,
            vertex_project_id=args.vertex_project_id,
            vertex_region=args.vertex_region,
        )
        print_step(f"Using Vertex AI (project: {args.vertex_project_id}, region: {args.vertex_region})")
    else:
        llm = ClaudeClient(api_key=args.api_key, model=get_model_id(args.model))

    analyzer = Analyzer(llm)

    # Build NIC info for analysis
    nic_analysis_info = None
    if nic_mismatch and fastest_nic:
        current_speed = None
        for nic in metrics.nic_info:
            if nic.get("ip") == current_nic_ip:
                current_speed = nic.get("speed", "unknown")
                break
        nic_analysis_info = {
            "mismatch": True,
            "current_ip": current_nic_ip,
            "current_speed": current_speed,
            "fastest_ip": fastest_nic["ip"],
            "fastest_speed": fastest_nic["speed_mbps"],
        }

    print_step(f"Sending metrics to {get_model_id(args.model)} for analysis...")
    analysis = analyzer.analyze(metrics, baseline_results, nic_analysis_info)

    print(f"\nSummary: {analysis.summary}")
    print(f"\nBottlenecks Identified ({len(analysis.bottlenecks)}):")
    for i, b in enumerate(analysis.bottlenecks, 1):
        print(f"\n  {i}. {b.issue}")
        if b.current_state:
            print(f"     Current: {b.current_state}")
        if b.why_problem:
            print(f"     Why: {b.why_problem}")
        if b.expected_impact:
            print(f"     Impact: {b.expected_impact}")

    print(f"\nRecommendations ({len(analysis.recommendations)}):")
    for rec in analysis.recommendations:
        print(f"  [{rec.impact.upper()}] {rec.setting}: {rec.current_value} -> {rec.recommended_value}")
        print(f"         Reason: {rec.reason}")

    # Step 4: Apply remediations
    print_header("Step 4: Applying Tunings")

    # First, switch to fastest NIC if mismatch detected
    nic_switched = None
    if nic_mismatch and fastest_nic and not args.dry_run:
        print_step("Switching to fastest NIC (100Gbps)...")
        print(f"  *** ROOT CAUSE FIX: Network interface changed during RHEL 9.7 migration ***")
        nic_switched = collector.switch_to_fastest_nic()
        if nic_switched and nic_switched.get("switched"):
            print(f"  Switched: {nic_switched['previous_ip']} -> {fastest_nic['ip']}")
            print(f"  This alone should improve medium/large file performance by ~300%")
    elif nic_mismatch and args.dry_run:
        print_step("[DRY RUN] Would switch to fastest NIC")
        print(f"  {current_nic_ip} -> {fastest_nic['ip']}")

    remediator = Remediator(sut_client, dry_run=args.dry_run)

    if not args.dry_run:
        print_step("Creating backup of nginx config...")
        remediator.backup_nginx_config()

    print_step("Applying recommendations...")
    actions = remediator.apply_recommendations(analysis.recommendations)

    for action in actions:
        status = "OK" if action.success else "FAILED"
        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"  {prefix}{action.recommendation.setting}: {status}")

    # Step 5: Run post-tuning benchmarks
    print_header("Step 5: Running Post-Tuning Benchmarks")

    after_results = []
    if not args.skip_benchmark and not args.dry_run:
        print_step("Running benchmarks after tuning...")
        after_results = collector.run_all_benchmarks(f"{args.contestant}-after")

        print("\nAfter-Tuning Results:")
        for result in after_results:
            print(f"  {result.workload}: {result.requests_per_sec:,.0f} rps")
    elif args.dry_run:
        print_step("Skipping (dry run mode)")
        after_results = baseline_results  # Use baseline for report structure
    else:
        print_step("Skipping (--skip-benchmark)")

    # Step 6: Generate report
    print_header("Step 6: Generating Report")

    report = PerformanceReport(
        timestamp=datetime.utcnow().isoformat(),
        baseline_metrics=metrics,
        baseline_results=baseline_results,
        analysis=analysis,
        actions_taken=actions,
        after_results=after_results,
        token_usage=llm.get_total_usage(),
        decision_log=analyzer.get_decision_log(),
    )

    reporter = Reporter(llm)

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if args.format in ["markdown", "both"]:
        md_report = reporter.generate_markdown_report(report)
        md_path = output_dir / f"report_{timestamp}.md"
        md_path.write_text(md_report)
        print(f"  Markdown report: {md_path}")

    if args.format in ["json", "both"]:
        json_report = reporter.generate_json_report(report)
        json_path = output_dir / f"report_{timestamp}.json"
        json_path.write_text(json_report)
        print(f"  JSON report: {json_path}")

    # Print summary
    print_header("Summary")

    if baseline_results and after_results and not args.dry_run:
        print("=== Performance Comparison ===\n")
        print(f"{'Workload':<12} | {'Baseline (rps)':>15} | {'After (rps)':>15} | {'Change':>12} | {'Status':<10}")
        print("-" * 75)

        improvements = report.calculate_improvements()
        for imp in improvements:
            pct = imp["improvement_pct"]
            if pct > 10:
                status = "IMPROVED"
            elif pct < -10:
                status = "DEGRADED"
            else:
                status = "STABLE"

            sign = "+" if pct >= 0 else ""
            print(f"{imp['workload']:<12} | {imp['before_rps']:>15,.0f} | {imp['after_rps']:>15,.0f} | {sign}{pct:>10.1f}% | {status:<10}")

        print("\nLegend:")
        print("  IMPROVED  - More than 10% improvement")
        print("  STABLE    - Within +/-10%")
        print("  DEGRADED  - More than 10% degradation")

    print("\nToken Usage:")
    print(llm.get_usage_report())

    print("\nAgent run complete.")


if __name__ == "__main__":
    main()
