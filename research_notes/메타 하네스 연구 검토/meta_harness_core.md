# Meta-Harness (메타 하네스): the canonical work, method, results, limitations, and the "harness matters" claim

> **How these notes were sourced (read first).** In this environment the egress proxy blocked arxiv.org, alphaxiv.org, huggingface.co, emergentmind.com, yoonholee.com and *.github.io (HTTP 403 at CONNECT). WebFetch failed on every host. Primary material was read in four ways instead:
> 1. **The official code repos**, cloned from GitHub: `stanford-iris-lab/meta-harness` at commit 8123cca (2026-10-01) and `stanford-iris-lab/meta-harness-tbench2-artifact` at commit 57fefdb (2026-03-26).
> 2. **A full zh-CN translation of the arXiv v1 paper**, kept in the GitHub repo `deusyu/harness-engineering` (`works/meta-harness-paper-translation.md`). Its tables 1 and 3–8 are reproduced as text with the original numbers, so I read the numbers directly. Its front matter gives the source as arXiv 2603.28052, published 2026-03-30. Table 2 is only an image in the translation, so its per-dataset numbers come from search snippets.
> 3. **The GitHub source of credible secondary write-ups**: Lilian Weng's blog repo, Jianyu Huang's blog repo, and the `zby/commonplace` knowledge base.
> 4. **WebSearch snippets**, labeled "(snippet)" wherever used.
>
> Every number below cites the arXiv URL as the canonical location. A number marked "via translation" was read from the translation, not from the English PDF.

## Q1. What is the canonical "Meta-Harness" work, and does the term mean more than one thing?

### Takeaway
"Meta-Harness" almost always refers to one Stanford IRIS Lab preprint: **"Meta-Harness: End-to-End Optimization of Model Harnesses"** by Yoonho Lee, Roshen Nair, Qizheng Zhang, Kangwook Lee, Omar Khattab and Chelsea Finn (Stanford, KRAFTON, MIT). It is arXiv:2603.28052 (cs.AI), v1 dated 30 March 2026, with MIT-licensed code at `stanford-iris-lab/meta-harness`. The term also has three secondary uses:
- a generic noun for a "harness that optimizes harnesses", which the paper itself coins;
- the wider 2026 discourse on "harness engineering";
- a Korean-search naming collision with Meta (메타) Platforms' agent products.

The paper dominates because the other uses cite it, name themselves after it, or are unrelated to it.

