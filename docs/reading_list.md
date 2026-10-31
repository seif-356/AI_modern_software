# Reading list: Multi-Agent Bug Fixing System

Every entry was checked to exist (title, authors, venue) via web search on 2026-10-31.
Full texts were **not** read by Claude; each member must read the ★ papers before Phase 1.
`[P1]` = already cited in `docs/phase1/proposal.tex`.

## 1. Core (★ must read)

| # | Paper | Venue | Why it matters to us |
|---|---|---|---|
| 1 ★ | Qi, Long, Achour, Rinard – [An Analysis of Patch Plausibility and Correctness for Generate-and-Validate Patch Generation Systems](https://www.cs.toronto.edu/~fanl/papers/kali-issta2015.pdf) | ISSTA 2015 | Plausible ≠ correct: most reported patches were wrong. Basis of our held-out-test metric. [P1] |
| 2 ★ | Sobania, Briesch, Hanna, Petke – [An Analysis of the Automatic Bug Fixing Performance of ChatGPT](https://arxiv.org/abs/2301.08653) | APR @ ICSE 2023 | ChatGPT on QuixBugs-Python: 31/40 with dialogue. Direct baseline. [P1] |
| 3 ★ | Xia, Zhang – [Automated Program Repair via Conversation (ChatRepair)](https://arxiv.org/abs/2304.00385) | ISSTA 2024 | Single-agent loop with test feedback; 162/337 Defects4J at $0.42/bug. Model for our S1 baseline. [P1] |
| 4 ★ | Xia, Deng, Dunn, Zhang – [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489) | FSE 2025 | Simple pipeline competitive with agents. The main challenge to "multi-agent is better". [P1] |
| 5 ★ | Lee et al. – [UniDebugger (earlier: FixAgent): Hierarchical Multi-Agent Framework for Unified Software Debugging](https://arxiv.org/abs/2404.17153) | EMNLP 2025 | Closest prior work: multi-agent repair, reports all QuixBugs fixed. Claims changed across arXiv versions. [P1] |
| 6 ★ | Hu, Shang, Xu, He, Zhang – [Can GPT-O1 Kill All Bugs? An Evaluation of GPT-Family LLMs on QuixBugs](https://arxiv.org/abs/2409.10033) | APR @ ICSE 2025 | o1 40/40, GPT-4o 38/40: QuixBugs is saturated. [P1] |
| 7 ★ | Huang et al. – [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798) | ICLR 2024 | LLMs struggle to self-correct without external feedback → reviewer agent may rubber-stamp (RQ2). [P1] |
| 8 ★ | Tao, Zhou, Wang, Zhang, Zhang, Cheng – [MAGIS: LLM-Based Multi-Agent Framework for GitHub Issue Resolution](https://arxiv.org/abs/2403.17927) | NeurIPS 2024 | 4 agents; ablation: removing the QA agent drops 13.94% → 10.63% on SWE-bench. Precedent for our reviewer ablation. |

## 2. Agents and multi-agent systems

| # | Paper | Venue | Why |
|---|---|---|---|
| 9 | Bouzenia, Devanbu, Pradel – [RepairAgent: An Autonomous, LLM-Based Agent for Program Repair](https://arxiv.org/abs/2403.17134) | ICSE 2025 | Tool-using single agent; 164/835 Defects4J. [P1] |
| 10 | Yang et al. – [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793) | NeurIPS 2024 | Agent–tool interface design. [P1] |
| 11 | Zhang, Ruan, Fan, Roychoudhury – [AutoCodeRover: Autonomous Program Improvement](https://arxiv.org/abs/2404.05427) | ISSTA 2024 | AST-aware code search + LLM; $0.43/task. |
| 12 | Huang et al. – [AgentCoder: Multi-Agent Code Generation with Iterative Testing](https://arxiv.org/abs/2312.13010) | arXiv 2023–24 | Programmer / test-designer / test-executor agents; test designer kept independent of the code. |
| 13 | Rondon et al. – [Evaluating Agent-based Program Repair at Google](https://arxiv.org/abs/2501.07531) | ICSE SEIP 2025 | Industrial evidence; enterprise bugs differ from SWE-bench. |

## 3. LLM repair with execution feedback

| # | Paper | Venue | Why |
|---|---|---|---|
| 14 | Chen, Lin, Schärli, Zhou – [Teaching Large Language Models to Self-Debug](https://arxiv.org/abs/2304.05128) | ICLR 2024 | Execution feedback improves LLM self-repair. [P1] |

## 4. Benchmarks and contamination

| # | Paper | Venue | Why |
|---|---|---|---|
| 15 | Lin, Koppel, Chen, Solar-Lezama – [QuixBugs](https://github.com/jkoppel/QuixBugs) | SPLASH Companion 2017 | Our primary dataset: 40 one-line bugs, Python + Java. [P1] |
| 16 | Wu et al. – [ConDefects: Dataset to Address the Data Leakage Concern for LLM-based FL and APR](https://arxiv.org/abs/2310.16253) | FSE 2024 (Demo) | 1,625 Python bugs (AtCoder, Oct 2021–Sep 2023), built against leakage. Our second dataset. [P1] |
| 17 | Muennighoff et al. – [OctoPack (HumanEvalFix)](https://arxiv.org/abs/2308.07124) | ICLR 2024 | 164 human-written buggy functions with tests; fallback dataset. [P1] |
| 18 | Jimenez et al. – [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770) | ICLR 2024 | Standard repo-level benchmark; why we don't use it (cost). [P1] |
| 19 | Just, Jalali, Ernst – Defects4J: A Database of Existing Faults… | ISSTA 2014 | Standard Java APR benchmark used by 3, 9. [P1] |

## 5. Background and surveys

| # | Paper | Venue | Why |
|---|---|---|---|
| 20 | Le Goues, Nguyen, Forrest, Weimer – GenProg: A Generic Method for Automatic Software Repair | IEEE TSE 2012 | Classic pre-LLM APR. [P1] |
| 21 | Zhang et al. – [A Systematic Literature Review on LLMs for Automated Program Repair](https://arxiv.org/abs/2405.01466) | arXiv (v4, 2025) | Field overview (189 papers); scope changed across versions — cite the one you read. |

## 6. Multi-agent focus (added 2026-10-31)

Already above: #5 UniDebugger, #8 MAGIS, #12 AgentCoder (multi-agent); #4 Agentless, #7 Huang (evidence against).
⚠ = only title/abstract snippet confirmed; numbers not checked.

| # | Paper | Venue | Why |
|---|---|---|---|
| 22 ★ | Tran, Kiela – [Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets](https://arxiv.org/abs/2604.02460) | arXiv, Apr 2026 | Single agent ≥ multi-agent when token budget is equal. Explicitly excludes tool use / code execution → our RQ1 tests exactly that gap. |
| 23 ★ | Cemri, Pan et al. – [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) | NeurIPS 2025 | 14 failure modes in 3 categories (design, inter-agent misalignment, verification). Use to classify our multi-agent failures. |
| 24 | Huawei et al. – [CodeR: Issue Resolving with Multi-Agent and Task Graphs](https://arxiv.org/abs/2406.01304) | arXiv 2024 | Reproducer, localizer, editor, verifier on a fixed task graph; notes free agent chat can loop forever → justifies a fixed LangGraph graph. 28.33% SWE-bench Lite. |
| 25 | Hong, Zhuge et al. – [MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352) | ICLR 2024 | Role-based agents with structured hand-offs; naive agent chaining compounds hallucinations. |
| 26 | Qian et al. – [ChatDev: Communicative Agents for Software Development](https://aclanthology.org/2024.acl-long.810) | ACL 2024 | Chat-chain design/code/test agents; "communicative dehallucination". |
| 27 | Du, Li, Torralba, Tenenbaum, Mordatch – [Improving Factuality and Reasoning through Multiagent Debate](https://arxiv.org/abs/2305.14325) | ICML 2024 | Main evidence *for* multiple agents (fewer hallucinations) — but compute not matched (see #22). |
| 28 ⚠ | [MarsCode Agent: AI-native Automated Bug Fixing](https://arxiv.org/abs/2409.00899) | arXiv 2024 | Industrial multi-agent bug fixing (ByteDance). |
| 29 ⚠ | [SGAgent: Suggestion-Guided Multi-Agent Framework for Repository-Level Software Repair](https://arxiv.org/abs/2602.23647) | arXiv 2026 | Localizer → suggester → fixer; repo-level. |
| 30 ⚠ | [MultiFixer: Coordinator-Proposer Multi-Agent Framework for Multi-Hunk Bugs](https://arxiv.org/abs/2607.26591) | arXiv 2026 | Multi-agent for bugs needing edits in several places. Results not checked. |
