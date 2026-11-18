"""LLM access with a hard per-bug budget.

Every system (S0, S1, S2, S2-R) talks to the model only through `LLM.chat`,
which charges the shared `Budget`. This is what makes the equal-budget
comparison (RQ1) enforceable rather than a convention.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol


class QuotaExhausted(RuntimeError):
    """The API account has no credit left; retrying cannot help."""


FATAL_API_CODES = ("insufficient_quota", "credit_balance_exhausted", "invalid_api_key", "no credits remaining")


class BudgetExceeded(Exception):
    """Raised when a system tries to call the model after its budget is spent."""


@dataclass
class Budget:
    max_calls: int = 8
    max_output_tokens: int = 8000
    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    log: list[dict] = field(default_factory=list)

    @property
    def remaining_calls(self) -> int:
        return self.max_calls - self.calls

    @property
    def remaining_tokens(self) -> int:
        return self.max_output_tokens - self.output_tokens

    def check(self) -> None:
        if self.remaining_calls <= 0 or self.remaining_tokens <= 0:
            raise BudgetExceeded(
                f"calls {self.calls}/{self.max_calls}, "
                f"output tokens {self.output_tokens}/{self.max_output_tokens}"
            )

    def charge(self, role: str, prompt_tokens: int, output_tokens: int, latency: float) -> None:
        self.calls += 1
        self.prompt_tokens += prompt_tokens
        self.output_tokens += output_tokens
        self.latency_s += latency
        self.log.append(
            {"role": role, "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
             "latency_s": round(latency, 3)}
        )

    def usage(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "latency_s": round(self.latency_s, 3),
            "max_calls": self.max_calls,
            "max_output_tokens": self.max_output_tokens,
        }


class LLM(Protocol):
    model: str

    def chat(self, messages: list[dict], budget: Budget, role: str) -> str: ...


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OpenAICompatibleLLM:
    """Any OpenAI-compatible chat endpoint (OpenAI, Groq, OpenRouter, Ollama...).

    Configured with environment variables:
      LLM_MODEL      model name (required)
      LLM_BASE_URL   endpoint, default https://api.openai.com/v1
      LLM_API_KEY    key (falls back to OPENAI_API_KEY)
    """

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.2,
                 per_call_max_tokens: int = 1500, retries: int = 4):
        from openai import OpenAI

        self.model = model or os.environ.get("LLM_MODEL") or ""
        if not self.model:
            raise ValueError("Set LLM_MODEL (e.g. a small, cheap chat model).")
        self.temperature = temperature
        self.per_call_max_tokens = per_call_max_tokens
        self.retries = retries
        self.client = OpenAI(
            base_url=base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1",
            api_key=api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
        )

    def chat(self, messages: list[dict], budget: Budget, role: str) -> str:
        budget.check()
        max_tokens = max(1, min(self.per_call_max_tokens, budget.remaining_tokens))
        last_err: Exception | None = None
        for attempt in range(self.retries):
            t0 = time.time()
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages,
                    temperature=self.temperature, max_tokens=max_tokens,
                )
            except Exception as err:  # rate limits / transient network errors
                detail = f"{err} {getattr(err, 'code', '')} {getattr(err, 'body', '')}"
                if any(code in detail for code in FATAL_API_CODES):
                    raise QuotaExhausted(str(err)) from err
                last_err = err
                time.sleep(2 ** attempt)
                continue
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            p = getattr(usage, "prompt_tokens", None) or _estimate_tokens(str(messages))
            o = getattr(usage, "completion_tokens", None) or _estimate_tokens(text)
            budget.charge(role, p, o, time.time() - t0)
            return text
        raise RuntimeError(f"LLM call failed after {self.retries} attempts: {last_err}")


class ScriptedLLM:
    """Returns pre-written replies in order. For unit tests only, never for results."""

    def __init__(self, replies: list[str], model: str = "scripted-test-double"):
        self.replies = list(replies)
        self.model = model
        self.seen: list[list[dict]] = []

    def chat(self, messages: list[dict], budget: Budget, role: str) -> str:
        budget.check()
        self.seen.append(messages)
        text = self.replies.pop(0) if self.replies else ""
        budget.charge(role, _estimate_tokens(str(messages)), _estimate_tokens(text), 0.0)
        return text