### Cited Findings
**Identity and metadata**
- Title, authors and arXiv ID are given in the official repo's BibTeX: `@misc{lee2026metaharness…, title={Meta-Harness: End-to-End Optimization of Model Harnesses}, author={Yoonho Lee and Roshen Nair and Qizheng Zhang and Kangwook Lee and Omar Khattab and Chelsea Finn}, year={2026}, eprint={2603.28052}, primaryClass={cs.AI}}`. — [GitHub stanford-iris-lab/meta-harness README](https://github.com/stanford-iris-lab/meta-harness)
- The v1 submission date is 30 March 2026, and the affiliations are Stanford, KRAFTON and MIT. — [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (snippet), consistent with the translation front matter: [deusyu/harness-engineering translation](https://github.com/deusyu/harness-engineering/blob/main/works/meta-harness-paper-translation.md)
- **Venue:** I found only the arXiv preprint. The commonplace KB classifies it as a "Preprint". — [zby/commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)

**Links and artifacts**
- The project page is https://yoonholee.com/meta-harness/ (it has an interactive demo). Slides are at https://yoonholee.com/assets/pdf/meta-harness-slides.pdf and a paper PDF mirror at https://yoonholee.com/meta-harness/paper.pdf. — [repo README badges](https://github.com/stanford-iris-lab/meta-harness); [paper.pdf](https://yoonholee.com/meta-harness/paper.pdf) (snippet; the host was blocked for direct reading)
- The optimized TerminalBench-2 harness is released separately at `stanford-iris-lab/meta-harness-tbench2-artifact`. Its first commit is dated 2026-03-26 with the message "Meta-Harness agent for Terminal-Bench 2.0 (76.4%)". The main code repo's initial commit is dated 2026-04-14. — [tbench2 artifact repo](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact); [meta-harness repo](https://github.com/stanford-iris-lab/meta-harness) (git log)

**Funding**
- The acknowledgements thank "KRAFTON AI for API credits" and say the work is "supported by OpenAI, KFAS, and Schmidt Sciences AI2050". — [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (via translation)

**Problem framing**
- The abstract defines a harness as "the code that determines what information to store, retrieve, and present to the model". It says system performance depends on the harness as well as the weights. It says existing text optimizers "compress feedback too aggressively: they are memoryless, condition only on scalar scores, or restrict feedback to short templates or summaries". — [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (snippet + translation)
- The repo describes Meta-Harness as "a framework for automated search over task-specific model harnesses: the code around a fixed base model that decides what to store, retrieve, and show while the model works." — [repo README](https://github.com/stanford-iris-lab/meta-harness)

**Why it is called "Meta"**
- The paper says Meta-Harness "is itself a harness in the broad sense (hence the name), because it determines what information the proposer model sees during search". — [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (via translation, §3)
- Lilian Weng gives the same reading: "'Meta-' in its name means it is a harness for optimizing harnesses." — [Lil'Log, "Harness Engineering for Self-Improvement", 2026-07-04](https://lilianweng.github.io/posts/2026-07-04-harness/)

**Secondary use 1: a generic label for harness-optimizing loops**
- Several later works use "Meta-Harness" in their titles or names:
  - AutoDesign: "Meta-Harness Optimization for Long-Horizon Agentic Design" — [arXiv 2608.13560](https://arxiv.org/pdf/2608.13560) (snippet)
  - MetaCaster: "Meta-Harness-Optimized Agent…" — [arXiv 2608.23473](https://arxiv.org/pdf/2608.23473) (snippet)
  - "Simple Meta-Harness on Islo.dev", an HN post — [HN 48022596](https://news.ycombinator.com/item?id=48022596) (snippet)
  - `SuperagenticAI/metaharness`, a "Python library and CLI for harness optimization with Codex" — [repo README "Built on Meta-Harness"](https://github.com/stanford-iris-lab/meta-harness)

**Secondary use 2: the wider "harness engineering" discourse**
- The paper's introduction places itself in this discourse and cites:
  - OpenAI, "Harness engineering: leveraging Codex in an agent-first world" (Feb 2026)
  - Anthropic, "Effective harnesses for long-running agents" (Nov 2025)
  - C. Bölük, "I improved 15 LLMs at coding in one afternoon. Only the harness changed." (Feb 2026)
  - B. Böckeler on martinfowler.com, "Harness engineering" (Mar 2026)
  - Sources: [OpenAI](https://openai.com/index/harness-engineering/); [Anthropic](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents); [blog.can.ac](https://blog.can.ac/2026/02/12/the-harness-problem/); [martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html). Dates are as given in the paper's references: [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (via translation)
- Lilian Weng's July 2026 survey charts how the optimized object has progressed: "instruction prompts → structured context → workflow → harness code → optimizer code". She places Meta-Harness after ACE and MCE in this progression. — [Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)

**Secondary use 3: Korean-language naming collisions**
- A Korean search for "메타 하네스" mostly returns Meta Platforms agent news (e.g., the "Muse" personal agent). — [파이낸셜뉴스](https://www.fnnews.com/news/202609090419066714) (snippet)
- A KuCoin headline reads "Meta to launch Harness agent framework". — [KuCoin blog](https://www.kucoin.com/fr/blog/bd-meta-to-launch-harness-agent-framework-continues-open-source-model-releases) (title-only snippet; not verified)
- Korean coverage also discusses a Kakao-affiliated Claude Code "Harness" plugin, described as a "meta-skill" that auto-generates agent teams. — [wikidocs 박재홍의 실리콘밸리](https://wikidocs.net/blog/@jaehong/10292/) (snippet)

### Inferences
- When Korean users say "메타 하네스" for a hot 2026 agent-research topic, they almost certainly mean the Lee et al. paper and its follow-ups. Three things point this way:
  - the repo's "Built on Meta-Harness" list;
  - the many 2026 arXiv follow-ups that benchmark against it (see Q4);
  - Weng's survey treating it as a landmark.
- The Meta Platforms and Kakao results are naming collisions, not alternative research meanings.
- Co-author Qizheng Zhang is also the first author of ACE (Zhang et al. 2025), the main hand-designed baseline beaten in text classification. This follows from the reference list (ref [58], "Q. Zhang, C. Hu, … K. Olukotun") in [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) (via translation). It matters when judging the baseline: ACE was presumably run competently, but the comparison is not independent.
- Omar Khattab's co-authorship links the work to the DSPy and prompt-optimizer lineage. The commonplace KB says the same: [zby/commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)

### Gaps
- I could not read the English PDF or the project page directly. I could not confirm whether an arXiv v2 or later revision changed any numbers.
- No conference venue or acceptance was found as of October 2026.
- I could not verify a per-author affiliation mapping. One secondary source says Kangwook Lee is at MIT, which I could not verify.

## Q2. Method: what is searched, who proposes, what feedback, how candidates are evaluated, budget, and overfitting control

### Takeaway
Meta-Harness is a deliberately minimal outer loop. A coding agent proposes new **single-file Python harness programs**; in the paper this was Claude Code running Opus 4.6. Each harness controls prompting, retrieval, memory and orchestration around a **frozen** base model.

The key design choice is feedback. The proposer is not given a compressed prompt. It gets **filesystem access to every prior candidate's source code, scores and raw execution traces**, up to about 10 million tokens per evaluation. It reads this with grep and cat (a median of 82 files per iteration).

Candidates are evaluated on a search set, and a Pareto frontier is kept. There is no parent-selection rule. Typical runs are about 20 to 40 iterations. Overfitting is controlled by keeping the test set from the proposer, except on TerminalBench-2, where search and final evaluation used the same 89 tasks.

### Cited Findings
**Objective**
- The optimization target is H* = argmax_H E_{x∼X, τ∼p_M(H,x)} r(τ,x). Here M is a fixed LLM, H is a stateful harness program, τ is the rollout and r is a task reward. When there are several objectives, such as accuracy and context cost, candidates are compared under Pareto dominance and the resulting frontier is reported. — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation); also [Jianyu Huang's blog](https://jianyuh.github.io/llm/2026/04/14/Meta-Harness.html)

**What is searched**
- "Each harness is a single-file Python program that modifies task-specific prompting, retrieval, memory, and orchestration logic… The base model M varies by domain and is always frozen." — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (English quote via [commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/))
- Discovered harnesses are "roughly 100–1000 lines of code" each. — [arXiv 2603.28052 App. B](https://arxiv.org/abs/2603.28052) (via translation)

**The proposer**
- "The proposer P is Claude Code with Opus-4.6, guided by a minimal domain-specific skill that describes where to write new harnesses, how to inspect previous harnesses and their execution traces, and what files it can and cannot modify." — [commonplace ingest quoting §3](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)
- The authors say using a coding agent rather than a raw LLM is essential "because accumulated experience quickly exceeds context limits, so the proposer must decide what to inspect and validate edits by interacting with the codebase directly". — [arXiv 2603.28052 §1](https://arxiv.org/abs/2603.28052) (via translation)

**Feedback channel**
- Each evaluated harness gets its own directory containing its source code, scores and execution traces ("prompts, tool calls, model outputs, and state updates"). The proposer queries this with tools such as grep and cat. — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation)
- "A single evaluation can produce up to 10,000,000 tokens of diagnostic information, roughly three orders of magnitude beyond the largest feedback budgets used in prior text-optimization settings." — [arXiv 2603.28052 §1](https://arxiv.org/abs/2603.28052) (via translation)

**Table 1 (MTok of context per iteration, authors' estimates)**

| Method | History | MTok/iter |
| --- | --- | --- |
| OPRO | window | 0.002 |
| TextGrad | latest only | 0.015 |
| AlphaEvolve | window | 0.022 |
| GEPA | summary | 0.008 |
| Feedback Descent | summary | 0.012 |
| TTT-Discover | window | 0.026 |
| Meta-Harness | full | 10.0 |

— [arXiv 2603.28052 Table 1](https://arxiv.org/abs/2603.28052) (via translation)

**How the proposer actually uses the filesystem**
- In the TB2 run (10 iterations, Opus 4.6), the proposer read a **median of 82 files per iteration (range 69–99)**. Of these, 41% were prior harness source, 40% execution traces, 6% score or summary files and 13% other. It typically referenced more than 20 prior candidates per step. — [arXiv 2603.28052 App. A, Table 8](https://arxiv.org/abs/2603.28052) (via translation)

**Search loop (Algorithm 1)**
1. Initialize a population with valid baseline harnesses and evaluate them.
2. For t = 1…N: the proposer queries the filesystem and proposes k new harnesses.
3. Each candidate that passes interface validation is evaluated and logged.
4. Return the Pareto frontier.

"Meta-Harness maintains a population… and a Pareto frontier… but imposes no parent-selection rule." — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation)

**Budget**
- "A typical run evaluates roughly 60 harnesses over 20 iterations." — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation)
- Per domain:
  - Text classification: 20 iterations × 2 candidates = 40 candidates.
  - Math: 40 iterations producing 109 candidate retrieval harnesses.
  - TB2: the qualitative appendix analyzes a 10-iteration run.
  - Source: [arXiv 2603.28052 §4.1, §4.2, App. A](https://arxiv.org/abs/2603.28052) (via translation)

**Separating search from test**
- "The proposer never sees test-set results; its only feedback comes from the search set." The final test evaluation is run on the Pareto frontier. — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation)
- The repo enforces this operationally. "Evolution uses validation results only… Finalization permanently blocks more evolution under that run name. The test data is included in this public repository, so this is operational isolation, not access control." — [text_classification README](https://github.com/stanford-iris-lab/meta-harness/blob/main/reference_examples/text_classification/README.md)

**Overfitting rules in the proposer skill (TB2)**
- The TB2 proposer skill has explicit "Anti-overfitting rules": "No task-specific hints. Do not hardcode knowledge about specific tasks" and "Never mention task names in agent code, prompts, or comments." — [TB2 SKILL.md](https://github.com/stanford-iris-lab/meta-harness/blob/main/reference_examples/terminal_bench_2/.claude/skills/meta-harness-terminal-bench-2/SKILL.md)
- A later "experimental/harbor_meta_harness" pilot (July 2026) adds per-task `forbidden_references` leakage checks. It also adds a universal denylist covering `/tests`, `verifier`, `/solution`, `task.toml` and `test_outputs`. — [harbor_meta_harness README](https://github.com/stanford-iris-lab/meta-harness/blob/main/experimental/harbor_meta_harness/README.md)

**Why search in code space**
- The authors argue that representing harnesses as programs "provides a natural regularization bias: coding models tend to propose coherent algorithms rather than brittle hard-coded solutions". — [arXiv 2603.28052 §3](https://arxiv.org/abs/2603.28052) (via translation)

**Practical guidance (Appendix D)**
- The skill text is "the strongest lever"; in their experience, "iterating on the skill text had a larger effect on search quality than changing the number of iterations or population size". They suggest a few short evolution runs of 3–5 iterations to debug the skill first.
- Use a search set that is hard for the baseline, sized for about 50 full evaluations per run. This was 50–100 examples for classification and 88 problems for math retrieval.
- Log in JSON, add a small query CLI, run cheap interface validation before full evaluation, and keep evaluation outside the proposer.
- Source: [arXiv 2603.28052 App. D](https://arxiv.org/abs/2603.28052) (via translation)

**How to use it on a new domain**
- The repo has the user point a coding assistant at `ONBOARDING.md` to produce a `domain_spec.md`. The onboarding rules say "Keep final test data and results outside its accessible workspace" and "Start with a few iterations to check proposal quality and cost before committing to a larger budget." — [ONBOARDING.md](https://github.com/stanford-iris-lab/meta-harness/blob/main/ONBOARDING.md)
- The examples use Claude Code as the proposer. Other proposers can be used by adapting `claude_wrapper.py`, which "must log proposer interactions". — [repo README](https://github.com/stanford-iris-lab/meta-harness)

**Secondary descriptions**
- Weng summarizes the design: the "proposer… is itself a coding agent and the final output is a collection of harness candidates on the Pareto frontier… The entire execution history is accessible via a file system." — [Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)
- A code-grounded review describes the release's candidate-handling contracts. Text-classification candidates are `MemorySystem` subclasses implementing `predict`, `learn_from_batch`, `get_state` and `set_state`. Proposers write a `pending_eval.json` manifest. Candidates are import-checked and smoke-tested before benchmarking. — [zby/commonplace review](https://github.com/zby/commonplace/blob/main/kb/agent-memory-systems/reviews/meta-harness.md)

### Inferences
- The method's novelty is less "LLM-driven program search", which ADAS, AFlow and AlphaEvolve already do, and more **the interface**. It is an unstructured, agentic, full-history filesystem in place of hand-designed archives, mutation operators or summaries. The authors bet that proposer capability will grow, so they put the intelligence in the proposer rather than in the search scaffolding. Weng's framing and the commonplace review read it the same way.
- In TB2 the proposer can add code freely, and the main overfitting control is a rule in a prompt (the skill), plus post-hoc regex and manual audits. This is a soft control, not a structural guarantee.

### Gaps
- I could not see the exact number of TB2 search iterations behind the final 76.4% harness (the appendix analyzes a 10-iteration run), nor how many candidates were evaluated in total.
- The paper text I read gives no dollar cost for proposer tokens. The repo gives TB2 evaluation cost only (see Q3).

## Q3. Results: benchmarks, baselines, numbers, compute and cost, cross-model transfer

### Takeaway
Three domains were tested:
1. **Online text classification** with GPT-OSS-120B. The best harness reached **48.6%** test accuracy, against 40.9% for ACE and 40.0% for MCE. That is **+7.7 points over ACE with about 4× fewer context tokens** (11.4K vs 50.8K). Meta-Harness matched OpenEvolve and TTT-Discover's final search-set accuracy in about 10× fewer evaluations and ended more than 10 points higher. It generalized to 9 unseen datasets (73.1% vs ACE 70.2%).
2. **Retrieval-augmented IMO-level math.** One discovered BM25-routing harness raised average accuracy by **+4.7 points over no retrieval across five models**: GPT-OSS-20B, which was used for selection, plus four models never seen in search. It beat plain BM25 by 1.3 points.
3. **TerminalBench-2** (89 tasks). It scored **76.4%** with Opus 4.6, #2 among Opus 4.6 agents behind ForgeCode's 81.8%, and **37.6%** with Haiku 4.5, #1 among Haiku agents.

Search was relatively cheap for classification ("a few hours"). TB2 is expensive: about **$500 and 4–6 hours per search iteration** in the release configuration.

### Cited Findings
**Online text classification: setup**
- Base model: GPT-OSS-120B.
- Datasets: LawBench (215 classes), Symptom2Disease (22 classes) and USPTO-50k (180 classes).
- The search population was initialized with zero-shot, few-shot, ACE and MCE.
- Source: [arXiv 2603.28052 §4.1](https://arxiv.org/abs/2603.28052) (via translation)
- The paper used a local vLLM deployment of gpt-oss-120b, MXFP4-quantized, with max-model-len 32768. The repo warns that "API-backed runs may perform differently from that setup." — [text_classification README](https://github.com/stanford-iris-lab/meta-harness/blob/main/reference_examples/text_classification/README.md)

**Online text classification: test results (Table 2)**
- The selected harness "achieves 48.6% accuracy, outperforming ACE by 7.7 points and MCE by 8.6 points… Meta-Harness uses only 11.4K context tokens vs. 50.8K for ACE and 28.5K for MCE." — [arXiv 2603.28052 §4.1](https://arxiv.org/abs/2603.28052) (via translation)
- Per-dataset values (snippet of Table 2):

| Harness | USPTO | S2D | Law | Avg | Ctx column |
| --- | --- | --- | --- | --- | --- |
| ACE | 16.0 | 77.8 | 29.0 | 40.9 | 203.0 |
| MCE | 14.0 | 83.0 | 23.0 | 40.0 | 114.0 |
| Meta-Harness | 14.0 | 86.8 | 45.0 | 48.6 | 45.5 |

  Gains concentrate on LawBench (+16) and S2D (+9); USPTO does not improve. — [arXiv 2603.28052](https://arxiv.org/html/2603.28052v1) (snippet)
- The discovered harnesses need no extra LLM calls beyond the main task call. — [arXiv 2603.28052](https://arxiv.org/html/2603.28052v1) (snippet)

**Online text classification: the best discovered harness**
- "Label-Primed Query" (`label_primed_query_anchored.py`) makes one large call built from three parts: a label primer listing all valid labels, a coverage block with one query-relevant example per class, and query-anchored contrastive pairs (similar examples with different labels). Retrieval uses TF-IDF. — [arXiv 2603.28052 App. B.1](https://arxiv.org/abs/2603.28052) (via translation); [Jianyu Huang's blog](https://jianyuh.github.io/llm/2026/04/14/Meta-Harness.html)
- A lower-context frontier point, "Draft Verification", uses two short calls. It tests a draft guess against retrieved counterexamples. — [arXiv 2603.28052 App. B.1](https://arxiv.org/abs/2603.28052) (via translation)

**Online text classification: comparison with text optimizers (search set, Table 4)**
- Each method got the same proposer (Opus 4.6, max reasoning) and the same budget of candidate evaluations. Selection used only the search set.

| Method | Median | Best |
| --- | --- | --- |
| GEPA | 32.6 | 40.2 |
| Best-of-N | 34.0 | 44.2 |
| OpenEvolve | 39.1 | 43.3 |
| TTT-Discover | 34.1 | 45.6 |
| Meta-Harness | 50.0 | 56.7 |

- "Meta-Harness matches the best prior text optimizers (OpenEvolve, TTT-Discover) with 10× fewer full evaluations, and its final accuracy surpasses theirs by more than 10 points."
- Figure 1 says it reached the next-best method's final accuracy within 4 evaluations, where that method took 60 proposals.
- Source for the three items above: [arXiv 2603.28052 §4.1, Table 4, Fig. 1/4](https://arxiv.org/abs/2603.28052) (via translation)

**Online text classification: ablation of what the proposer sees (Table 3, search set)**

| Proposer sees | Median | Best | Runs above zero-shot |
| --- | --- | --- | --- |
| Scores + code only | 34.6 | 41.3 | 26 |
| Scores + code + LLM summaries | 34.9 | 38.7 | 23 |
| Full interface with raw traces | 50.0 | 56.7 | 39 |

- "Summaries do not recover the missing signal, and may even hurt by compressing away diagnostically useful details." The median full-interface candidate beats the best candidate from either ablation. — [arXiv 2603.28052 §4.1, Table 3](https://arxiv.org/abs/2603.28052) (via translation); English quotes in [commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)
- One secondary video summary says traces "double" median accuracy. That is an overstatement: 50.0/34.6 ≈ 1.45×. — [Emergent Mind video](https://www.emergentmind.com/videos/meta-harness-end-to-end-harness-optimization-f660476a) (snippet); my arithmetic

**Online text classification: out-of-distribution test (Table 5)**
- Nine datasets unseen in search: SciC, FiNER, Amz5, FPB, GoEmo, Bank77, News, SciT and TwHate.

| Harness | Average accuracy | Extra context |
| --- | --- | --- |
| Meta-Harness | 73.1 | 7.3K |
| ACE | 70.2 | 11.7K |
| Few-shot (32) | 69.6 | 5.2K |
| Few-shot (8) | 68.9 | 2.2K |
| Few-shot (all) | 68.2 | 7.4K |
| Zero-shot | 67.0 | – |

- Meta-Harness is best on 6/9 datasets. Notably, going beyond 32 few-shot examples hurt on 7/9 tasks. — [arXiv 2603.28052 §4.1, Table 5](https://arxiv.org/abs/2603.28052) (via translation)

**Retrieval-augmented math: setup**
- The retrieval corpus has at least 500,000 solved problems from 8 open datasets. It was deduplicated and decontaminated against the evaluation and search sets.
- Search set: 250 Olympiad-level problems (OlympiadBench + Omni-MATH hard), over 40 iterations producing 109 candidates.
- The search population was initialized with zero-shot, few-shot and ACE. The harness was selected on GPT-OSS-20B search-set performance.
- Test set: 200 unseen IMO-level problems from IMO-AnswerBench, IMO-ProofBench and ArXivMath. Each problem was sampled 3 times and pass@1 averaged.
- Source: [arXiv 2603.28052 §4.2](https://arxiv.org/abs/2603.28052) (via translation)

**Retrieval-augmented math: results (Table 6, average pass@1 across five models)**

| Retrieval method | Average | Change vs no retrieval |
| --- | --- | --- |
| No retrieval | 34.1 | – |
| Dense, k=1 | 34.4 | +0.3 |
| Dense, k=5 | 38.1 | +4.0 |
| Random few-shot | 32.2 | −1.9 |
| BM25 | 37.5 | +3.4 |
| Meta-Harness | 38.8 | +4.7 |

- Per model, Meta-Harness scored 31.7 (GPT-5.4-nano), 30.4 (GPT-5.4-mini), 34.9 (Gemini-3.1-Flash-Lite), 46.3 (Gemini-3-Flash) and 50.6 (GPT-OSS-20B). It improved over no retrieval on all five.
- On Gemini-3-Flash it scored slightly below BM25 (46.3 vs 46.6) and below Dense k=5 (47.2). Dense k=5 also beat it on Gemini-3.1-Flash-Lite (37.1 vs 34.9).
- Source: [arXiv 2603.28052 Table 6](https://arxiv.org/abs/2603.28052) (via translation)
- The discovered program is a four-route lexical router (Combinatorics, Geometry, Number Theory, Default) using BM25 with a math-aware tokenizer. Combinatorics fetches 20 candidates, deduplicates to 8, reranks and keeps 3. Geometry returns 1 hard NuminaMath reference plus 2 raw BM25 neighbors. The program "merged two successful search lineages". — [arXiv 2603.28052 App. B.2](https://arxiv.org/abs/2603.28052) (via translation)

**TerminalBench-2: setup and results (Table 7)**
- Search was initialized from Terminus 2 and Terminus-KIRA (KRAFTON AI). Search and final evaluation were both run on the same 89 tasks. — [arXiv 2603.28052 §4.3](https://arxiv.org/abs/2603.28052) (via translation)
- Opus 4.6 pass rates:

| Harness | Pass rate (%) |
| --- | --- |
| Claude Code | 58.0 |
| Terminus 2 | 62.9 |
| Mux | 66.5 |
| Droid | 69.9 |
| TongAgents | 71.9 |
| MAYA-V2 | 72.1 |
| Terminus-KIRA | 74.7 |
| Capy | 75.3 |
| **Meta-Harness** | **76.4** |
| ForgeCode | 81.8 |

- Haiku 4.5 pass rates:

| Harness | Pass rate (%) |
| --- | --- |
| OpenHands | 13.9 |
| Claude Code | 27.5 |
| Terminus 2 | 28.3 |
| Mini-SWE-Agent | 29.8 |
| Terminus-KIRA | 33.7 |
| Goose | 35.5 |
| **Meta-Harness** | **37.6** |

- The other harnesses' results are taken from the official leaderboard. — [arXiv 2603.28052 Table 7](https://arxiv.org/abs/2603.28052) (via translation)
- On ForgeCode, the authors say "we were unable to reproduce its reported result from publicly available code alone, suggesting its leaderboard score relies on components beyond the released repository." — [arXiv 2603.28052 §4.3](https://arxiv.org/abs/2603.28052) (via translation)
- The artifact README gives the protocol as "76.4% on Terminal-Bench 2.0 (89 tasks × 5 trials, Claude Opus 4.6)". By difficulty: Easy (4 tasks) 100.0, Medium (55) 81.1, Hard (30) 64.7. — [tbench2 artifact README](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact)

**TerminalBench-2: what was discovered**
- The main change is "environment bootstrapping". Before the agent loop starts, one compound shell command (15-second timeout, fails silently) snapshots the working directory, the /app listing, available languages (Python, GCC/G++, Node, Java, Rust, Go), package managers (pip, apt-get) and memory. The snapshot is injected into the first prompt.
- The authors estimate this saves 2–4 exploratory turns. It is about 80 lines added to Terminus-KIRA.
- It improved 7 of 89 tasks over KIRA, mostly tasks needing domain toolchains (e.g., protein-assembly, path-tracing).
- The proposer's logged hypothesis was that the snapshot "will reduce wasted exploration episodes by 3–5 turns on dependency-heavy tasks."
- Source: [arXiv 2603.28052 App. B.3](https://arxiv.org/abs/2603.28052) (via translation); [tbench2 artifact README](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact) ("saves 2-5 early exploration turns")

**TerminalBench-2: how the proposer reasoned**
- In early iterations the proposer bundled structural fixes with prompt-template edits, and both candidates regressed. It then hypothesized that the shared prompt change was a confound, isolated the structural fix, and finally pivoted to a purely additive change, which became the best candidate. — [arXiv 2603.28052 §4.3, App. A.2](https://arxiv.org/abs/2603.28052) (via translation)

**Compute and cost**
- The paper says "a single search run completes in a few hours of wall-clock time." — [arXiv 2603.28052 §5](https://arxiv.org/abs/2603.28052) (via translation)
- For TB2 the repo says: "With Opus 4.6 and a high-tier API key, the default 89x2 search run at concurrency 50 takes about 4-6 hours and costs roughly $500 per iteration." The default "paper-style config" is Opus 4.6, the full 89 tasks, 2 search trials, concurrency 50. A 30-task "hard" subset is suggested for cheaper validation. — [TB2 reference README](https://github.com/stanford-iris-lab/meta-harness/blob/main/reference_examples/terminal_bench_2/README.md)
- The commonplace KB notes the paper gives no token or API cost analysis. It estimates proposer consumption at about 200M tokens per run (10 MTok × about 20 iterations); this is its own estimate. — [commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)

**Transfer across models**
- Model transfer was tested only in math, where one harness transferred to four unseen models from two families (GPT-5.4, Gemini-3/3.1). The authors claim the harnesses are "readable, transferable strategies that can be reused across models, including future, stronger ones". — [arXiv 2603.28052 §4.2, §5](https://arxiv.org/abs/2603.28052) (via translation)
- For TB2, a separate Haiku 4.5 result is reported, but I found no statement on whether it is the same harness as the Opus one or a separate search. A later paper describes the TB2 Haiku comparator as "a Claude Opus 4.6 proposer with a Haiku 4.5 base agent". — [commonplace note on arXiv 2607.19592](https://github.com/zby/commonplace/blob/main/kb/sources/knowledge-centric-self-improvement-2607.19592.ingest.md)

### Inferences
- **Unit discrepancy in the context column.** The snippet's Table 2 context values (203.0 / 114.0 / 45.5) are almost exactly 4× the in-text token numbers (50.8K / 28.5K / 11.4K). The likely explanation is that the table reports characters or another unit while the text reports tokens; the repo measures `memory_context_chars`. This is my inference and is unverified. Either way, the "4× fewer" ratio holds in both units.
- **Search-set vs test-set numbers.** The 50.0/56.7 ablation and optimizer figures (Tables 3–4) are search-set numbers. The 48.6% headline is a test-set number (Table 2). Secondary write-ups sometimes mix them.
- **The math gain is modest.** Against the strongest simple baseline the gain is +1.3 points over BM25. Model-specific results are mixed against dense k=5.
- **TB2 gains are small.** On TB2 the improvement over the starting harness is +1.7 points (Opus: 76.4 vs KIRA 74.7) and +3.9 (Haiku: 37.6 vs KIRA 33.7). With 89 tasks × 5 trials, a gap of about 1.7 points is plausibly within run-to-run noise. No confidence intervals were reported in what I read.
- **TB2 total cost (inference).** At the release config (about $500 and 4–6 hours per iteration), a 10-iteration TB2 search would cost on the order of $5,000 and 40–60 hours of evaluation. That is much more than "a few hours", so that phrase plausibly applies to the cheaper classification and math runs. This is my inference from the repo numbers, not a stated figure.

### Gaps
- I could not read the zero-shot and few-shot rows of the in-distribution Table 2. They are only in an image I could not access.
- I found no confidence intervals or seed variance for TB2 or Table 2.
- I found no proposer token or dollar costs for the classification or math runs.
- I found no comparison against ADAS/AFlow-style agent-design search, or against DSPy optimizers other than GEPA, in the paper's experiments. GEPA appears only in the Table 4 search-set comparison.

## Q4. Stated limitations, criticisms, replications, follow-ups and reception

### Takeaway
**Authors' own limitations:**
- Only one (very strong) proposer was tested.
- On TB2, search and evaluation used the same benchmark, defended as a "discovery problem" with regex and manual leakage audits, and the resulting harness is specialized to TB2.
- Co-evolving harness and weights is left as future work.

**Third-party criticisms:**
- The trace-access ablation covers only one domain.
- The work is limited to hard-oracle domains.
- Cost is not reported.
- There is a risk of adaptive overfitting.

**Follow-ups and reception:** a large follow-up literature appeared from April to October 2026, including Google's RRSI, KRAFTON's WHALE, HarnessCompass, "Bad Genius" and ModularRSI. Some of these show Meta-Harness overfitting the search split or transferring poorly. Reception was strongest via X, Reddit and blogs, including a Lilian Weng survey. Hacker News engagement with the paper itself was minimal.

### Cited Findings
**Limitations stated by the authors**
- On TB2: "we perform search and final evaluation on the same 89-task benchmark. We use the benchmark as a discovery problem… this is standard practice… the benchmark is small and expensive to evaluate, and introducing a separate split would materially weaken the search signal. We also check for overfitting by manual inspection and regex-based audits for task-specific string leakage." They also note "the resulting harness is specialized to the TerminalBench-2 regime." — [arXiv 2603.28052 §4.3](https://arxiv.org/abs/2603.28052) (snippet + translation)
- On the proposer: "our experiments show that harness search can work with one particularly strong coding-agent proposer (Claude Code); studying more broadly how the effect varies with the proposer agent remains future work." — [arXiv 2603.28052 §5](https://arxiv.org/abs/2603.28052) (via translation)
- Future work: "co-evolving the harness and the model weights". — [arXiv 2603.28052 §5](https://arxiv.org/abs/2603.28052) (via translation)
- The authors argue that overfitting in code space "is more inspectable: brittle if-chains or hard-coded class mappings are visible on inspection in a way that weight-space overfitting is not." — [arXiv 2603.28052 §5](https://arxiv.org/abs/2603.28052) (snippet + translation)
- The repo's release note says: "This is a cleaned-up version of the code we used for the paper. It has not been tested beyond verifying that it runs." — [repo README](https://github.com/stanford-iris-lab/meta-harness)

**Criticisms in secondary analyses**
- The commonplace KB (an independent analysis written from reading the paper) lists:
  - "Ablation coverage is narrow": the trace ablation was run only on text classification.
  - The proposer is "a single, highly capable system".
  - "Hard-oracle domains only".
  - "No cost analysis".
  - "Overfitting risk is acknowledged but not tested" for agentic coding.
  - "Comparison baselines are uneven": the math baselines are only retrieval methods, and TB2 compares only against hand-engineered harnesses, not other automated search.
  - Source: [zby/commonplace ingest](https://zby.github.io/commonplace/sources/meta-harness-end-to-end-optimization-of-model-harnesses/)
- Lilian Weng cautions that "the search in the TerminalBench-2 experiment is initialized from Terminus-KIRA and Terminus-2, two very strong harnesses." Her general future-challenges section names reward hacking: "if it comes from benchmark scores, it may exploit benchmark artifacts". It argues the evaluator should "sit outside the loop that evolves harness, with held-out tests, trace audits, and human review." — [Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)

**Follow-ups that test Meta-Harness's generalization (mostly snippet-level)**
- **RRSI (Google; arXiv 2609.24972, Sept 2026)** argues that ordinary harness evolution is "vulnerable to adaptive overfitting", because one finite evolution set is reused for feedback, proposals and selection. It adds sparse edit budgets plus a critic and a pruner.
  - In its Table 1 (Harvey LAB plus out-of-distribution sets JobBench, GDPval and APEX-Agents), Meta-Harness scores 93.0 on the evolve split vs RRSI's 90.5. On OOD, Meta-Harness gets 37.1 / 49.1 / 35.7 vs RRSI's 40.7 / 52.3 / 37.9.
  - One reported OOD average is 40.6 for Meta-Harness, 43.6 for RRSI and 39.7 for the starting harness.
  - The abstract and v1 HTML give different headline numbers.
  - Source: [arXiv 2609.24972](https://arxiv.org/abs/2609.24972) (snippet). The Meta-Harness repo lists RRSI as a follow-up: [repo README](https://github.com/stanford-iris-lab/meta-harness)
- **"Do Agent Optimizers Compound?" (arXiv 2607.14004)** gave GEPA, Meta Harness and RELAI-VCL 200 rollouts each on 12 hard TB2 tasks, then tested transfer to a 22-task union.

| Agent | Phase 1 | Transfer | Re-optimization | Lifelong average |
| --- | --- | --- | --- | --- |
| Baseline | 62.5 | 56.8 | 56.8 | 58.7 |
| GEPA | 70.8 | 54.5 | 72.7 | 66.0 |
| Meta Harness | 66.6 | 68.2 | 59.1 | 64.6 |
| RELAI-VCL | 79.2 | 72.7 | 77.3 | 76.4 |

  This is quoted in [zby/commonplace note](https://github.com/zby/commonplace/blob/main/kb/sources/agent-optimizers-compound-terminal-bench.ingest.md) (original: [arXiv 2607.14004](https://arxiv.org/html/2607.14004v1)). The authors of that paper have a competing method (RELAI-VCL).
- **WHALE (KRAFTON; arXiv 2609.00196)** alternates rejection-sampling fine-tuning with Meta-Harness search on Qwen3.5-2B/4B. It reports beating the stronger single-component baseline by 7.67–10.05 points. This is the authors' stated future direction, realized. — [commonplace note](https://github.com/zby/commonplace/blob/main/kb/sources/whale-joint-harness-weight-optimization.ingest.md); [arXiv 2609.00196](https://arxiv.org/abs/2609.00196)
- **ModularRSI (arXiv 2609.14857)** compares against AHE and Meta-Harness given 16 epochs, and favors itself. — [commonplace note](https://github.com/zby/commonplace/blob/main/kb/sources/modularrsi-generalizable-harness-self-improvement.ingest.md)
- **Knowledge-centric self-improvement (arXiv 2607.19592)** reports 43.8% ± 3.4 on TB2 with Haiku 4.5, above the 37.6% Meta-Harness comparator. — [commonplace note](https://github.com/zby/commonplace/blob/main/kb/sources/knowledge-centric-self-improvement-2607.19592.ingest.md)
- **Other critique and extension papers, known by title or snippet only:**
  - HarnessCompass, which adds a gate rejecting edits that mention specific task instances: [arXiv 2608.01918](https://arxiv.org/pdf/2608.01918)
  - "Bad Genius: Counterfactual-Guided Harness Evolution Beyond Task-Specific Shortcuts", which argues task holdouts miss benchmark-wide shortcuts: [arXiv 2609.18366](https://arxiv.org/pdf/2609.18366)
  - "Rethinking the Evaluation of Harness Evolution for Agents": [arXiv 2607.12227](https://arxiv.org/html/2607.12227v1)
  - "Automated Discovery Has No Universally Superior Harness": [arXiv 2607.18235](https://arxiv.org/pdf/2607.18235)
  - Harness-R1, which uses RL to learn the editing policy: [arXiv 2608.02276](https://arxiv.org/pdf/2608.02276)
  - All are snippets only.
- **Projects and papers built on Meta-Harness, as listed in the official repo:**
  - "Don't Train the Model, Evolve the Harness", applied to Harvey's Legal Agent Benchmark
  - SuperagenticAI/metaharness (Codex-based)
  - Harness Forge, a Claude Code skill
  - dkhanal/meta-harness
  - meta-harness-on-islo
  - Tencent VideoHarness-RSI
  - RRSI, WHALE, AutoRef, MetaBench-Harness, and Mixture of Self-Improving Branches
  - Source: [repo README "Built on Meta-Harness"](https://github.com/stanford-iris-lab/meta-harness)
- **Domains with reported improvements, per the repo's onboarding:**
  - classification and math
  - coding (Meta-Harness, RHO arXiv 2606.05922, RRSI)
  - visual generation (AutoRef, AutoDesign)
  - legal work (held-out Harvey LAB, transferring to JobBench, GDPval and APEX-Agents via RRSI)
  - engineering design (Frontier-Eng via RRSI)
  - long-video QA (VideoHarness-RSI)
  - Source: [ONBOARDING.md](https://github.com/stanford-iris-lab/meta-harness/blob/main/ONBOARDING.md)

**Reception**
- An X post by Lior Alexander popularized the "6x" framing: "Changing just this layer can create a 6x performance gap on the same model. It's called Meta-Harness." — [X/@LiorOnAI](https://x.com/LiorOnAI/status/2038669301541228606) (snippet)
- A Reddit r/singularity thread on Meta-Harness's TB2 result reportedly had 286 upvotes and 57 comments, focused on "what a harness is" and whether AI-designed harnesses beat manual iteration. — [marvin-42 insights](https://insights.marvin-42.com/articles/rsingularity-debates-meta-harness-after-its-terminalbench-2-lead-over-claude-code) (snippet; aggregator)
- On Hacker News the arXiv submission reportedly drew "3 points, 0 comments". A related "Simple Meta-Harness on Islo.dev" thread drew comments criticizing vague, LLM-sounding writing. — [HN 48022596](https://news.ycombinator.com/item?id=48022596) (snippet)
- Other coverage includes DAIR.AI Academy, Hugging Face community blogs, Maxim AI, Softmax Data and Jianyu Huang's blog. — [DAIR.AI](https://academy.dair.ai/papers/meta-harness); [HF blog Svngoku](https://huggingface.co/blog/Svngoku/meta-harness-end-to-end-optimization-of-model); [getmaxim.ai](https://www.getmaxim.ai/blog/meta-harness-what-if-we-let-an-agent-optimize-the-code-around-an-llm/); [softmaxdata](https://softmaxdata.com/blog/a-new-harness-in-town-meta-harness/); [jianyuh.github.io](https://jianyuh.github.io/llm/2026/04/14/Meta-Harness.html) (mostly snippets; Huang's post read in full)
- Lilian Weng's July 2026 survey uses Meta-Harness as a central example. Her conclusion: "once harness design becomes an executable search space, a strong coding agent can exploit the same design space human engineers use." — [Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)

### Inferences
- **The main open criticism is generalization under adaptive reuse of the evaluation set.** RRSI's numbers show the pattern: Meta-Harness is best on the split it evolves on, but adds less than 1 point out of distribution in that setting. "Agent Optimizers Compound" shows the opposite pattern on TB2 subsets: good transfer, weak re-optimization. So the evidence on generalization is mixed and setting-dependent. Most of these papers propose competing methods and have an incentive to show Meta-Harness's weaknesses.
- **Momentum.** By October 2026, Meta-Harness has become the standard baseline and starting point for "harness evolution" papers. That status, more than its own TB2 rank (which later work has surpassed), is why it is a "hot topic".

### Gaps
- I found no independent replication of the paper's exact headline numbers (48.6%, +4.7, 76.4%) by a third party.
- I could not read the full Reddit, X or HN threads; the reception claims above rely on snippets and aggregators.
- I could not check whether the authors published a response to RRSI or the other overfitting critiques, or a revised version.

## Q5. Is the harness claimed to be the dominant factor in agent performance? Figures and quotes

### Takeaway
The paper's opening claim is that "changing the harness around a fixed LLM can produce a **6× performance gap on the same benchmark**." That figure is **cited from another paper (SWE-bench Mobile, Tian et al. 2026)**, not measured by Meta-Harness, and secondary media often present it as a Meta-Harness finding. The paper says harnesses matter "often as much as the model itself", not that they always dominate.

The paper's own TB2 table does show large same-model spreads:
- 58.0% to 81.8% on Opus 4.6
- 13.9% to 37.6% on Haiku 4.5, about 2.7×

The model gap is still larger than any harness gap: the best Haiku harness (37.6%) is far below the worst Opus harness (58.0%).

### Cited Findings
**The 6× claim and its source**
- Intro, first sentence: "Changing the harness around a fixed large language model (LLM) can produce a 6× performance gap on the same benchmark [46]. The harness… often matters as much as the model itself." — [arXiv 2603.28052 §1](https://arxiv.org/abs/2603.28052) (via translation; the English "6×… same benchmark" wording is confirmed by [Jianyu Huang's blog](https://jianyuh.github.io/llm/2026/04/14/Meta-Harness.html) and search snippets)
- Reference [46] is "M. Tian, Z. Wang, B. Yang, … J. You (2026) SWE-bench Mobile: can large language model agents develop industry-level mobile applications?" — [arXiv 2603.28052 references](https://arxiv.org/abs/2603.28052) (via translation)
- Secondary outlets present 6× as Meta-Harness's own result, for example "Stanford + MIT: Meta-Harness Optimization Boosts LLM Performance Up to 6x" and "The 6x Gap Lives in Your Code, Not Your Model". — [ypyl.github.io](https://ypyl.github.io/news/2026/09/13/stanford-mit-meta-harness-optimization-boosts-llm-performance/); [tandemly.ai](https://tandemly.ai/research/meta-harness-optimization) (snippets)

**Same-model spreads in the paper's own data (Table 7)**
- Opus 4.6: Claude Code 58.0, Terminus 2 62.9, Terminus-KIRA 74.7, Meta-Harness 76.4, ForgeCode 81.8.
- Haiku 4.5: OpenHands 13.9, Claude Code 27.5, Terminus-KIRA 33.7, Meta-Harness 37.6.
- "Prior work has shown that the choice of agent harness has a major effect on performance on this benchmark." — [arXiv 2603.28052 §4.3, Table 7](https://arxiv.org/abs/2603.28052) (via translation)

**Other harness-sensitivity evidence**
- Can Bölük's Feb 2026 post (cited by the paper) argues the edit tool alone is a bottleneck. A snippet attributes "Grok Code Fast 1 from 6.7% to 68.3%" and "hashline beat patch for 14 of 16 models" to hashline editing, but the search summary could not confirm these numbers come from Bölük's own post. — [blog.can.ac](https://blog.can.ac/2026/02/12/the-harness-problem) (snippet; author-run, not independent)
- In the paper's out-of-distribution classification results, naive context stuffing hurts: going beyond 32 few-shot examples lowered accuracy on 7/9 datasets. — [arXiv 2603.28052 §4.1](https://arxiv.org/abs/2603.28052) (via translation)
- A counter-signal: "It's Not the Capability: Harness Sensitivity Is Non-Monotone Across LLM Agent Tiers" reportedly finds heavier harnesses mainly caused formatting breakdowns in capable models. — [arXiv 2605.26731](https://arxiv.org/pdf/2605.26731) (snippet only)
- Weng's own view: "It is hard to forecast how much the future of RSI will rely on harness engineering… Eventually it is possible that many harness improvements will be internalized into core model behavior, but the interface with external context and tools should remain." — [Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)
- Korean community figures appear only secondhand:
  - Kakao "Harness" plugin: 49.5 vs 79.3 quality score across 15 software tasks, reported in a Threads post.
  - A blog's GAIA comparison: 30.91% (minimal harness) vs 74.55% (production harness).
  - Source: [wikidocs](https://wikidocs.net/blog/@jaehong/10292/) / search summary (low reliability; author-reported, not peer-reviewed)

### Inferences
- **Arithmetic from Table 7 (my calculation).** Swapping harnesses on a fixed model moves TB2 by up to 23.8 points on Opus 4.6 (58.0 → 81.8) and 23.7 points on Haiku 4.5 (13.9 → 37.6). Swapping the model on a fixed harness moves it by about 41 points (Terminus-KIRA 33.7 → 74.7; Claude Code 27.5 → 58.0). So on TB2 the model still matters more than the harness. The defensible claim is "the harness is a first-order factor comparable to a model generation", not "the harness dominates the model".
- **Correct attribution of 6×.** The 6× figure belongs to SWE-bench Mobile's measurements. Meta-Harness's own measured gains from automated search are much smaller: +7.7 points on classification, +4.7 on math, +1.7 and +3.9 on TB2.

### Gaps
- I did not read SWE-bench Mobile itself. I could not verify which models and harnesses produce the 6× gap, or whether it comes from a near-zero baseline, which would inflate a ratio.
- I found no systematic, controlled harness-vs-model variance decomposition across benchmarks in the sources I could access.
