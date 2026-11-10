# Two installed plugin versions: actual LLM A/B

2026-11-10 (Asia/Shanghai). Cycle `PLUGIN-VERSION-LLM-AB-001`.

**Conclusion: both versions complete the same tasks correctly; this small optimization did not demonstrate an end-to-end speed or token benefit.** Six paired comparisons split evenly: B was faster in three and slower in three. Do not describe this as a native-tool comparison or an acceptance of the entire new architecture's benefit.

## What actually ran

- A: `a3a72b929f55c40f195ff5e1a9f64ceb303b6360`, canonical `e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0`.
- B: `d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d`, canonical `a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b`.
- Both are independently built wheels installed into separate venvs, using the same NumPy/Pillow versions. Root compared Git, wheel and installed bytes; each actual Blender worker records its corresponding installed source identity.
- Same requested `gpt-6.1-sol` / `medium`, ChatGPT/Pro login, prompt, two tools and completion rule. Provider-resolved effort is not available. No Google or external paid API was used.
- Three fixed synthetic three-bone tasks: actual correction with common world rotation/translation; already-satisfied no-op; unreachable within the permitted interval. Two fresh A/B pairs for each task, balanced A/B and B/A order. Each consumer gets a newly initialized owned scene and a fresh model session.
- A common experimental MCP bridge exposes the existing installed programmatic scheduler. It does not solve or assign candidate poses. This is not a newly published default MCP capability. The completion rule requires an actual engine receipt; this experiment does not test unrestricted model tool preference.

## Results from the twelve comparable sessions

Each column contains six sessions. Durations include all observed task activity within the named boundary. These are descriptive results from the fixed sample, not causal or population performance estimates.

| Metric | A | B | Observed B change |
| --- | ---: | ---: | ---: |
| Model answer quality | 6/6 | 6/6 | same |
| Actual geometry / correct no-op or unreachable outcome | 6/6 | 6/6 | same |
| Prompt submission through complete final answer, median | 19.7645 s | 19.9394 s | +0.89% |
| Session start through confirmed cleanup, median | 22.7791 s | 23.4558 s | +2.97% |
| Session start through confirmed cleanup, summed | 140.6413 s | 141.0656 s | +0.30% |
| Actual scheduler entry, median | 104.7122 ms | 110.9432 ms | +5.95% |
| Worker product method, median | 69.1952 ms | 70.3802 ms | +1.71% |
| Model tool calls | 12 | 12 | unchanged |
| Public input tokens, summed | 139,210 | 139,177 | essentially unchanged |
| Public output tokens, summed | 1,537 | 1,502 | -2.28% |
| Input plus output tokens, summed | 140,747 | 140,679 | -0.048% |
| Cached input tokens, summed | 74,880 | 60,928 | cache exposure differs |
| Delivered tool/schema text bytes, summed | 58,321 | 58,325 | essentially unchanged |

Both versions invoke two tools per task and deliver essentially the same facts. The new code therefore does not remove a model round or materially reduce its context. There is no demonstrated user-visible gain from this particular change.

All four actual corrections met the area-loss target, and all eight no-op/unreachable cases correctly avoided candidate writes. The independent blind reviewer passed all twelve answers, 72/72 semantic criteria. Some no-op answers leave the unmeasured after-value null; others explicitly reuse the unchanged before-value. Neither is a false independent after-measurement. No false execution or achievement claim was found.

The earlier +3.6% record measured hot entries in one sequential eight-task process. This experiment uses a fresh process/ledger for every consumer; the new entry measurements are not directly comparable to that old hot-entry absolute timing.

## What the local optimization saved, and one slow entry

Across A's six formal tasks, expert preparation inclusive time is 10.0517 ms, of which 7.2744 ms is static parsing that B still performs. The exclusive removed feature work is **2.7773 ms total**, about 0.463 ms per task. Ledger validations fall 12→6, but their aggregate duration is only 0.0064→0.0049 ms in these fresh, initially empty ledgers. These deletions are real and tiny relative to roughly twenty-second model tasks.

One B unreachable entry took 323.3851 ms versus its A counterpart's 96.2852 ms. Its first `service_save` took 232.8528 ms versus 5.7901 ms; mutation RPC duration was almost identical (85.6595 versus 85.6032 ms). The outlier is localized to the state-save phase, not the geometry method. The records do not identify the underlying OS/filesystem cause. This observation is not used to discard the slow sample or launch another tuning round.

## Original infrastructure failure and full accounting

The first attempted consumer returned a correct answer and completed the actual action, but CLI teardown bypassed the adapter's graceful shutdown. Terminal/cleanup evidence was missing. It remains an infrastructure failure, with its original code, output, actual after-record and complete ledger preserved. The original owned processes were confirmed absent; the original scene was not retried.

A single amendment allowed a common adapter fix: close and record the owned host before returning the tool result. The twelve comparable sessions then ran in fresh scenes with identical corrected adapter bytes. Product source, prompt, tool schema and tasks stayed fixed.

- Total test consumer attempts: **13**; complete lifecycle passes: **12/13**. Corrected comparable sessions: **12/12**. The infrastructure attempt is not mixed into the six clean timing pairs.
- The failed attempt consumed 23,576 input tokens and 231 output tokens; its full recorded lifecycle was 37.0635 s, with 18.8122 s through final answer. These costs remain included in experiment totals.
- All thirteen test consumers total **301,963 input / 3,270 output tokens**, including 148,992 cached input tokens. Actual provider request counts beyond exposed tool/turn events are unavailable.
- Building/installing the two test environments took 60.2225 s. Auxiliary no-model preflight, adaptation, recovery and independent review are separate preparation costs, not hidden inside per-task speed claims.
- Author/coordinator/judge model usage and dollar cost are not exposed and remain unmeasured. Pro token counts are not converted into invented API charges. The experiment does not establish monetary net benefit.

## Independent evidence and scope

Root ran 1120 Git/wheel/install checks, then 355 actual session/source/tool/usage/timing checks and 220 independent geometry checks on the twelve formal records. The blind answer judge performed 72 separate semantic checks. These counts are checks, not extra assets or model samples. Author assertions are not counted as root executions.

Root recomputed areas, transforms and source-frame alignment from saved native arrays with independent math. Preparatory reviewer errors (exact float equality, an incorrect intermediate world-frame assumption, and literal matching of TOML-escaped argv) were corrected against actual data contracts; their failed reports remain saved. No acceptance tolerance or product result was altered to pass.

Primary root evidence: `INSTALL_REVIEW.json`, `RUN_REVIEW.json`, `COST_DETAILS.json`, `BLIND_ANSWERS.json`, `BLIND_QUALITY_REVIEW.json`. The implementation originals live at `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/plugin_version_llm_ab_001/`.

Formal installation, original assets, competing branches and paused Google/API work were not changed. This concludes the requested two-version sandbox experiment; no additional optimization or consumer sampling is initiated.
