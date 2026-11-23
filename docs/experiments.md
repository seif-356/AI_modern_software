# Experiment guide

## Inspect the saved Phase 2 run

The repository includes 372 recorded attempts with `gemini-3.5-flash-lite` at temperature 0.2. Each of the four systems ran three times on each of 31 Python bugs, with a ceiling of eight model calls and 8,000 output tokens per attempt. The table counts final patches from the saved records. [Raw attempts](../results/raw/quixbugs_gemini-3.5-flash-lite.jsonl) · [Summary and confidence intervals](../results/summary.md)

| System | Correct | Plausible but incorrect | Failing | Mean model calls |
|---|---:|---:|---:|---:|
| S0 single-shot | 90 | 3 | 0 | 1.00 |
| S1 with feedback | 90 | 3 | 0 | 1.00 |
| S2 with reviewer | 89 | 2 | 2 | 3.76 |
| S2-R without reviewer | 88 | 3 | 2 | 2.19 |

S1 passed the visible tests on the first call in all 93 attempts, so the saved run never exercised its retry loop. S2 used more calls and returned one fewer correct patch than S1. Their paired comparison had two wins for S1 and one for S2 (exact McNemar p = 1.0). This small public benchmark gives limited evidence about repair quality on unfamiliar programs. Model exposure to QuixBugs during training is unknown. [Paired results](../results/mcnemar.csv) · [Phase 2 report](phase2/phase2_report.pdf)

To regenerate the analysis, activate the [project environment](../README.md#quick-start) and run the following from the repository root. The explicit `--raw` selects the bundled run. The output goes to a separate directory so you can compare it with the published tables. This command makes no model calls.

```bash
python scripts/analyze.py \
  --raw results/raw/quixbugs_gemini-3.5-flash-lite.jsonl \
  --out /tmp/sw403-phase2-analysis
```

| Output | How to read it |
|---|---|
| `summary.csv`, `summary.md` | Outcome rates and usage by system. The 95% intervals resample bugs 2,000 times with seed 403, keeping each bug's runs together. |
| `per_bug.csv` | Number of correct runs for each bug and system. |
| `mcnemar.csv` | Exact two-sided comparisons paired by bug ID and run index. The two discordant counts show which system fixed cases the other missed. |
| `reviewer.csv` | Verdicts on final visible-passing S2 patches with a recorded review. This file is generated when qualifying patches exist. |
| `figures/correct_rate.png`, `figures/outcomes.png` | Correct rates with intervals, and the share of attempts in each outcome class. |

The dashboard reads JSONL files under `results/raw/`. Select one in the sidebar to inspect a bug's patch diff, labels and trace. The McNemar and reviewer tables come from CSV files in `results/` shared across that folder's raw runs. When comparing a new run, use the tables in its own analysis output directory. [Dashboard](../dashboard/app.py) · [Analysis script](../scripts/analyze.py)

## Run a new experiment

First preview the work without credentials. With a fresh output path, the command below reports 372 jobs to do. `--dry-run` reads the data and counts missing jobs without executing candidates or calling a model.

```bash
python scripts/run_experiment.py --systems s0 s1 s2 s2r --runs 3 \
  --out results/raw/my-run.jsonl --dry-run
```

A live run uses an OpenAI-compatible chat endpoint. Set the following environment variables in the shell that launches the runner or the API. Supply credentials through your environment and keep them out of the repository. [Model client](../bugfix/llm.py)

| Variable | Meaning |
|---|---|
| `LLM_MODEL` | Model identifier accepted by the endpoint. Required for live repairs. |
| `LLM_API_KEY` | Provider credential. The client falls back to `OPENAI_API_KEY`. |
| `LLM_BASE_URL` | API base URL. Defaults to `https://api.openai.com/v1`. |
| `LLM_RPM` | Optional requests-per-minute limit shared by worker threads. The default `0` disables client-side pacing. |

For a small live trial, the following command runs two systems once on one bug. The CLI expects the full dataset ID, including `quixbugs/`. It appends one JSON line per completed attempt. Use the same arguments and file to resume.

```bash
python scripts/run_experiment.py --bugs quixbugs/bitcount --systems s0 s1 \
  --runs 1 --max-calls 8 --max-tokens 8000 --workers 1 \
  --out results/raw/bitcount-trial.jsonl
```

To run the full design, remove the bug filter, select `s0 s1 s2 s2r`, set `--runs 3` and choose a fresh output file. Resume deduplicates only by `(bug_id, system, run)`. Changing the dataset, prompts, model, temperature or budget calls for a different file. Missing attempts remain eligible on the next invocation. Run a final dry run with the same arguments to check that zero jobs remain. [Experiment runner](../scripts/run_experiment.py)

## Read an attempt

Each JSONL record identifies the bug, system, zero-based run, model, temperature, budget and Git commit. It also stores wall time, token usage, final source, the trace, test counts and a label. Inspect `stop_reason` alongside the label. For example, a budget stop can still return a previously visible-passing candidate. [Repair systems and API](architecture.md)

| Label | Evaluator rule for the bundled dataset |
|---|---|
| `correct` | The candidate passes every visible and held-out test. Correctness is relative to those cases. |
| `plausible_incorrect` | All visible tests pass and at least one held-out test fails. |
| `failing` | The candidate fails to load or fails at least one visible test. |

The plausible-incorrect rate uses **all attempts** as its denominator. The overfitting rate uses only **visible-passing attempts**. H1 flags parse or load failures, H2 flags selected name, attribute or import errors and new third-party imports, H3 flags a change to the target's recorded positional argument names, H4 flags an unchanged normalised program, and H5 flags an incorrect patch approved by the reviewer. These are automatic indicators. A flag such as H3 can coexist with a passing label. [Evaluator](../bugfix/evaluate.py) · [Results aggregation](../scripts/analyze.py)

## Rebuild the QuixBugs data

The bundled split contains 118 visible and 122 held-out cases. Preparation retains cases the reference implementation passes, then divides passing and failing cases for each buggy program using seed 403. Every included bug has a visible failure and a held-out case. Nine graph programs lack compatible JSON cases. Their names and the exact upstream revision are in the [manifest](../data/quixbugs/manifest.json). The imported data carries the [QuixBugs MIT licence](../data/quixbugs/QUIXBUGS_LICENSE).

To rebuild from the recorded revision, run the commands below from the repository root with the project environment active. They write to a fresh temporary directory. Compare the two JSONL files to check the split on your machine. Reference-case timeouts can affect which cases are retained. [Preparation script](../scripts/prepare_quixbugs.py)

```bash
workdir=$(mktemp -d)
git clone https://github.com/jkoppel/QuixBugs.git "$workdir/QuixBugs"
git -C "$workdir/QuixBugs" checkout --detach 4257f44b0ff1181dedaedee6a447e133219fcebf
python scripts/prepare_quixbugs.py --src "$workdir/QuixBugs" --out "$workdir/prepared" --seed 403
diff -u data/quixbugs/bugs.jsonl "$workdir/prepared/bugs.jsonl"
```
