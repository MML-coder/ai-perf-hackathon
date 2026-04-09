"""
Agentic loop - autonomous exploration and tuning.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .tools import AgentTools, ToolResult
from .ssh_client import SSHClient


@dataclass
class AgentState:
    """Current state of the agent."""
    iteration: int = 0
    baseline_rps: dict = field(default_factory=dict)
    current_rps: dict = field(default_factory=dict)
    actions_taken: list = field(default_factory=list)
    done: bool = False
    success: bool = False
    summary: str = ""


SYSTEM_PROMPT = """You are an autonomous performance tuning agent for RHEL/Nginx systems.

GOAL: Improve Nginx performance for small and medium file workloads. Target: >100% improvement on each.
NOTE: Medium files are NETWORK-LIMITED. You MUST switch to 100G NIC to see improvement!

TOOLS AVAILABLE:
- run_command: Execute shell commands on SUT or benchmark node
- read_file: Read configuration files
- write_file: Write/modify configuration files
- run_benchmark: Measure performance (workloads: homepage, small, medium, large, mixed) - ALWAYS use this, never ab/curl!
- done: Signal completion with summary

SYSTEMATIC APPROACH:
1. DISCOVER: Explore system state before making changes
   - **CHECK NICS FIRST** (primary root cause!):
     for iface in $(ls /sys/class/net/ | grep -v lo); do
       speed=$(ethtool $iface 2>/dev/null | grep Speed | awk '{print $2}')
       ip=$(ip addr show $iface | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
       echo "$iface: $speed (IP: $ip)"
     done
   - Check which IP benchmark uses: On benchmark node, grep 'test-machine' /etc/hosts
   - Check CPU cores: nproc
   - Check memory: free -h
   - Check nginx config: cat /etc/nginx/nginx.conf
   - Check nginx workers: ps aux | grep nginx
   - Check file limits: ulimit -n, cat /proc/$(pgrep -o nginx)/limits
   - Check kernel params: sysctl net.core.somaxconn, net.ipv4.tcp_congestion_control
   - Check disk: cat /sys/block/nvme0n1/queue/scheduler

2. ANALYZE: Identify bottlenecks from collected data
   - If using 25G NIC but 100G available, this is PRIMARY root cause!

3. TUNE: Apply changes systematically (backup first!)
   - Switch to 100G NIC first if available (biggest impact)
   - Then apply nginx tunings
   - Then kernel tunings

4. VERIFY: Run benchmark after each change

5. ITERATE: If no improvement, try different approach

TUNING AREAS (in priority order):

NGINX (immediate effect):
- worker_processes auto (match CPU cores)
- worker_rlimit_nofile 65535 (file descriptor limit per worker)
- worker_connections 4096 (concurrent connections per worker)
- open_file_cache max=10000 inactive=60s (CRITICAL for small files)
- sendfile on, tcp_nopush on, tcp_nodelay on
- access_log off (reduce I/O overhead)
- keepalive_requests 10000
- aio threads, directio 512k (for large files)

KERNEL TCP (immediate via sysctl):
- net.core.somaxconn = 65535
- net.core.rmem_max = 67108864 (64MB)
- net.core.wmem_max = 67108864
- net.ipv4.tcp_rmem = 4096 1048576 67108864
- net.ipv4.tcp_wmem = 4096 1048576 67108864
- net.ipv4.tcp_congestion_control = bbr
- net.core.netdev_max_backlog = 65535

FILE LIMITS:
- /etc/systemd/system/nginx.service.d/limits.conf with LimitNOFILE=65535
- After creating, run: systemctl daemon-reload && systemctl restart nginx

DISK I/O:
- NVMe scheduler: echo none > /sys/block/nvme0n1/queue/scheduler
- Read-ahead: blockdev --setra 8192 /dev/nvme0n1

NETWORK (CRITICAL - CHECK FIRST!):
- **PRIMARY ROOT CAUSE**: RHEL 9.7 migration often changes default NIC from 100G to 25G!
- Discover all NICs and speeds:
  for iface in $(ls /sys/class/net/ | grep -v lo); do
    speed=$(ethtool $iface 2>/dev/null | grep Speed | awk '{print $2}')
    ip=$(ip addr show $iface | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
    echo "$iface: $speed (IP: $ip)"
  done
- If 100G NIC available but using 25G, switch benchmark node's /etc/hosts:
  On benchmark node: Update "test-machine" entry to point to 100G NIC IP
  ssh benchmark_host "sed -i 's/^[^#].*test-machine/#&/' /etc/hosts"
  ssh benchmark_host "echo '<100G-IP> test-machine' >> /etc/hosts"
- This alone can give 3-4x improvement for medium/large files!
- Ring buffers: ethtool -G <iface> rx 2047 tx 2047

TUNED PROFILE:
- tuned-adm profile throughput-performance

REBOOT-REQUIRED CHANGES (note these but don't apply):
- NUMA balancing changes
- Hugepages configuration
- Kernel boot parameters (isolcpus, nohz_full)
- BIOS settings (C-states, P-states)
If you identify such optimizations, note them in your summary as "would require reboot".

RULES:
- ALWAYS backup before changing: cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak
- ALWAYS test nginx: nginx -t before reload
- ALWAYS reload after nginx changes: nginx -s reload OR systemctl reload nginx
- ONE change at a time, then benchmark
- If something breaks, rollback immediately
- Log your reasoning for each decision

CRITICAL BENCHMARK RULES:
- ALWAYS use the run_benchmark tool for performance measurement!
- NEVER use 'ab' (Apache Bench) or 'curl' for performance testing - they give inaccurate results
- run_benchmark uses 'wrk' with proper settings (16 threads, 300 connections, 60 seconds)
- ab gives 50x lower numbers than wrk - DO NOT USE IT
- Focus on workloads: small, medium
- For MEDIUM files: You MUST switch to 100G NIC first - it's network-limited on 25G!

When done, call the 'done' tool with a detailed summary including:
- What bottlenecks were found
- What changes were applied
- Before/after performance numbers
- Any reboot-required optimizations identified but not applied"""


class AgenticRunner:
    """Runs the autonomous agent loop."""

    def __init__(
        self,
        sut_host: str,
        benchmark_host: str,
        llm_client,
        max_iterations: int = 20,
        target_improvement: float = 0.10,
    ):
        self.sut = SSHClient(sut_host)
        self.benchmark = SSHClient(benchmark_host)
        self.tools = AgentTools(self.sut, self.benchmark)
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.target_improvement = target_improvement
        self.state = AgentState()
        self.messages: list = []
        self.decision_log: list = []

    def run(self) -> AgentState:
        """Run the autonomous agent loop."""
        # Get initial baseline
        print(">> Getting baseline performance...")
        baseline = self._run_quick_benchmark()
        self.state.baseline_rps = baseline
        print(f"   Baseline: {baseline}")

        # Initialize conversation
        self.messages = [
            {
                "role": "user",
                "content": f"""You are connected to:
- SUT (nginx server): {self.sut.host}
- Benchmark node: {self.benchmark.host}

Baseline performance:
{json.dumps(baseline, indent=2)}

Target: Improve requests/sec by at least {self.target_improvement*100:.0f}%

Start by exploring the system to identify bottlenecks. Use the tools provided."""
            }
        ]

        # Agentic loop
        while not self.state.done and self.state.iteration < self.max_iterations:
            self.state.iteration += 1
            print(f"\n>> Iteration {self.state.iteration}/{self.max_iterations}")

            # Call LLM with tools
            response = self._call_llm_with_tools()

            # Process response
            if response.stop_reason == "tool_use":
                self._handle_tool_calls(response)
            elif response.stop_reason == "end_turn":
                # Agent is thinking, add response and continue
                self._add_assistant_message(response)
                self.messages.append({
                    "role": "user",
                    "content": "Continue. Use tools to explore or apply changes."
                })

        return self.state

    def _call_llm_with_tools(self):
        """Call LLM with tool definitions."""
        response = self.llm.client.messages.create(
            model=self.llm.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=self.tools.get_tool_definitions(),
            messages=self.messages,
        )

        # Track tokens
        self.llm._get_usage(self.llm.model).add(
            response.usage.input_tokens,
            response.usage.output_tokens
        )

        return response

    def _handle_tool_calls(self, response):
        """Handle tool calls from LLM response."""
        # Add assistant message with tool use
        self._add_assistant_message(response)

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = self._execute_tool(block.name, block.input, block.id)
                tool_results.append(result)

        # Add tool results to messages
        self.messages.append({
            "role": "user",
            "content": tool_results
        })

    def _execute_tool(self, name: str, inputs: dict, tool_use_id: str) -> dict:
        """Execute a single tool and return result."""
        print(f"   Tool: {name}")

        # Log decision
        self.decision_log.append({
            "iteration": self.state.iteration,
            "tool": name,
            "inputs": inputs,
            "timestamp": datetime.utcnow().isoformat(),
        })

        if name == "done":
            self.state.done = True
            self.state.success = inputs.get("success", False)
            self.state.summary = inputs.get("summary", "")
            output = "Agent signaled completion."

        elif name == "run_command":
            result = self.tools.run_command(
                inputs["command"],
                inputs.get("target", "sut")
            )
            output = result.output if result.success else f"Error: {result.error}"
            print(f"      {inputs['command'][:50]}...")

        elif name == "read_file":
            result = self.tools.read_file(
                inputs["path"],
                inputs.get("target", "sut")
            )
            output = result.output if result.success else f"Error: {result.error}"

        elif name == "write_file":
            result = self.tools.write_file(inputs["path"], inputs["content"])
            output = "File written successfully" if result.success else f"Error: {result.error}"
            self.state.actions_taken.append({
                "type": "write_file",
                "path": inputs["path"],
            })

        elif name == "run_benchmark":
            result = self.tools.run_benchmark(inputs.get("workload", "small"))
            output = result.output if result.success else f"Error: {result.error}"
            # Update current rps if we can parse it
            self._update_current_rps(inputs.get("workload"), output)

        else:
            output = f"Unknown tool: {name}"

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": output[:8000],  # Truncate long outputs
        }

    def _add_assistant_message(self, response):
        """Add assistant response to messages."""
        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
                print(f"   Agent: {block.text[:100]}...")
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        self.messages.append({"role": "assistant", "content": content})

    def _run_quick_benchmark(self) -> dict:
        """Run quick benchmark to get baseline."""
        results = {}
        for workload in ["small", "medium"]:
            result = self.tools.run_benchmark(workload)
            if result.success:
                # Parse rps from output
                import re
                match = re.search(r"Requests/sec:\s+([\d.]+)", result.output)
                if match:
                    results[workload] = float(match.group(1))
        return results

    def _update_current_rps(self, workload: str, output: str):
        """Update current rps from benchmark output."""
        import re
        match = re.search(r"Requests/sec:\s+([\d.]+)", output)
        if match and workload:
            self.state.current_rps[workload] = float(match.group(1))

    def get_decision_log(self) -> list:
        """Get the decision log."""
        return self.decision_log
