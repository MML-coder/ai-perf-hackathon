"""
LLM wrapper with token tracking for Claude API.
Supports both direct Anthropic API and Google Cloud Vertex AI.
"""
import os
from dataclasses import dataclass
from typing import Optional


# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "claude-sonnet-4@20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4@20250514": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5@20251001": {"input": 0.80, "output": 4.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


@dataclass
class TokenUsage:
    """Track token usage per model."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1

    def cost(self) -> float:
        """Calculate cost in USD."""
        pricing = MODEL_PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "api_calls": self.calls,
            "cost_usd": round(self.cost(), 4),
        }


@dataclass
class LLMResponse:
    """Response from LLM with content and token info."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str


class ClaudeClient:
    """Claude API client with token tracking. Supports Vertex AI and direct API."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    # Vertex AI model mapping (Vertex uses different model names)
    VERTEX_MODELS = {
        "sonnet": "claude-sonnet-4@20250514",
        "opus": "claude-opus-4@20250514",
        "haiku": "claude-haiku-4-5@20251001",
        "claude-sonnet-4-20250514": "claude-sonnet-4@20250514",
        "claude-opus-4-20250514": "claude-opus-4@20250514",
        "claude-haiku-4-5-20251001": "claude-haiku-4-5@20251001",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_vertex: bool = False,
        vertex_project_id: Optional[str] = None,
        vertex_region: str = "us-east5",
    ):
        self.use_vertex = use_vertex
        self.model = model or self.DEFAULT_MODEL
        self.usage: dict[str, TokenUsage] = {}

        if use_vertex:
            from anthropic import AnthropicVertex
            project_id = vertex_project_id or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
            if not project_id:
                raise ValueError("Vertex project ID required. Set ANTHROPIC_VERTEX_PROJECT_ID or pass vertex_project_id")
            self.client = AnthropicVertex(project_id=project_id, region=vertex_region)
            # Convert model name for Vertex
            if self.model in self.VERTEX_MODELS:
                self.model = self.VERTEX_MODELS[self.model]
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)

    def _get_usage(self, model: str) -> TokenUsage:
        if model not in self.usage:
            self.usage[model] = TokenUsage(model=model)
        return self.usage[model]

    def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a prompt to Claude and track token usage."""
        model = model or self.model

        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Track usage
        self._get_usage(model).add(input_tokens, output_tokens)

        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
        )

    def get_total_usage(self) -> list[dict]:
        """Get token usage summary for all models."""
        return [usage.to_dict() for usage in self.usage.values()]

    def get_usage_report(self) -> str:
        """Generate a markdown table of token usage with cost."""
        lines = ["| Model | Input Tokens | Output Tokens | Total | API Calls | Cost (USD) |",
                 "|-------|--------------|---------------|-------|-----------|------------|"]

        total_input = 0
        total_output = 0
        total_calls = 0
        total_cost = 0.0

        for usage in self.usage.values():
            total = usage.input_tokens + usage.output_tokens
            cost = usage.cost()
            lines.append(
                f"| {usage.model} | {usage.input_tokens:,} | {usage.output_tokens:,} | {total:,} | {usage.calls} | ${cost:.4f} |"
            )
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_calls += usage.calls
            total_cost += cost

        lines.append(
            f"| **Total** | **{total_input:,}** | **{total_output:,}** | **{total_input + total_output:,}** | **{total_calls}** | **${total_cost:.4f}** |"
        )

        return "\n".join(lines)
