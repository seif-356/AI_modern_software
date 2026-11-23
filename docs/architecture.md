# Architecture and repair API

The command-line experiment runner and the FastAPI service use the same four Python repair systems. Each takes a `Bug`, a model client and a fresh `Budget`. A system returns a `RepairResult` containing the final program, stop reason, model usage and trace. The evaluator then assigns the outcome used by both entry points. [System registry](../bugfix/systems/__init__.py) · [Shared result type](../bugfix/systems/base.py)

## How a repair works and methodology 

1. The runner loads a benchmark record, or the API builds one from the request. The harness runs the original program on the visible tests. Repair prompts include the buggy program, visible cases and failure feedback. Held-out examples and reference code stay out of the prompts. [Bug records](../bugfix/bugs.py) · [Prompts](../bugfix/prompts.py)
2. The selected system generates a complete Python program. The patch parser takes the last supported fenced code block, or the full reply when there is no block. The test tool loads the candidate and calls the named function with each case's positional arguments. [Patch parsing](../bugfix/patching.py) · [Test runner](../bugfix/sandbox.py)
3. The evaluator reruns visible and held-out cases on the final candidate. A reviewer verdict and a test label answer different questions. An approved patch can still fail a held-out test. The API returns both values, and the experiment runner saves both in the attempt record. [Evaluator](../bugfix/evaluate.py)

| Mode | What uses the model budget | When the system returns |
|---|---|---|
| `s0` | One repair call | Returns the first candidate after testing it. |
| `s1` | One agent keeps a conversation and receives failure feedback | Stops at the first visible pass. On budget exhaustion it returns the latest candidate. |
| `s2` | A localiser identifies the fault, a fixer proposes a program, and a reviewer judges candidates that pass the visible tests | Failed tests or a rejected review send feedback to the fixer. Approval ends the loop. On budget exhaustion it prefers the latest visible-passing candidate, then the latest candidate, then the original program. |
| `s2r` | The same LangGraph localiser and fixer as `s2`, with the reviewer removed | Stops at the first visible pass or when the budget runs out. |

The call and output-token limits apply to the whole attempt, including all model roles. Test executions consume no model calls. Input tokens are recorded separately. Equal ceilings allow systems to use different numbers of calls and tokens. [Single-agent systems](../bugfix/systems/single.py) · [LangGraph systems](../bugfix/systems/multi.py) · [Model client and budget](../bugfix/llm.py)

The harness runs candidate code in a temporary directory in a separate `python -I` process. It defaults to two seconds per test and attempts to set a 1 GiB address-space limit. The child still runs with the host user's permissions. Run the prototype locally with trusted inputs. [Harness](../bugfix/harness.py)

## Try the API

Activate the environment from the [quick start](../README.md#quick-start), then launch the service from the repository root. A live repair needs the [model settings](experiments.md#run-a-new-experiment). The health check and the interactive API schema at `http://127.0.0.1:8000/docs` work before model configuration.

```bash
python -m uvicorn bugfix.api:app --host 127.0.0.1 --port 8000
```

In a second terminal, run `curl http://127.0.0.1:8000/health` to list supported systems. To request one repair, send a function and its test cases. The nested array in the first case passes one list as the argument to `find_max`.

```bash
curl -sS http://127.0.0.1:8000/repair \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "code": "def find_max(xs):\n    return min(xs)\n",
  "function_name": "find_max",
  "visible_tests": [{"input": [[1, 3, 2]], "output": 3}],
  "heldout_tests": [{"input": [[-4, -2, -9]], "output": -2}],
  "mode": "s1",
  "max_calls": 2,
  "max_output_tokens": 1000
}
JSON
```

`visible_tests` requires at least one case. `heldout_tests` defaults to an empty list. The default mode is `s2`. The request accepts `max_calls` from 1 to 30 (default 8) and `max_output_tokens` from 100 to 50,000 (default 8,000). An invalid mode, empty visible suite or out-of-range budget produces HTTP 422. A missing `LLM_MODEL` produces HTTP 503 on a repair request. [API implementation](../bugfix/api.py)

Read `patch` for the complete returned Python source, `stop_reason` for why the system stopped and `usage` for the calls and tokens spent. The top-level `label` gives the evaluator's verdict. Check `evaluation.heldout_total` alongside it. When the request omits held-out cases, a visible pass alone yields `correct`. The `trace` lists role replies and tool steps in order. [Evaluation labels and flags](experiments.md#read-an-attempt)
