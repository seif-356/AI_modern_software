# Inference provenance

The November 26, 2026 experiments use an archived Gemini block, local model weights and explicitly selected hosted routes. The [inventory](inventory.csv) counts saved, completed attempts. It does not count an API rejection as a repair failure.

| Provider | Observed outcome |
|---|---|
| Google Gemini | Reused all 372 stored `gemini-3.5-flash-lite` records from Phase 2. No new inference requests. |
| OpenAI | `gpt-5.4-nano-2026-03-17` completed 48 matched-panel attempts and 400 breadth attempts. The stored responses report 551,202 input tokens and 210,299 output tokens. At the listed uncached input and output rates, this is an estimated **US$0.3731** in API usage before any cache discount. The estimate is calculated from recorded usage, rather than an account invoice. [Model pricing](https://developers.openai.com/api/docs/models/gpt-5.4-nano) |
| OrcaRouter | The key's catalog advertised `deepseek/deepseek-v4-flash-free` at zero per request. The route completed 28 attempts, then returned HTTP 429 and a retry delay exceeding 11 hours. Ten attempts report more tokens than their calls could consume under the stated caps, including four above the total attempt allowance. We exclude this route from equal-budget paired comparisons. [Route pricing](https://www.orcarouter.ai/models/deepseek/deepseek-v4-flash-free) |
| Meta | The authenticated catalog listed `muse-spark-1.3`. The standard generation endpoint returned HTTP 402 and reported that the team must resolve billing verification. No Muse completion or repair score was recorded. |
| DeepSeek direct | The direct account was checked without sending a repair prompt. The hosted DeepSeek V4 Flash traces come from OrcaRouter. |
| Local llama.cpp | Qwen2.5-Coder-1.5B-Instruct, SmolLM2-1.7B-Instruct and DeepSeek-Coder-1.3B-Instruct use pinned GGUF files on loopback endpoints. These runs incur no provider API fees. Model revisions and weight checksums are in the [guide](../../docs/phase3/README.md) and [local runner](../../scripts/run_local.py). |

The [budget audit](budget_audit.csv) includes every recorded attempt. It flags a known breach when reported totals exceed the call or output cap, or exceed the per-call cap multiplied by completed calls. Where a per-call usage trace is available, the check also uses its violation flag. Earlier records contain aggregate usage, which cannot detect every possible single-call overrun.
