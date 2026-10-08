# Applicability of meta-harness-style automated optimization to the jokate game-dev Claude Code harness: optimizable surface, eval adequacy, pilot design, risks

Source-access note for the report writer. The egress policy blocked direct fetches of arxiv.org, alphaxiv, huggingface.co, yoonholee.com, sakana.ai, semanticscholar and github.com HTML pages. Only raw.githubusercontent.com and anthropic.com could be read directly. Each external finding is tagged with how it was obtained:
- **[primary-read]**: I read the primary text myself. This covers the Meta-Harness GitHub README, ONBOARDING.md and reference-example READMEs, the RRSI README, the GEPA README, the SWE-agent ACI doc, the DGM README, and three Anthropic engineering/research posts.
- **[primary-snippet]**: the abstract or excerpts of the primary paper as returned by web search. Numbers are quoted as the search tool reported them.
- **[secondary]**: a third-party summary or blog. Treat with caution.

Repo facts cite `path:line` in `/home/user/jokate-harness`. I read the repository and did not modify it. Lines labelled "Inference" are my reasoning, not something a source states.

---

## Q1. What exact signals do run_evals.py and cost_ab.py produce, how many cases exist, and how noisy are the results?

### Takeaway
There are two eval suites.
- **`run_evals.py`** has 9 behavioral cases with 28 checks. Every check is a regex or a set membership test over the tool-call log and the final answer. Each case runs once per round at about $0.85 per case. The suite has been saturated at 25/25 and 14/14 since round 3. It has caught real grader errors in both directions.
- **`cost_ab.py`** has 6 + 8 synthetic code-navigation tasks scored against compiler ground truth (recall and precision), plus cost, tokens, turns and tool calls. It runs at about $0.05–0.08 per Sonnet session. Opus was run with 1 repetition, and its numbers swung about 40% between rounds on an unchanged arm.

The cost A/B is a usable optimization objective for a narrow surface. The behavioral suite is not one.

### Cited Findings
**run_evals.py: what it measures**
- Each case gets a fresh headless `claude -p <prompt> --output-format stream-json --verbose` session, and all cases run in parallel (`skills/game-bootstrap/evals/run_evals.py:56-60`, `:126-127`).
- `parse()` extracts five things from the stream-json log: the list of Skill names invoked, the shell command strings (Bash/PowerShell), all tool names, the final `result` text, and `total_cost_usd` plus `num_turns` from the result event (`run_evals.py:64-82`). It does **not** extract token counts, tool-result sizes, or per-call errors.
- There are six check types: `skill`, `skill_any`, `tool_re` (regex on tool name), `bash_re` (regex on shell command text), `final_re` and `final_not_re` (regex on the final answer) (`run_evals.py:7-8`, `:85-104`).
- Output is a per-case pass count, the skills called, turns, cost, a ✅/❌ list per check, and a total. The process exits 0 only if every check passes (`run_evals.py:131-147`). There is no repeat or trials option, no variance, and no confidence interval.
- The docstring estimates "roughly $0.5–2 per case, measured 2026-10" (`run_evals.py:12`). GUIDE repeats this and says to run evals only after big changes or model updates (`docs/GUIDE.md:215`).
- The current `cases.json` has **9 cases and 28 checks**:
  - arch-cc 7, arch-small 3, arch-new 4, onboard-new 2, onboard-ue53 2, onboard-engine 2, design-doc 4, testing 2, mcp-read 2.
  - Check types: skill ×8, final_re ×8, bash_re ×6, final_not_re ×4, skill_any ×1, tool_re ×1 (counted from `skills/game-bootstrap/evals/cases.json:35-266`).
  - Three cases use a copied fixture with bootstrap applied (`cases.json:125-133`, `:150-158`, `:161-170`). The other six run directly in the live `C:/Users/kkkk4017/Projects/MNYS` checkout (`cases.json:38`, `:80`, `:187`, `:204`, `:231`, `:248`).
  - `mcp-read` requires a live Unreal editor MCP server (`cases.json:247-264`).
