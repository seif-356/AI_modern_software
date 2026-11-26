# Phase 3 replication guide

The [IEEE paper](phase3_report.pdf), [presentation](presentation.pdf) and [recorded demo](demo.mp4) accompany the [replication branch](https://github.com/seif-356/AI_modern_software/tree/phase-3-study). The sources for the paper and slides are editable LaTeX. Run commands below from the repository root with Python 3.11. Install the measured Python dependencies with `python -m pip install -r requirements-phase3.txt`.

## Replay and inspect

```sh
python scripts/demo_phase3.py
python -m streamlit run dashboard/app.py
python -m pytest -o addopts= -q
```

The replay script finds an actual archived Gemini S2 approval and executes the saved patch on the original visible and held-out tests. In the dashboard, select the archive, `quixbugs/max_sublist_sum`, S2, run 0. Inspect the source diff and reviewer message, then compare the reserved example with the reported prediction.

## Study blocks

| Block | Sampling and unit | Run evidence |
|---|---|---|
| Archived Gemini | 31 QuixBugs functions × four systems × three repetitions, eight calls and 8,000 output tokens maximum | [Original raw JSONL](../../results/raw/quixbugs_gemini-3.5-flash-lite.jsonl) |
| Matched model panel | Three QuixBugs functions and three ConDefects submissions, each in original and renamed form. One run per system per variant | [Data and source manifest](../../data/phase3/) · [new traces](../../results/phase3/raw/) |
| GPT breadth study | 100 different ConDefects tasks, one eligible Python submission per task, one run per system | [Program records, licenses and difficulty ratings](../../data/condefects/) · [raw traces](../../results/phase3/raw/openai-breadth.jsonl) |

A new attempt can use four requests, 1,536 completion tokens in total and 512 per request. Temperature is requested at 0.2. The archived model is exactly `gemini-3.5-flash-lite`. It is analyzed exclusively from its 372 historical records. The new runs use one repetition per condition to direct available inference towards model diversity and 100 distinct contest tasks. Compare architectures within a study block. The [inventory](../../results/phase3/inventory.csv) distinguishes completed and planned counts.

The first new panel records carry the base Git commit of the working checkout while the Phase 3 code was being developed. The implementation is committed on this branch. The JSONL records also identify the exact dataset digest, model, temperature and token limits. Hosted inference and concurrent local sampling can produce different patches on a rerun.

## Rebuild published results without inference

```sh
python scripts/analyze.py --raw results/raw/quixbugs_gemini-3.5-flash-lite.jsonl --out results
python scripts/analyze_phase3.py
python scripts/plot_difficulty.py
python scripts/paper_tables.py
tectonic docs/phase3/phase3_report.tex
tectonic docs/phase3/presentation.tex
```

For Tectonic installations requiring an explicit bundle, use `-b https://data1b.fullyjustified.net/tlextras-2022.0r0.tar`. The paper uses IEEEtran and the talk uses Beamer. The [outcome counts](../../results/phase3/outcomes.csv), [paired system comparisons](../../results/phase3/system_pairs.csv), [renaming discordances](../../results/phase3/renaming_pairs.csv), [reviewer decisions](../../results/phase3/reviewers.csv) and [difficulty breakdown](../../results/phase3/difficulty.csv) are derived from the stored records. The figure uses 95% Wilson score intervals per difficulty band and system. The archived bootstrap intervals resample bugs.

## Reproduce datasets

```sh
git clone https://github.com/appmlk/ConDefects.git ConDefects
git -C ConDefects checkout 43f0834a82c5e3bc4516c079fe7765f63b1a15cd
python scripts/prepare_phase3.py --src ConDefects
python scripts/prepare_condefects.py --src ConDefects --cache ../sw403-example-cache
```

The matched panel uses independent, study-authored contest test oracles and the archived QuixBugs split. Its builder verifies both reference programs and the equality of failing test IDs in each original/renamed pair. The breadth builder reads public English sample inputs and outputs from the linked AtCoder task statements. It validates references, records a visible failure for each submitted program and preserves the source URLs. The cache permits interrupted downloads to resume. Use the checked-in data to replicate the study inputs byte for byte.

## Supplementary Muse browser panel

Muse ran once per workflow and variant on the 12 matched inputs. Each visible submission used a fresh Edge side chat with the repository's role instructions and visible evidence in one message. Local tests supplied feedback to the workflow. The four-submission ceiling applied per attempt. Model identity, token ceilings, temperature, internal tool use and account memory were unverified. No paid API requests or upgrades were used.

The 48 [scored attempts](../../results/phase3/pilots/muse-web-panel.jsonl) use the [original GCD pilot](../../results/phase3/pilots/muse-web-gcd.json) once and [83 subsequent role prompts and replies](../../results/phase3/pilots/muse-web-calls.jsonl). A discarded collection pass recorded 27 additional replies. Some code blocks were truncated during capture. The pass was excluded in full before restarting the remaining 47 attempts. Final collection used persisted replies and Muse's **Copy code** control for patches. Each workflow solved 10 of 12 variants and failed held-out tests on both presentations of ABC223 A.

Run `python scripts/run_muse_web.py` from the repository root to reproduce the 48 scores offline. The replay checks each stored role and prompt, re-executes visible and held-out tests, and writes the supplemental panel file. The primary study tables use their original 992 attempts.

## Full Muse browser evaluation

The [browser logs and scores](../../results/phase3/muse-web-full/) contain one trial per workflow for each of the 31 original QuixBugs programs and 100 ConDefects tasks. Each dataset is divided into four files by input index modulo four. Each score identifies the input by SHA-256 and records the final code, visible and held-out passes, reviewer decision and message count. The 12 trials shared with the matched panel cover GCD, valid parenthesization and maximum sublist sum. Their prompts and replies are in the matched-panel files above. The expanded evaluation used 902 new messages and 21 messages from those shared trials.

| Workflow | QuixBugs passing both partitions (of 31) | ConDefects passing both partitions (of 100) |
|---|---:|---:|
| S0 | 30 | 96 |
| S1 | 30 | 97 |
| S2 | 30 | 98 |
| S2-R | 30 | 98 |

We repeated 27 trials in full after finding 34 unresolved code-block placeholders. The [exclusion manifest](../../results/phase3/muse-web-full/excluded-captures.jsonl) identifies those trials and their 63 discarded replies. The table uses only the final captures. Message totals count accepted role responses in scored trials. Browser delivery retries and discarded captures are outside that count.

Run the following from the repository root to replay the expanded study offline. The replay checks roles, prompts, input identities and scores. One faulty ConDefects submission prints a two-element Python set whose display order can vary. Its replay accepts either order in the test feedback. Held-out timeouts can also vary with machine load. The replay reports those timing differences and preserves the originally measured scores. The same Levenshtein case timed out in all four measured QuixBugs workflows.

~~~sh
python scripts/run_muse_full.py --lane 0
python scripts/run_muse_full.py --lane 1
python scripts/run_muse_full.py --lane 2
python scripts/run_muse_full.py --lane 3
~~~

For fresh browser collection, use a separate checkout with empty lane files and add `--collect` to a lane command. Open the loopback form on port 18220 plus the lane number. Send its prompt in a fresh Muse side chat in Edge, capture the complete first response with the site's copy control for each code block, and submit the response on the local form. The collector runs the tests and supplies each subsequent role prompt. The protocol measures at most four accepted browser submissions per trial. The web app exposes no verifiable API model ID or token budget.

## Full-dataset model runs

The [coverage table](../../results/phase3/full-models/coverage.csv) joins the original and expanded studies by exact input and workflow. A scored failure counts as a completed trial. The table uses Gemini repeat zero for the four pass-count columns. The archive retains all three repeats. The 100-task ConDefects sample excludes the three contest tasks in the matched panel.

Run the audit locally to regenerate the totals and a list of every missing cell.

~~~sh
python scripts/full_model_coverage.py --missing missing-runs.csv
~~~

The new cohorts are `full-quixbugs` and `full-condefects`. Append `--dry-run` to inspect the remaining work without inference. Each local model can serve both cohorts in one session.

~~~sh
python scripts/run_phase3.py --profile openai --cohort full-quixbugs --dry-run
python scripts/run_local.py --profile qwen --server /path/to/llama-server --weights /path/to/models --cohort full-quixbugs full-condefects
~~~

These cohorts reuse rows only when the original input, tests, model and generation settings match. New rows are saved after scoring. The expansion uses the same four-call and 1,536-output-token attempt budgets, with up to 512 output tokens per call. The runner checks the 16,384-byte prompt limit before inference. If a later prompt exceeds the limit, the scorer evaluates the candidate available at that point and records `input_limit`. A later request that the local server rejects for exceeding its context window similarly records `context_limit`. An oversized initial prompt is an unexecuted trial. Add `--paper` to the coverage audit to regenerate the paper table after all four GPT/local samples are complete. The original matched panel, breadth experiment, archived Gemini runs and Muse browser supplement remain identifiable by their source files.

## Model execution

The [provider notes](../../results/phase3/provider_notes.md) document endpoints, actual status and measured usage. The [MAST trace table](../../results/phase3/mast_failures.csv) links failed S2 attempts to observed repetition, specification or verification failures. Other diagnoses remain unresolved when the trace does not distinguish them. For the optional Windows demo recording, start Streamlit on port 18185 and run `python scripts/record_demo.py` with Playwright, Edge, ffmpeg and the local System.Speech synthesizer installed.

The Phase 3 runner checks the target JSONL for already completed attempts and incompatible configurations before requesting credentials. A completed file produces zero further requests. To collect a fresh independent replication, use a separate checkout and move the target raw file aside in that checkout. Keep the published raw files available for comparison.

| Profile | Exact requested model | Endpoint or weight source |
|---|---|---|
| `openai` | `gpt-5.4-nano-2026-03-17` | OpenAI Chat Completions, `OPENAI_API_KEY` |
| `orca` | `deepseek/deepseek-v4-flash-free` | OrcaRouter, `ORCAROUTER_API_KEY`. The runner checks the authenticated zero-price route |
| `qwen` | Qwen2.5-Coder-1.5B-Instruct Q4_K_M | [Official GGUF snapshot](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/tree/f86cb2c1fa58255f8052cc32aeede1b7482d4361) |
| `smollm2` | SmolLM2-1.7B-Instruct Q4_K_M | [Official GGUF snapshot](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/tree/2d4a76a30b4af41ecd395c35725ac11688d4cfe4) |
| `deepseek-coder` | DeepSeek Coder 1.3B Instruct Q4_K_M | [Pinned GGUF conversion](https://huggingface.co/TheBloke/deepseek-coder-1.3b-instruct-GGUF/tree/4595af8c3dff738094bd6c86054dfb5a90d5c41e) of the [upstream model](https://huggingface.co/deepseek-ai/deepseek-coder-1.3b-instruct) |
| `muse` | `muse-spark-1.3` | Meta, `MODEL_API_KEY`, standard metered endpoint |
| `deepseek` | `deepseek-flash` | Direct DeepSeek, `DEEPSEEK_API_KEY`, metered endpoint |

The inventory is the source of truth for measured models. Listing a provider profile documents how it can be run. A hosted execution goes only to the selected provider. There is no automatic model fallback. Missing keys are prompted with hidden input and candidate processes receive a restricted environment.

```sh
python scripts/run_phase3.py --profile openai --dry-run
python scripts/run_phase3.py --profile openai --cohort breadth --dry-run
python scripts/run_phase3.py --profile orca
```

The zero-price route can return HTTP 429 when its quota is exhausted. Successful attempts remain in the output for a later resume. See the [OrcaRouter model terms](https://www.orcarouter.ai/models/deepseek/deepseek-v4-flash-free) and [OpenAI model pricing](https://developers.openai.com/api/docs/models/gpt-5.4-nano).

The [budget audit](../../results/phase3/budget_audit.csv) compares reported usage to the recorded token and call limits. The free hosted DeepSeek route completed 28 of 48 cells before a quota response with a retry delay over 11 hours. Ten rows exceed the observable ceiling for their number of completed calls, including four above the total attempt cap. All 28 are retained as descriptive diagnostics and excluded from equal-budget paired comparisons. For earlier files with only aggregate usage the audit can identify some per-call violations but cannot certify every individual request. New runner versions retain per-call counts and stop an attempt when a provider reports an over-limit response.

For local inference, download the Q4_K_M GGUF file for the chosen model and install [llama.cpp b12776](https://github.com/ggml-org/llama.cpp/releases/tag/b12776). The measured machine used a Windows Vulkan build on a GTX 1650. Substitute the model and executable directories used on your system.

```sh
python scripts/run_local.py --profile qwen --server /path/to/llama-server --weights /path/to/models
python scripts/run_local.py --profile smollm2 --server /path/to/llama-server --weights /path/to/models
python scripts/run_local.py --profile deepseek-coder --server /path/to/llama-server --weights /path/to/models
```

The helper verifies the SHA-256 weight digest, starts a loopback-only service with the expected alias, runs the panel and terminates the process. The general FastAPI app can also use a running model server. Set `LLM_MODEL`, `LLM_BASE_URL` and `LLM_API_KEY` to its alias, loopback API URL and local placeholder key. Run `python -m uvicorn bugfix.api:app --host 127.0.0.1` and use the interactive documentation at `http://127.0.0.1:8000/docs` to post a repair.

## Independent review and course submission

Two team members each make a separate copy of the [blinded packet](../../results/phase3/review_packet.csv). Use the specification link and compare the candidate with the reference. Mark `correct` or `incorrect` and supply a short rationale or counterexample for each row. Preserve both original sets of judgments before discussing disagreements. The [key](../../results/phase3/review_key.json) maps packet IDs to model attempts after adjudication.

```sh
python scripts/analyze_phase3.py --ratings reviewer_a.csv reviewer_b.csv
```

The scorer checks complete, unique IDs and reports observed agreement and Cohen's kappa; kappa is undefined when both raters use the same single category throughout. The paper discloses the outstanding review. Course submission requires the students' own writing and contributions. The draft paper, talk and code disclose AI assistance. The team handles the Moodle submission and shares the branch link with the TA.
