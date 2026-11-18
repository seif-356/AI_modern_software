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

### Reproduce

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                       # 44 tests, no API key needed
export LLM_API_KEY=...                 # your key; never commit it
export LLM_MODEL=...                   # e.g. a small, cheap chat model
# optional: export LLM_BASE_URL=https://api.groq.com/openai/v1  (any OpenAI-compatible endpoint)
python scripts/run_experiment.py --systems s0 s1 s2 s2r --runs 3 --max-calls 8 --max-tokens 8000
python scripts/analyze.py
streamlit run dashboard/app.py
uvicorn bugfix.api:app                 # then POST /repair
```

Rebuild the dataset (optional): `git clone https://github.com/jkoppel/QuixBugs && python scripts/prepare_quixbugs.py --src QuixBugs`.

**Excluded from Phase 2:** the 9 QuixBugs graph programs (they use `node.py` objects, not JSON tests); listed in `data/quixbugs/manifest.json`.

## Team

Each member commits their own work. Split to be confirmed by the team.

| Name | ID | Planned area |
|---|---|---|
| Seif Zaki | 202201554 | Datasets & evaluation module |
| Karim Wael | 202202212 | Agents & FastAPI |
| Kareem Ezzaldin | 202201972 | Dashboard, manual labelling, statistics |

## Labs

- [`lab1/`](lab1/) – Lab 1: manual vs. AI-generated pytest tests for `is_prime`

## AI tools used

Claude Code (Anthropic) – literature search/verification and drafting. Declared in each report.