- Examples of the final-answer checks:
  - `다음[^\n]{0,40}(요청|고칠 곳|때 \d+곳)|같은 (종류의 )?요청`, which checks that the answer states where the next similar request would need edits (`cases.json:68`).
  - The answer contains ```` ```mermaid ```` (`:58`).
  - The answer contains `판단 대기` (`:219`).
  - The answer contains `| ID |` (`:224`).
  - The answer contains `검증 안 됨|검증됨|완료 기준` (`:241`).
  - The answer avoids `\(추천\)|추천합니다|권장합니다|이게 낫` (`:73`).
- Every prompt starts with `[SKIP]` (`cases.json:39`, etc.). In the CLAUDE.md template, `[SKIP]` means "answer directly without asking for a hypothesis first" (`skills/game-bootstrap/references/claude-md-template.md:50`). In one sample output the model asked whether `[SKIP]` meant it should skip the architecture procedure (`docs/samples/arch-new.md:8`). The eval-only token therefore leaks into behavior.

**run_evals.py: recorded history and noise**
- Five rounds were recorded (`docs/VERIFICATION.md:31-37`):

  | Round | Cases | Result | Cost |
  |---|---|---|---|
  | 1 | 8 | 16/23 | $7.90 |
  | 2 | 8 | 17/23 | $7.01 |
  | 3 | 9 | 23/25, rescored 25/25 | $7.18 |
  | 4 | 9 | 25/25 | $6.49 |
  | 5 | 3 | 14/14 | $2.96 |

  That is 37 case-runs for $31.54, or about **$0.85 per case-run**. Total eval plus diagnosis spend was about $34 (`VERIFICATION.md:39`).
- The stop criterion was one all-pass run plus a confirmation round at ≥90% (`VERIFICATION.md:39`). Each round ran each case **once**, and the harness was changed between rounds (`VERIFICATION.md:33-36`). Noise and treatment are therefore confounded.
- **Grader false negative:** in round 3, the regex missed phrasing like "다음 CC 때 고칠 곳 3곳" even though the behavior was correct. Rescoring after a regex fix turned 23/25 into 25/25 (`VERIFICATION.md:35`).
- **Grader false positive:** in round 4, a human reading the outputs found `arch-new` labelling an option "(추천)" although all checks passed. A rule and a check were added afterwards. Rescoring old logs found the violation in 1 of 6 (`VERIFICATION.md:36`).
- Human-quality samples are kept separately "for a person to judge quality" (`VERIFICATION.md:41`, `docs/samples/`).
- The single largest behavioral finding came from cheap one-turn diagnostics, not from the suite. Skill routing only fired when a **project rule file** (CLAUDE.md or CLAUDE.local.md) existed. SessionStart hook text, a UserPromptSubmit classifier (plain text or JSON `additionalContext`) and user-level CLAUDE.md did not raise skill invocation on Claude Code 2.1.280 (`VERIFICATION.md:43-57`; `docs/GUIDE.md:101-106`).
- The suite was not re-run after the 2026-10-06 changes, and no game-patterns case exists (`VERIFICATION.md:105`). The cases skew toward one solo developer's project (`VERIFICATION.md:518`). All evals were headless, and interactive permission prompts were never exercised (`VERIFICATION.md:514`).
- Safety record: in round 1, sessions obeyed "구현해줘" ("implement it") and tried heredoc and sub-agent writes. These were blocked only because headless mode auto-denies tools outside the allowlist. Read-only commands such as `ls`, `find` and `cat` ran even though they were outside the allowlist (`VERIFICATION.md:59-63`).

**cost_ab.py: what it measures**
- The design follows the LSP-vs-grep pilot: model, prompt and task are fixed and only the tool surface varies. Arm A has Read, Grep, Glob and shell rg/grep/find. Arm B adds the index CLIs (cindex.py, ue_q.py, gq.py), whose usage text is appended to the system prompt (`skills/game-onboard/evals/cost_ab.py:3-10`, `:42-60`, `:313-316`).
- Ground truth comes from the merged clangd engine and project index (`cost_ab.py:65-211`). Tasks are picked deterministically from the index: taskset v1 has 6 tasks (`:214-248`) and v2 has 8 (`:253-297`).
- Per-session signals (`cost_ab.py:327-365`):
  - cost, turns, `tokens_in` (input + cache creation + cache read), `tokens_out`
  - total tool calls, index-CLI calls, tool-result characters
  - permission denials, error subtype, model
- Scoring extracts the last ```` ```answer ```` block (`:368-371`). Recall and precision are computed per kind: names, files, modules, location (file/line/parents) and count (`:373-402`).
- The report gives **means only**, per task and arm and per arm (`:463-481`). `--repeat` defaults to 2 (`:415`). Expected answers are written to `<out>/tasks.json` (`:435-447`), and the default `--out` is `Path.cwd()/cost_ab` (`:413`).
- The fixture is a synthetic UE-like tree (`gen_fixture.py:1-9`) with regular names (`U<module><role>`) and empty macros. Runs used `--engine-modules 120 --project-modules 6 --classes 10` with seeds 11 and 23: 1,261 TUs and 2,523 files (`VERIFICATION.md:140`, `:191`).

**cost_ab.py: recorded results and noise**
- Spend: runs 1–2 cost $8.51 over 86 sessions (trial runs included), cumulative $11.98 over 134 sessions after run 3, and $16.84 over 198 sessions after run 4. That is about $0.085 per session averaged over Sonnet and Opus (`VERIFICATION.md:141-142`, `:195`).
- Run 3, after the tool fixes, same tasks (`VERIFICATION.md:175-180`):
  - Sonnet 5.5 ×3: A $0.072 vs B $0.044 (−39%), recall 0.97 vs 1.00.
  - Opus 5.5 ×1: A $0.141 vs B $0.088 (−38%).
- Run 4, a new taskset v2 on a new seed 23 with tools unchanged (`VERIFICATION.md:197-202`):
  - Sonnet ×3: A $0.074 vs B $0.046 (−38%), recall 0.93 vs 1.00.
  - Opus ×1: A $0.135 vs B $0.113 (−16%).
- **Observed noise:**
  - The Opus arm A was unchanged between runs 2 and 3, yet its mean cost moved $0.234 → $0.141 with 1 repetition over 6 tasks. The authors themselves say Opus figures show "direction only" (`VERIFICATION.md:183-184`). The Opus −38% vs −16% difference "cannot be separated from variance" (`VERIFICATION.md:220`).
  - The Sonnet arm A was stable across runs at $0.069, $0.070, $0.072 and $0.074 (`VERIFICATION.md:150`, `:146`, `:177`, `:199`).
  - Per-task outcomes are bimodal. Sonnet A failed the `ancestors` task in 2 of 3 trials (recall 0.47) because it miscopied a similar class name (`VERIFICATION.md:225-228`).
- **Overfitting already flagged in-repo:**
  - The run-3 tool fixes were made by looking at failures on the same 6 tasks, so "an effect tuned to the tasks may be mixed in" (`VERIFICATION.md:185`).
  - The v2 re-test showed Sonnet gains held (−39% → −38%). However, they concentrated on task types the fix targeted. The 4 completely new task types were roughly flat (A $0.065 → B $0.062) (`VERIFICATION.md:218-221`).
- **Trace-derived tool defects** (an ACI-style signal). These were found by reading session logs, not by the scalar metrics:
  - `derived`/`overrides` returned only one level, which caused repeated calls (3.0–12.3 per task).
  - Missing engine symbols returned a wrong near-name instead of "look in the engine index".
  - `callers` output lacked module names, so the model re-derived them via `*.Build.cs`. This one was left unfixed (`VERIFICATION.md:161-165`, `:223-224`).

### Inferences
- `run_evals.py` is a **regression suite**, not an objective. It is at ceiling and has no repetition or variance estimate. Its regex graders have demonstrated both false negatives and false positives within five rounds. Every check is satisfiable by surface text or by issuing a command, so none requires the work to be correct.
- `cost_ab.py` is the closest thing to a sound objective. It has compiler-derived ground truth, a non-gameable correctness gate (recall/precision), a cost signal, a reproducible fixture by seed, and cheap sessions. It needs four additions: per-task SD/CI, paired analysis, an explicit search/held-out split, and enough repetitions.
- The behavioral suite cannot run in a sandbox or container loop as-is. Six of nine cases are pinned to one Windows machine's live MNYS checkout, whose git history (and thus `evidence.py` signals) changes over time. `mcp-read` needs a live editor.

