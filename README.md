# AI_modern_software

SW403 – AI in Modern Software Engineering (Fall 2026), Zewail City.

## Course project: Multi-Agent Bug Fixing System

**Research question:** Does multi-agent collaboration improve LLM-based bug fixing once
LLM-call budget, patch correctness (plausible vs. correct) and training-data contamination
are controlled?

| Phase | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Proposal & literature review (IEEE, 2–3 pages) | [`docs/phase1/proposal.tex`](docs/phase1/proposal.tex) | Draft |
| 2 | Prototype, experimental setup, early results | `src/` (planned) | Not started |
| 3 | Full prototype, 6–8 page paper, demo | – | Not started |

Planned stack: Python, LangGraph (agents), FastAPI (`POST /repair`), Streamlit (dashboard).
Datasets: QuixBugs-Python, ConDefects-Python sample.

## Team

<!-- TODO: names and student IDs; each member commits their own work -->
- Member 1 – datasets & evaluation module
- Member 2 – agents & FastAPI
- Member 3 – dashboard, manual labelling, statistics

## Labs

- [`lab1/`](lab1/) – Lab 1: manual vs. AI-generated pytest tests for `is_prime`

## AI tools used

Claude Code (Anthropic) – literature search/verification and drafting. Declared in each report.
