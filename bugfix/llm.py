"""LLM access with a hard per-bug budget.

Every system (S0, S1, S2, S2-R) talks to the model only through `LLM.chat`,
which charges the shared `Budget`. This is what makes the equal-budget
comparison (RQ1) enforceable rather than a convention.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol


class QuotaExhausted(RuntimeError):
    """The API account has no credit left; retrying cannot help."""


FATAL_API_CODES = ("insufficient_quota", "credit_balance_exhausted", "invalid_api_key", "no credits remaining", "no longer available", "NOT_FOUND")


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
    input_limit_reached: bool = False

    @property
    def remaining_calls(self) -> int:
        return self.max_calls - self.calls

    @property
    def remaining_tokens(self) -> int:
        return self.max_output_tokens - self.output_tokens

    def check(self) -> None:
        if self.remaining_calls <= 0 or self.remaining_tokens <= 0 or any(e.get("limit_exceeded") for e in self.log):
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
            "provider_limit_violations": sum(entry.get("limit_exceeded", False) for entry in self.log),
        }


class LLM(Protocol):
    model: str

    def chat(self, messages: list[dict], budget: Budget, role: str) -> str: ...


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class RateLimiter:
    """Spaces calls evenly so all worker threads together stay under `rpm` requests/minute."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self.next_slot = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        time.sleep(max(0.0, slot - now))


def _retry_after(detail: str, default: float = 30.0) -> float:
    m = re.search(r"retry in ([0-9.]+)s", detail)
    return min(120.0, float(m.group(1)) + 1.0) if m else default


class OpenAICompatibleLLM:
    """Any OpenAI-compatible chat endpoint (OpenAI, Groq, OpenRouter, Ollama...).

    Configured with environment variables:
      LLM_MODEL      model name (required)
      LLM_BASE_URL   endpoint, default https://api.openai.com/v1
      LLM_API_KEY    key (falls back to OPENAI_API_KEY)
      LLM_RPM        optional client-side cap on requests per minute (e.g. 14 for a 15 RPM free tier)

    Rate-limit errors are retried after the delay the API asks for and are never
    charged to the budget; only completed calls count.
    """

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.2,
                 per_call_max_tokens: int = 1500, retries: int = 10, rpm: float | None = None,
                 max_prompt_bytes: int | None = None, stop_at_prompt_limit: bool = False):
        from openai import OpenAI

        self.model = model or os.environ.get("LLM_MODEL") or ""
        if not self.model:
            raise ValueError("Set LLM_MODEL (e.g. a small, cheap chat model).")
        self.temperature = temperature
        self.per_call_max_tokens = per_call_max_tokens
        self.retries = retries
        self.max_prompt_bytes = max_prompt_bytes
        self.stop_at_prompt_limit = stop_at_prompt_limit
        self.client = OpenAI(
            base_url=base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1",
            api_key=api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            max_retries=0,  # retries are handled below so rate-limit waits are explicit
        )
        self.limiter = RateLimiter(rpm if rpm is not None else float(os.environ.get("LLM_RPM", "0")))

    def chat(self, messages: list[dict], budget: Budget, role: str) -> str:
        budget.check()
        if self.max_prompt_bytes is not None:
            size = sum(len(m["content"].encode("utf-8")) + 32 for m in messages)
            if size > self.max_prompt_bytes:
                if self.stop_at_prompt_limit and budget.calls:
                    budget.input_limit_reached = True
                    raise BudgetExceeded("Next prompt exceeds the input limit")
                raise ValueError("Prompt exceeds the configured input limit")
        max_tokens = max(1, min(self.per_call_max_tokens, budget.remaining_tokens))
        last_err: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait()
            t0 = time.time()
            try:
                limit = ({"max_completion_tokens": max_tokens, "reasoning_effort": "none"}
                         if self.model.startswith("gpt-5.4-nano") else {"max_tokens": max_tokens})
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=self.temperature, **limit,
                )
            except Exception as err:  # rate limits / transient network errors
                detail = f"{err} {getattr(err, 'code', '')} {getattr(err, 'body', '')}"
                if any(code in detail for code in FATAL_API_CODES) or re.search(r"per ?day", detail, re.I):
                    raise QuotaExhausted(detail[:2000]) from err
                last_err = err
                rate_limited = "429" in detail or "RESOURCE_EXHAUSTED" in detail
                if attempt + 1 < self.retries:
                    time.sleep(_retry_after(detail) if rate_limited else 2 ** min(attempt, 5))
                continue
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            p = getattr(usage, "prompt_tokens", None) or _estimate_tokens(str(messages))
            o = getattr(usage, "completion_tokens", None) or _estimate_tokens(text)
            budget.charge(role, p, o, time.time() - t0)
            if usage is not None and o > max_tokens:
                budget.log[-1]["limit_exceeded"] = True
                # The provider has already consumed these tokens. Preserve measured
                # usage and prevent further calls or use of the over-limit reply.
                raise BudgetExceeded(f"Provider reported {o} tokens for a {max_tokens}-token request")
            return text
        raise RuntimeError(f"LLM call failed after {self.retries} attempts") from last_err


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