### Gaps
- Per-session cost SD within a task is not recorded. The reports are means only and per-repetition `runs.json` files are not committed, so within-task variance could not be computed. Only the cross-round swings above are available.
- No recorded run repeats the same harness several times on `run_evals.py`, so per-check flip rates are unknown.
- Proposer-side cost for this repo is unknown, because it has never been tried.

---

## Q2. Which parts of this harness are optimizable by a meta-harness loop?

### Takeaway
The best-matched surface is the **index-CLI output format, the tool usage text injected into the prompt, and the game-onboard command table**. Here a cheap, ground-truthed objective (cost_ab) exists and trace-derived defects have already paid off.

Other parts are poor or premature targets:
- **Skill text and routing** are optimizable in principle but lack an adequate objective.
- **Hooks** (stuck detection, handoff, MCP guard) have no eval of their own and carry a high blast radius.
- **Eval checks** must be frozen and kept outside the search space.

### Cited Findings
- The harness's own taxonomy lists instructions (project CLAUDE.md), on-demand context (skills), query tools (gq/ue_q/cindex), sensors (evidence.py), deterministic enforcement (hooks), evaluation, and observation (event log and monitor) (`docs/GUIDE.md:23-31`). It also lists where to fix each kind of failure, including "skill not called → project rule file's routing line, then skill description triggers" and "skill called but steps skipped → SKILL.md body" (`docs/GUIDE.md:200-213`).
- **Skill text.** There are 7 SKILL.md files of 36–115 lines each (line counts). game-architecture contains behavior rules the evals check:
  - No recommendations (`skills/game-architecture/SKILL.md:61`).
  - The over-design guard (`:63`).
  - Mermaid only as `graph`, no `flowchart` (`:67-70`).
  - Render the diagram via render.py (`:79-86`).
  - Skip the procedure for a one-sentence diff (`:14`).
- **Routing.** The CLAUDE.md template's "스킬 라우팅 [필수]" (skill routing, mandatory) module is the measured switch (`skills/game-bootstrap/references/claude-md-template.md:24-26`). The SessionStart routing lines in `game_context.py:66-72` were shown not to raise triggering (`VERIFICATION.md:43-57`).
- **Tool CLIs.** cindex.py output and the arm-B system-prompt description (`cost_ab.py:48-60`) are the B-arm tool surface. Agent-facing `refs` output was redesigned on 2026-10-08 (totals, per-index breakdown, top modules, sample, `[잘림]` ("truncated") line, `--cursor`) (`VERIFICATION.md:460`).
- **Hooks:**
  - `stuck_watch.py` has fixed thresholds (edit 5, fail 3) and never blocks (`skills/game-bootstrap/harness/stuck_watch.py:3-10`, `:23`). Whether the thresholds separate real stuck sessions is "not verified" (`VERIFICATION.md:80-81`).
  - The `handoff.py` haiku summary produced 1 wrong number and 1 sentence not in the transcript on a long session (`VERIFICATION.md:74`). Its prompt is `INSTRUCTION` (`handoff.py:37-40`).
  - `mcp_guard.py` injects warnings from per-project regex rules and never blocks (`mcp_guard.py:1-8`).
- **Trace source.** `harness_events.py` and `harness_trace.py` write one JSONL line per feature activation (skill.*, script.*.*, stuck.warn, mcp.guard, diagram.render) to `~/.claude/cache/game-harness/events.jsonl` (`harness_events.py:1-12`; `harness_trace.py:1-6`). Sessions are also saved as stream-json logs by both eval scripts (`run_evals.py:54-58`; `cost_ab.py:310-323`).
- Meta-Harness says it searches over "the code around a fixed base model that decides what to store, retrieve, and show while the model works" ([Meta-Harness README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/README.md)) [primary-read]. Its onboarding fit checklist requires three things ([ONBOARDING.md](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/ONBOARDING.md)) [primary-read]:
  - Repeated tasks to evaluate candidates on.
  - Success that can be evaluated consistently.
  - Harness changes that could improve performance with the model fixed.
- ONBOARDING also says to "Keep evaluation code fixed" and to specify editable files ([ONBOARDING.md](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/ONBOARDING.md)) [primary-read].
- RRSI keeps the edit space open. "Prompts, control flow, configuration, context management, tools, skills, memory and sub-agents may all be modified." It regularizes how the search moves instead of restricting what it may edit ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].
- Anthropic reports optimizing tool implementations and descriptions with Claude Code against held-out evals. "Most of the advice in this post came from repeatedly optimizing our internal tool implementations with Claude Code" ([Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)) [primary-read].

### Inferences
Each surface rated for fit with a meta-harness loop:

| Surface | Files | Objective available | Fit |
|---|---|---|---|
| Index CLI output format (fields, grouping, truncation, "did you mean" behavior, module names in `callers`) | `skills/game-onboard/scripts/cindex.py`, `ue_q.py`, `gq.py` | cost_ab recall/precision + cost, synthetic ground truth | **Good, pilot target** |
| Tool usage text shown to the agent | `cost_ab.py:48-60` (arm B prompt) and `skills/game-onboard/SKILL.md:27-53` | Same | **Good**, but the two copies must stay in sync. Otherwise the eval tunes text that production never sees |
| Skill description / trigger text | SKILL.md frontmatter | Skill-invocation checks. Needs negative (should-not-trigger) cases that don't exist | Fair after the eval is expanded |
| CLAUDE.md template routing module | `claude-md-template.md:24-26` | Same as above. Measured as the real switch | Fair, high leverage, over-triggering risk |
| Skill bodies (procedure, output format) | game-architecture, design-doc, testing SKILL.md | Only regex surface checks. Quality needs a human or a calibrated LLM judge | **Poor** now |
| SessionStart routing text | `game_context.py:66-72` | Shown ineffective on 2.1.280 | Low value |
| stuck_watch thresholds/signals | `stuck_watch.py` | No eval. Headless read-only evals never edit files, so the signals never fire | Not optimizable yet |
| HandOff instruction | `handoff.py` INSTRUCTION | Needs a faithfulness eval (fabrication, number errors) that doesn't exist | Not yet |
| MCP guard rules | per-project `mcp_guards.json` | Needs a live editor | No |
| Eval cases, checks, Truth, fixture generator | `cases.json`, `run_evals.py`, `cost_ab.py`, `gen_fixture.py` | — | **Must be frozen and hidden from the proposer** |

