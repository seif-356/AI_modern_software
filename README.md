# AI_modern_software

SW403 – AI in Modern Software Engineering (Fall 2026), Zewail City.

## Course project: Multi-Agent Bug Fixing System

**Research question:** Does multi-agent collaboration improve LLM-based bug fixing once
LLM-call budget, patch correctness (plausible vs. correct) and training-data contamination
are controlled?

| Phase | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Proposal & literature review (IEEE, 2–3 pages) | [`docs/phase1/AI_modern_software_phase1.pdf`](docs/phase1/AI_modern_software_phase1.pdf) (source: [`proposal.tex`](docs/phase1/proposal.tex)) | Submitted |
| 2 | Prototype, experimental setup, early results | [`bugfix/`](bugfix/), [`scripts/`](scripts/), [`data/`](data/), [`results/`](results/) | In progress (due 23 Nov 2026) |
| 3 | Full prototype, 6–8 page paper, demo | – | Not started |

Stack: Python, LangGraph (agents), FastAPI (`POST /repair`), Streamlit (dashboard).
Datasets: QuixBugs-Python (Phase 2), ConDefects-Python sample (Phase 3).

## Project documentation

- [Architecture and repair API](docs/architecture.md) traces one repair through the four systems and includes a request you can try locally.
- [Experiment guide](docs/experiments.md) explains how to inspect the saved run, start or resume an experiment, and interpret the results.
- [Phase 2 report](docs/phase2/phase2_report.pdf) covers the research design, early findings and limitations.

## Replication package (Phase 2)

| Path | What it is |
|---|---|
| `bugfix/llm.py` | OpenAI-compatible model client with a hard per-bug budget (LLM calls + output tokens) |
| `bugfix/systems/` | **S0** single-shot, **S1** single agent with test feedback, **S2** LangGraph multi-agent (localiser → fixer → test-runner tool → reviewer), **S2-R** S2 without reviewer |
| `bugfix/sandbox.py`, `bugfix/harness.py` | Runs candidate code in an isolated subprocess with per-test timeouts and a memory limit |
| `bugfix/evaluate.py` | Automatic checker: correct / plausible-but-incorrect / failing on **held-out** tests, hallucination flags H1–H5 |
| `bugfix/api.py` | FastAPI service, `POST /repair` |
| `dashboard/app.py` | Streamlit dashboard: metrics, hallucinations, errors, per-attempt traces |
| `data/quixbugs/` | 31 QuixBugs Python bugs with a seeded visible / held-out test split (`bugs.jsonl`, `manifest.json`, MIT licence) |
| `scripts/prepare_quixbugs.py` | Rebuilds `data/quixbugs/` from a QuixBugs checkout |
| `scripts/run_experiment.py` | Runs systems × bugs × runs, appends to `results/raw/*.jsonl` (resumable) |
| `scripts/analyze.py` | Tables, bootstrap CIs, exact McNemar tests, figures → `results/` |
| `tests/` | Plumbing tests (scripted model, no API calls) and dataset validation |

### Quick start

Run these commands from the repository root in a Linux shell (WSL on Windows). Use Python 3.12 with `venv` and `pip` available. The candidate test harness uses Unix process limits and timers.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest
```

To explore the 372 saved attempts, run `python -m streamlit run dashboard/app.py` in the same environment. Both the tests and the dashboard work without model credentials. For a quick look without installing anything, open the [saved results summary](results/summary.md).

## Team

Each member commits their own work. Split to be confirmed by the team.

| Name | ID | Planned area |
|---|---|---|
| Seif Zaki | 202201554 | Datasets & evaluation module |
| Karim Wael | 202202212 | Agents & FastAPI |
| Ahmed Ayman | 202200168 | Dashboard, manual labelling, statistics |

## Labs

- [`lab1/`](lab1/) – Lab 1: manual vs. AI-generated pytest tests for `is_prime`

## AI tools used

Claude Code (Anthropic) – literature search/verification and drafting. Declared in each report.
