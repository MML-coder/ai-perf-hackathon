"""
Tools the agent can use to explore and fix the system.
"""
from dataclasses import dataclass
from typing import Optional
import json

from .ssh_client import SSHClient


@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool: str
    success: bool
    output: str
    error: Optional[str] = None


class AgentTools:
    """Tools available to the autonomous agent."""

    def __init__(self, sut: SSHClient, benchmark: SSHClient, contestant: str = "agent-test"):
        self.sut = sut
        self.benchmark = benchmark
        self.contestant = contestant
        self.command_history: list[dict] = []

    def run_command(self, command: str, target: str = "sut") -> ToolResult:
        """Run a shell command on SUT or benchmark node."""
        client = self.sut if target == "sut" else self.benchmark
        result = client.run(command, timeout=60)

        self.command_history.append({
            "tool": "run_command",
            "target": target,
            "command": command,
            "success": result.success,
            "output": result.output[:2000],
        })

        return ToolResult(
            tool="run_command",
            success=result.success,
            output=result.output,
            error=result.stderr if not result.success else None,
        )

    def read_file(self, path: str, target: str = "sut") -> ToolResult:
        """Read a file from SUT or benchmark node."""
        client = self.sut if target == "sut" else self.benchmark
        result = client.read_file(path)

        self.command_history.append({
            "tool": "read_file",
            "target": target,
            "path": path,
            "success": result.success,
        })

        return ToolResult(
            tool="read_file",
            success=result.success,
            output=result.output,
            error=result.stderr if not result.success else None,
        )

    def write_file(self, path: str, content: str, target: str = "sut") -> ToolResult:
        """Write content to a file on SUT."""
        if target != "sut":
            return ToolResult(tool="write_file", success=False, output="", error="Can only write to SUT")

        result = self.sut.write_file(path, content)

        self.command_history.append({
            "tool": "write_file",
            "path": path,
            "success": result.success,
        })

        return ToolResult(
            tool="write_file",
            success=result.success,
            output=result.output,
            error=result.stderr if not result.success else None,
        )

    def run_benchmark(self, workload: str = "small") -> ToolResult:
        """Run a benchmark and get results.

        Note: benchmark.sh always runs ALL workloads regardless of arguments.
        The workload parameter is used to read the correct result file after.
        """
        # benchmark.sh runs all 5 workloads (~5 min total)
        result = self.benchmark.run(f"./benchmark.sh {self.contestant}", timeout=600)

        self.command_history.append({
            "tool": "run_benchmark",
            "workload": workload,
            "success": result.success,
        })

        return ToolResult(
            tool="run_benchmark",
            success=result.success,
            output=result.output,
            error=result.stderr if not result.success else None,
        )

    def get_tool_definitions(self) -> list[dict]:
        """Get Claude tool definitions for tool use."""
        return [
            {
                "name": "run_command",
                "description": "Run a shell command on the target system to diagnose or fix issues. Use this to explore the system, check configurations, apply tunings, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "target": {
                            "type": "string",
                            "enum": ["sut", "benchmark"],
                            "description": "Target system: 'sut' for nginx server, 'benchmark' for load generator"
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "read_file",
                "description": "Read contents of a file on the target system",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file"
                        },
                        "target": {
                            "type": "string",
                            "enum": ["sut", "benchmark"],
                            "description": "Target system"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file on the SUT. Use for applying configuration changes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file"
                        }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "run_benchmark",
                "description": "Run a performance benchmark to measure current performance. Use after applying tunings to verify improvement.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workload": {
                            "type": "string",
                            "enum": ["homepage", "small", "medium", "large", "mixed"],
                            "description": "Benchmark workload type"
                        }
                    },
                    "required": ["workload"]
                }
            },
            {
                "name": "done",
                "description": "Signal that tuning is complete. Call this when you've achieved the performance target or exhausted options.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Summary of what was done and results achieved"
                        },
                        "success": {
                            "type": "boolean",
                            "description": "Whether performance target was achieved"
                        }
                    },
                    "required": ["summary", "success"]
                }
            }
        ]