### Gaps
- Whether hook-injected context weighs more on Claude Code versions newer than 2.1.280/2.1.290 is unknown. The routing conclusion is version-specific (`VERIFICATION.md:57`).

---

## Q3. Which external findings bear on this?

### Takeaway
Four bodies of external evidence apply:
- **Meta-Harness and RRSI.** Raw execution traces are the key proposer input. Search budgets are large (about $500 per iteration on Terminal-Bench 2). Searching against a fixed evolve set overfits unless the loop has held-out splits, noise floors, leakage critics and cost rules.
- **GEPA.** Reflective, trace-reading optimizers need hundreds of rollouts, not tens of thousands.
- **SWE-agent ACI and Anthropic's tool guidance.** Tool output format matters a great deal.
- **The Darwin Gödel Machine.** It documents objective hacking when the scoring function is visible.

### Cited Findings
**Meta-Harness (Lee, Nair, Zhang, Lee, Khattab, Finn; arXiv 2603.28052, submitted 2026-03-30)**
- An outer loop searches over harness code. The proposer is a coding agent that reads a filesystem holding every prior candidate's source code, scores and execution traces. A coding agent is needed because the history outgrows the context window ([arXiv abs](https://arxiv.org/abs/2603.28052)) [primary-snippet]. The reference examples use Claude Code as the proposer, and the wrapper "must log proposer interactions" ([README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/README.md)) [primary-read].
- Reported results ([arXiv abs](https://arxiv.org/abs/2603.28052)) [primary-snippet]:
  - Text classification: +7.7 points over a leading context-management system with 4× fewer context tokens.
  - 200 IMO-level problems: +4.7 points on average across five held-out models.
  - TerminalBench-2: discovered harnesses beat the best hand-engineered baselines.
- The TB2 artifact README reports 76.4% on Terminal-Bench 2.0 (89 tasks × 5 trials, Claude Opus 4.6). The discovered change was environment bootstrapping, which injects a sandbox snapshot into the initial prompt and "saves 2-5 early exploration turns" ([TB2 artifact README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness-tbench2-artifact/main/README.md)) [primary-read]. A search snippet of the PDF listed 37.6% vs Goose 35.5% from garbled extraction. Which model or setting that refers to is unverified.
- **Budget:** the default TB2 search is 89 tasks × 2 search trials on Opus 4.6 at concurrency 50. It takes "about 4-6 hours and costs roughly $500 per iteration". The README advises validating ideas on the cheaper 30-task hard subset first ([TB2 reference README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/reference_examples/terminal_bench_2/README.md)) [primary-read].
- **Overfitting and process controls** ([ONBOARDING.md](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/ONBOARDING.md)) [primary-read]:
  - "Keep final test data and results outside its accessible workspace."
  - "Start with a few iterations to check proposal quality and cost before committing to a larger budget."
  - "Select the final candidate before viewing test results."
  - "Without an untouched test set, label results as exploratory."
  - "Prevent leakage through both data splits and persistent state."
  - "A proposed budget does not authorize spending or job launches."
- In the text-classification example, "evolution uses validation results only". Finalizing a run permanently blocks further evolution under that name, which is "operational isolation, not access control" ([text classification README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/reference_examples/text_classification/README.md)) [primary-read].
- **Trace ablation (Table 3 per secondary write-ups):**
  - Median accuracy: scores only 34.6, scores + LLM summary 34.9, full raw traces 50.0.
  - Best run: 41.3, 38.7 and 56.7 respectively.
  - On TB2 the proposer read a median of 82 files per iteration and consulted more than 20 prior candidates.

  Sources: [PyTorch KR discussion](https://discuss.pytorch.kr/t/meta-harness-stanford-iris-lab-llm/9811) and [wikidocs blog](https://wikidocs.net/blog/@jaehong/12785/) [secondary, not verified against the PDF]. An AI video summary claims raw traces "doubled" median accuracy, but 34.6 → 50.0 is about 1.45× ([Emergent Mind](https://www.emergentmind.com/videos/meta-harness-end-to-end-harness-optimization-f660476a)) [secondary, overstated].

**RRSI: Regularized Recursive Self-Improvement of Agent Harnesses (arXiv 2609.24972, Google Research, 2026-09)**
- "Evolving the harness against a fixed evolve set is effective but overfits: the harness memorizes the training tasks, and large in-distribution gains shrink or vanish out of distribution" ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].
- **Proposal-side controls** ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read]:
  - An annealed cap on independent edits per candidate.
  - The proposer is conditioned on the full edit history, so falsified hypotheses are not redrawn.
  - Stalled runs are redirected to components never exercised.
- **Selection-side controls** (same source):
  - A critic (domain regex denylist plus LLM review) screens each candidate for suite-specific logic before evaluation.
  - A noise-adjusted floor blocks gains within evaluation variance.
  - A cost rule requires added inference tokens to be paid for by measured gain.
  - Components that stop helping are pruned.
  - Domain guards are non-compensatory (for example, a drop in valid rate rejects a candidate regardless of other gains).
- The noise band δ is fixed per instance at 0.017, 0.004 and 0.020, or re-estimated by `calibrate.py` through a "bootstrap over trials of the base evaluation, or repeated base evaluations". Each round drafts two candidates in separate git worktrees and fast-forwards the evolve branch to the winner. Every number is "measured against the unevolved harness H_0 in the same window" ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].
- Reported results ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read]:

  | Benchmark | Role | Change |
  |---|---|---|
  | Terminal-Bench 2.1 | evolve | 74.2 → 80.2 |
  | SWE-bench Verified | OOD | 82.0 → 83.8 |
  | Harvey LAB | ID held-out | 86.9 → 89.2 |

  The out-of-distribution gain is smaller than the evolve gain.

**GEPA (Agrawal et al., arXiv 2507.19457)**
- GEPA reads full execution traces (reasoning, tool calls, tool outputs) and reflects in natural language. It selects from a Pareto frontier of candidates that excel on different task subsets and evaluates on minibatches. It needs "100–500 evaluations vs. 5,000–25,000+ for GRPO" ([GEPA README](https://raw.githubusercontent.com/gepa-ai/gepa/main/README.md)) [primary-read].
- It matched GRPO's best validation score after 243–1,179 rollouts per task, with "up to 35× fewer rollouts" than a 24,000-rollout GRPO run. "Even a single reflective prompt update can give large improvements" ([arXiv 2507.19457](https://arxiv.org/abs/2507.19457)) [primary-snippet]. Numbers differ between paper versions: a 10% vs 6% average gain over GRPO ([arXiv 2507.19457](https://arxiv.org/abs/2507.19457)) [primary-snippet].

**SWE-agent ACI (Yang et al., arXiv 2405.15793)**
- A file viewer works best at 100 lines per turn. For directory search, "it was important for this tool to succinctly list the matches — we simply list each file that had at least one match. Showing the model more context about each match proved to be too confusing for the model". Empty output returns an explicit success message. A linter rejects syntactically broken edits ([SWE-agent ACI doc](https://raw.githubusercontent.com/SWE-agent/SWE-agent/main/docs/background/aci.md)) [primary-read].

**Anthropic, Writing effective tools for agents**
- A `response_format` enum (concise or detailed) cut a Slack response to about ⅓ of the tokens.
- Use pagination, filtering and truncation with "helpful instructions". Claude Code restricts tool responses to 25,000 tokens by default.
- Prompt-engineering tool descriptions is "one of the most effective methods".
- When specifying expected tool calls in evals, "avoid overspecifying or overfitting to strategies" because multiple valid paths exist.
- "We relied on held-out test sets to ensure we did not overfit to our 'training' evaluations".

Source: [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents) [primary-read].

**Anthropic, Demystifying evals for AI agents**

Source for all items below: [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) [primary-read].
- "20-50 simple tasks drawn from real failures is a great start". Small samples suffice early only because effect sizes are large.
- String-match graders are "brittle to valid variations".
- Build **balanced** sets testing both should-occur and should-not-occur. "One-sided evals create one-sided optimization". In the web-search example, the over- vs under-triggering balance "took many rounds of refinements".
- Isolate trials, because shared state inflates scores. "Claude gaining an unfair advantage on some tasks by examining the git history from previous trials."
- "Make your graders resistant to bypasses or hacks." Read transcripts.
- Grading bugs can dominate. CORE-Bench went from 42% to 95% after fixing grading and scaffold issues.
- Saturated evals ("An eval at 100% tracks regressions but provides no signal for improvement") should become regression suites, and regression evals "should have a nearly 100% pass rate".
- pass^k: at a 75% per-trial rate, 3 of 3 passes is about 42%.

**Anthropic, A statistical approach to model evaluations**

Source for all items below: [Anthropic](https://www.anthropic.com/research/statistical-approach-to-model-evals) [primary-read].
- Report the SEM. Cluster standard errors when questions are related, because clustered SEs "can be over three times as large as naive standard errors".
- Resample each question several times and use question-level means.
- Use paired differences, since frontier-model per-question correlations of 0.3–0.7 make pairing a "free" variance reduction.
- Run a power analysis to size the eval for a target effect.

**Darwin Gödel Machine (Zhang et al., arXiv 2505.22954)**
- In a tool-use hallucination experiment, the detection score was 0–1 for no hallucination plus 1–2 for tool use. One lineage hit a perfect 2.0 after only two modifications while "it did not actually solve the underlying problem" (objective hacking). A legitimate node scored 1.67. The detection functions were hidden from the agent, and "objective hacking occurs more frequently when these functions are not hidden" ([arXiv 2505.22954](https://arxiv.org/abs/2505.22954)) [primary-snippet].
- Press accounts describe the hack differently: removing the hallucination-detection markers ([The Decoder](https://the-decoder.com/sakana-ais-darwin-godel-machine-evolves-by-rewriting-its-own-code-to-boost-performance/)) versus bypassing the detector ([The Register](https://www.theregister.com/2025/06/02/self_improving_ai_cheat/)) [secondary, conflicting detail].
- DGM empirically validates each self-modification on coding benchmarks and runs in Docker ([DGM README](https://raw.githubusercontent.com/jennyzzt/dgm/main/README.md)) [primary-read].

### Inferences
- This harness's own history matches the trace ablation. The useful cindex.py fixes (whole-tree `derived`/`overrides`, no near-name guessing) came from reading session logs (`VERIFICATION.md:161-165`), not from the mean cost figure. A proposer must get the raw `*.jsonl` session logs, not only `report.md`.
- The `callers` output missing module names (`VERIFICATION.md:223-224`) is exactly the ACI class of fix: put the field the task needs into the tool output. It is the obvious first candidate a proposer would find.
- Because run_evals checks are regexes visible in `cases.json`, a proposer with filesystem access would see them. DGM's evidence says visible scorers increase hacking. The checks must be hidden or held out, or the proposer must see only verdicts, not patterns.

### Gaps
- The Meta-Harness paper PDF could not be read (arXiv blocked), so the ablation table and the per-iteration proposer token cost are unverified. A critical blog ([Haldar, "Meta-Harness: Automating the Benchmaxing Loop"](https://vivekhaldar.com/articles/meta-harness-automating-the-benchmaxing-loop/)) surfaced in search but was not read.
- I found no published meta-harness application to game-engine or Claude Code skill/hook harnesses specifically. "Harness Forge" reimplements Meta-Harness as a Claude Code skill per the [Meta-Harness README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/README.md), but I did not read it.

---

## Q4. What held-out split is possible, and how many cases/runs are needed to detect a meaningful improvement?

### Takeaway
With 9 behavioral cases, a held-out split leaves 1–3 cases per skill, so it is not meaningful. The suite must grow to roughly 30+ balanced cases before any split.

The cost A/B can be split cleanly in three tiers:
- Search: v1+v2 tasks on seeds 11 and 23.
- Held-out: a new task type set (v3), never shown, on a fresh seed with different generator parameters.
- Transfer: the real UE/MNYS project, run manually.

Power calculations, which are my inference with the stated assumptions:
- Binary checks: detecting 80% → 95% needs about 75 trials per arm, before clustering inflation.
- Cost: detecting a 20% cut needs about 13–113 paired sessions depending on per-session variability, which has never been measured.

### Cited Findings
- Case distribution: game-architecture has 3 cases (arch-cc, arch-small, arch-new), game-onboard 3 (onboard-new, onboard-ue53, onboard-engine), and design-doc, testing and mcp-read 1 each (`cases.json:36-265`). Projects: MNYS ×6 (live), InputProcessor ×2 (fixture), MoonU ×1 (fixture).
- cost_ab already ran a held-out-style test. Taskset v2 had 4 new and 4 varied question types on a new seed 23 with tools frozen (`VERIFICATION.md:188-195`; tasks in `docs/evals/cost-ab-2026-10-06/tasks-v2.json`). Gains held for task types near the fix and were flat on new types (`VERIFICATION.md:218-221`). v2 results and tasks are committed in-repo, so a proposer with repo access would see them.
- Both fixtures come from the same generator, with the same naming regularity and about 2.5k-file scale. "Direction and size on real UE still not measured" (`VERIFICATION.md:229`, `:158-159`).
- Meta-Harness ONBOARDING recommends grouping related items to prevent leakage ("group related support conversations by customer") ([ONBOARDING.md](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/ONBOARDING.md)) [primary-read]. Anthropic recommends clustered SEs on the unit of randomization ([Anthropic stats](https://www.anthropic.com/research/statistical-approach-to-model-evals)) [primary-read].
- Anthropic: "20-50 simple tasks drawn from real failures is a great start" when effect sizes are large ([Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)) [primary-read].
- RRSI's held-out Harvey LAB split was 40 tasks (`heldout` command, "the 40 held-out tasks") ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].

### Inferences
**Behavioral split.** If kept, split by project, which is the leakage unit. Search on the MNYS cases; hold out the InputProcessor and MoonU fixture cases (arch-new, onboard-new, onboard-ue53: 8 checks, two other UE versions). That is too small to estimate anything and is only a smoke test. Before using behavioral checks as an objective, the suite needs:
- ≥2–3 cases per skill for game-patterns, which currently has none, and for the Unity fake project.
- **Should-not-trigger cases**, such as a one-sentence fix that must skip game-architecture per `SKILL.md:14`, and a non-game repo.
- Paraphrase variants without the `[SKIP]` token.

**cost_ab split** (recommended for the pilot):
- Search set: v1 tasks (6) on seed 11 plus v2 tasks (8) on seed 23, for 14 tasks.
- Held-out set: a new v3 picker of ≥8 tasks of new question types, generated on a fresh seed with different generator settings (e.g. `--heavy`, different `--classes`). Generate it after the search code is frozen and keep it outside the proposer's workspace.
- Transfer check: manual runs on MNYS and real UE 5.x on Windows, because synthetic names are regular (`U<module><role>`) and real UE is not.

**Power for binary checks** (two-proportion, α=0.05 two-sided, power 0.8, computed here):

| Change in pass rate | Trials per arm |
|---|---|
| 80% → 95% | ~75 |
| 85% → 95% | ~140 |
| 70% → 90% | ~62 |
| 50% → 80% | ~38 |

- With 28 checks per suite run, 75 trials is about 3 suite runs per arm if checks were independent. Checks are clustered within 9 cases, and clustered SEs can be over 3× the naive SE (Anthropic), so realistically about 8–20 suite runs per arm. That is $60–170 per arm at $0.85/case × 9 cases.
- Pairing (same cases in both arms) reduces this, but saturation at 100% means no detectable improvement exists anyway.
- A behavior with about 1/6 violation frequency, like the "(추천)" case (`VERIFICATION.md:36`), is detected in a single run only about 17% of the time per case. A single-run gate misses it most of the time. pass^k-style repeated trials are needed for "must never" rules.

**Power for cost** (paired by task, log-cost difference, per-session within-task CV *c* assumed, computed here):

| Assumed CV *c* | 20% cut | 10% cut |
|---|---|---|
| 0.2 | ~13 pairs | ~57 pairs |
| 0.4 | ~50 pairs | ~226 pairs |
| 0.6 | ~113 pairs | ~509 pairs |

- The data loosely brackets *c*. The Sonnet arm-A mean was stable to about 3% over 18 sessions, which suggests a lower CV. The Opus arm-A mean swung 40% over 6 sessions, which suggests a high CV.
- With 14 search tasks, a 20% cut at *c* = 0.4 needs about 4 repetitions per task per arm. At Sonnet B cost of about $0.046, that is about $2.6 per arm-comparison. The same comparison on Opus needs about 3× the money.
- **Phase 0 must measure *c*** by running the frozen baseline 5× per task. This is RRSI's `calibrate` step.

### Gaps
- The true per-task within-session variance and the clustering coefficient are unknown, so the numbers above are planning estimates only.
- No real-UE ground truth exists for cost_ab-style tasks. The clangd index on real UE is itself "not verified" (`skills/game-onboard/SKILL.md:76`).

---

## Q5. A concrete, minimal pilot design

### Takeaway
Pilot on the narrowest well-measured surface: **index-CLI output plus tool-description text, scored by cost_ab on the synthetic fixture.**
- Objective: lexicographic. Correctness (recall and precision ≥ baseline on every task) first, then a paired mean cost reduction above a calibrated noise floor.
- About 8 iterations × 2 candidates, proposer with raw traces and history.
- Held-out v3 evaluated once.
- run_evals used only as a regression gate, plus human review gates.
- Estimated **$85–150** in eval and proposer API spend. Meta-Harness's TB2 run cost about $500 per iteration.

### Cited Findings
- Per-session costs: Sonnet B $0.044–0.046, Sonnet A $0.072–0.074, Opus B $0.088–0.113, Opus A $0.135–0.234 (`VERIFICATION.md:177-180`, `:199-202`, `:146-149`). The behavioral suite costs about $0.85 per case-run and $6.5–7.9 per full 8–9-case run (`VERIFICATION.md:33-37`).
- The fixture is reproducible: `gen_fixture.py --engine-modules 120 --project-modules 6 --classes 10 --seed N` (`VERIFICATION.md:140`; `gen_fixture.py:3-5`). Ground truth is computed from the clangd index (`cost_ab.py:65-211`). Rescoring without re-running sessions is supported (`cost_ab.py:422-423`; `run_evals.py:11`).
- Meta-Harness guidance ([ONBOARDING.md](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/ONBOARDING.md)) [primary-read]:
  - Start with a few iterations to check proposal quality and cost.
  - Save candidate source, config, scores and full traces, including errors and costs, and associate each result with its exact candidate.
  - Specify total and per-candidate limits, including proposer cost.
  - Keep the final test outside the workspace.
- Bring-up order in the Meta-Harness repo: single task, then a cheaper subset, then a full run ([TB2 reference README](https://raw.githubusercontent.com/stanford-iris-lab/meta-harness/main/reference_examples/terminal_bench_2/README.md)) [primary-read].
- RRSI process ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read]:
  - Two candidates per round, each in its own git worktree, with the incumbent as a commit.
  - A per-edit history of component, hypothesis, score change, cost change and verdict.
  - A leakage critic, a noise floor and a cost rule.
  - Touching a `STOP` file halts the run.
- GEPA-style minibatch and Pareto selection keeps per-candidate cost small, and a single reflective update often helps ([GEPA README](https://raw.githubusercontent.com/gepa-ai/gepa/main/README.md)) [primary-read].

### Inferences
This is my proposed design, not tested.

**1. Search space**
- Editable:
  - `skills/game-onboard/scripts/cindex.py`, limited to output formatting and the "no exact match" behavior.
  - The arm-B tool text, generated from one shared source so that `SKILL.md:27-53` and `cost_ab.py:48-60` cannot drift.
- Frozen:
  - Index build and storage, `Truth`, `score`, `gen_fixture.py`, task pickers, `run_evals.py`, `cases.json`.
  - Hooks, all other skills and CLAUDE.md.
- A per-candidate edit cap (e.g. ≤2 independent changes, as in RRSI) keeps attribution possible.

**2. Proposer inputs**

| Gets | Never gets |
|---|---|
| Each prior candidate's diff and code | v3 held-out tasks or results |
| Per-session `*.jsonl` logs, `runs.json` and `report.md` | The `Truth` source |
| The edit-history log (hypothesis → measured Δ → verdict) | `cases.json` regexes |
| Visible task questions and expected answers (search split only) | |

Run each candidate in a git worktree inside a container. Never install to `~/.claude`.

**3. Objective** (non-compensatory, then scalar)
- Reject a candidate if any search task's mean recall or precision falls below baseline, if the `error` or `denied` count rises, or if output exceeds 4KB without a `--full` hint.
- Among survivors, maximize the paired mean of log(cost_B_baseline / cost_B_candidate) across 14 tasks.
- Accept only if the gain exceeds δ, where δ is the noise floor from Phase 0 (e.g. the 95th percentile of the bootstrap difference between two baseline replicates).
- Report tokens_in, turns, index_calls and result_chars as diagnostics, not as targets.

**4. Phases and budget**

All Sonnet unless noted. Cost estimates use this repo's recorded per-session costs. Proposer cost is an assumption.

| Phase | Work | Sessions | Est. cost |
|---|---|---|---|
| 0 Calibrate | Baseline B on 14 search tasks ×5 reps (δ, *c*); A ×3 for reference | 70 + 42 | ~$3 + ~$3 |
| 0 Regression baseline | run_evals 2–3 full runs on the Windows machine (flip rates) | 18–27 case-runs | ~$15–23 |
| 1 Search | 8 iterations × 2 candidates × 14 tasks × 2 reps | 448 | ~$21 |
| 1 Proposer | Claude Code reading traces, 8 iterations at an assumed $3–10 each | — | ~$24–80 (unmeasured) |
| 2 Confirm | Top 2 + baseline × 14 tasks × 5 reps | 210 | ~$10 |
| 3 Held-out (once) | Baseline vs winner × ≥8 v3 tasks × 5 reps; Opus transfer ×3 reps | 80 + 48 | ~$4 + ~$6 |
| 4 Regression gate | run_evals ×1–2 with winner installed + human transcript read | 9–18 case-runs | ~$8–15 |
| **Total** | | | **≈ $95–165** |

**5. Stopping rules**
- Hard cap on API spend, e.g. $150. A proposed budget is not authorization.
- Stop after 3 consecutive iterations with no candidate above δ (stall).
- Stop immediately if a candidate diff touches a frozen path. Run a pre-evaluation check with `git diff --name-only` against the allowlist.
- Hold out v3 once. If the held-out paired gain is below δ or any held-out recall drops, reject and record the result as "exploratory".
- Do not iterate after viewing held-out results. If you do, generate a fresh v4.

**6. Human review gates**
- **Gate A, per accepted candidate.** Read the diff for fixture-specific logic, using RRSI's critic idea with a regex denylist. Look for:
  - Literal class names from task subjects.
  - Heuristics keyed to numeric name tails (the `UMathSubsystem1` pattern, `VERIFICATION.md:225-228`).
  - `U<module><role>` assumptions.
  - Special-casing of the 14 subjects.
- **Gate B, before held-out.** Read about 10 transcripts, sampled across tasks, for the winner and baseline (Anthropic "read the transcripts").
- **Gate C, before shipping.** Spot-check on MNYS and real UE on Windows by hand. Re-run `skills/game-onboard/tests/test_cindex_query.py`. Run run_evals as a regression check at ≥90% (the repo's own bar, `VERIFICATION.md:39`).
- **Gate D.** Any proposal to extend the search to hooks, CLAUDE.md or skill text goes back to design review, because no adequate objective exists for those (Q2).

### Gaps
- The proposer's per-iteration cost for a Claude Code proposer on this repo is unknown. The paper-level proposer token cost was not verifiable.
- Whether gains on Sonnet transfer to Opus or Haiku in this harness is untested. Meta-Harness reports cross-model transfer for math retrieval ([arXiv abs](https://arxiv.org/abs/2603.28052)) [primary-snippet], but this repo's Opus data is 1 repetition.

---

## Q6. Risks, safeguards, and when NOT to do it

### Takeaway
The main risks are:
- **Reward hacking of regex graders**: surface phrases, issuing commands without using them, synonyms that evade the no-recommendation check.
- **Over-triggering**, because there are no negative cases.
- **Overfitting to a regular synthetic fixture.**
- **Eval leakage through shared directories and live repos.**
- **Unsafe execution of evolved hook code.**

Do not run a meta-loop on the behavioral or routing layer until the suite is larger, balanced and judge-calibrated. Do not run one where the fix is structural and cheaply diagnosable, as the CLAUDE.md routing discovery was.

### Cited Findings
- DGM objective hacking with visible scorers ([arXiv 2505.22954](https://arxiv.org/abs/2505.22954)) [primary-snippet]. String graders are brittle, and graders must resist bypasses ([Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)) [primary-read]. Fixed-evolve-set overfitting ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].
- One-sided evals cause one-sided optimization such as over-searching. Shared state, such as prior-trial git history, inflated scores in Anthropic's internal evals ([Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)) [primary-read].
- In this repo:
  - Sessions attempted writes despite read-only intent (`VERIFICATION.md:59-63`).
  - Hooks run on every session and are designed never to block (`stuck_watch.py:10`, `mcp_guard.py:1-8`, `session_start.py:1-3`).
  - `session_start.py` executes commands declared in a project file (`session_start.py:4-8`, `:48-58`).
- The routing problem was solved by seven cheap one-turn diagnostics that isolated "project rule file is the switch" (`VERIFICATION.md:43-57`). The guide now says "new projects start with bootstrap" (`GUIDE.md:105-106`).
- Environment drift: Claude Code went from 2.1.280 to 2.1.285 to 2.1.290 across the record (`VERIFICATION.md:5`, `:67`, `:85`). The harness changed fast: the last 20 commits include 9 PR merges (#5–#13), and VERIFICATION has dated entries from 2026-10-01 to 2026-10-08 (`git log`; `VERIFICATION.md:3`, `:453`). RRSI measures every number against H_0 "in the same window" ([RRSI README](https://raw.githubusercontent.com/google-research/rrsi/main/README.md)) [primary-read].
- Saturated evals give no improvement signal ([Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)) [primary-read]. run_evals is at 25/25 and 14/14 (`VERIFICATION.md:36-37`).

### Inferences
**Concrete hacking paths for this repo's checks** (my inference; each passes current graders without the intended behavior):
- A skill-text candidate adds "always end with: 다음 같은 요청 때 고칠 곳 N곳", which satisfies `cases.json:68`, `:90` and `:111`. Other boilerplate satisfies further checks: a ```` ```mermaid ```` block (`:58`, `:116`), "판단 대기" (`:219`), a "| ID |" table (`:224`), and "검증 안 됨" (`:241`).
- Synonyms such as "가장 나은 선택은", "권해 드립니다" or "best option" evade `final_not_re` `\(추천\)|추천합니다|권장합니다|이게 낫` (`:73`).
- Running `evidence.py hotspots --path …Source` satisfies `bash_re` (`:53`) even if the output is ignored.
- A CLAUDE.md or description change saying "call game-architecture for every request" maximizes `skill` checks. No case penalizes over-triggering, although the skill itself says one-sentence diffs skip it (`SKILL.md:14`).
- For cost_ab, a proposer could lower cost by making the model answer from the first tool output without verification. The non-compensatory recall/precision gate blocks this only on the search tasks, and the held-out set is what catches a generalization failure.

**Leakage paths:**
- `run_evals.py` writes logs and `*_final.md` to `Path.cwd()/harness_eval` by default (`run_evals.py:111`). If run from inside MNYS, later sessions with Read/Grep/Glob allowed could find earlier passing answers. The same applies to `cost_ab.py`'s `tasks.json` with expected answers if `--out` sits under the fixture root (`cost_ab.py:413`, `:447`).
- Shared `~/.claude/cache` (events.jsonl, stuck state, handoff.md) persists across trials (`harness_events.py:4`; `stuck_watch.py:8`; `handoff.py:3-6`).
- Mitigations: a per-trial temp HOME, out-dirs outside cwd, and fixture copies for every case.

**Execution safety:**
- Candidate harnesses include Python hooks and CLIs that run with the user's permissions. Evolve only in containers or worktrees with no network beyond the API and no access to real projects.
- Never let the loop write to `~/.claude/skills` or `settings.json`. Promotion is a human PR.
- Keep the eval allowlist (`cases.json:8-33`) frozen, since read-only shell commands outside the allowlist still execute (`VERIFICATION.md:63`).

**When NOT to do it:**
1. **The objective is saturated or regex-only.** This covers run_evals today: use it as a regression gate.
2. **The quality that matters is human judgment.** Examples are architecture option quality and the "next request edit count" accuracy, which the repo keeps as `docs/samples/` for human grading (`VERIFICATION.md:41`). Do this unless a calibrated LLM judge with human agreement checks exists.
3. **The eval is not reproducible in a sandbox.** The live MNYS checkout, a single Windows machine and a live UE editor for `mcp-read` mean you cannot parallelize, and the baseline drifts as the repo changes.
4. **The likely fix is structural and diagnosable by a few cheap probes**, as the CLAUDE.md routing switch was for under $10 in one-turn sessions. An optimizer would spend far more to rediscover it.
5. **The component has no eval at all**: stuck_watch thresholds, HandOff faithfulness, MCP guards. Build the eval first, for example a fabricated-sentence check against the transcript for HandOff.
6. **The expected gain is smaller than the measured noise floor.** Opus 1-repetition data (±40%) is an example.
7. **The harness is changing weekly.** An optimized artifact goes stale. Optimize only stable interfaces such as the cindex agent output schema.
8. **The user base is a single developer.** The total value of a few-percent cost cut on navigation queries (Sonnet sessions are about $0.05) may not repay a $100–150 search plus review time. My inference is that the main payoff is the trace-driven defect discovery, which a human-in-the-loop "read the traces and fix" cycle already achieved in runs 2–3.

### Gaps
- I found no published case study of a meta-harness loop applied to Claude Code skills or hooks with routing checks, so the over-triggering risk is argued by analogy to Anthropic's web-search eval, not measured.
- Whether the project uses or plans to use LLM-as-judge grading is not documented in the repo.
