# NATIVE-PLUGIN-COMPLEX-004 root comparison plan

User requested a fresh comparison of native Blender, the previous plugin and the current optimized plugin. This batch measures real model consumption and complete-task cost; it does not substitute the earlier scripted native solver results.

## Arms and loading

- N: ordinary read-only Blender Python, including bpy, NumPy, mathutils/BVH, model-written computation and persistent per-session variables. No task solver or oracle is injected.
- O: fixed d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d, canonical a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b, 137 sources. Installed into a product-only controlled lab release, not activated as default.
- C: fixed df016079b0265ee327f884c90dd4815c392016b6, canonical 3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd, 137 sources. Use the current installed controlled entry with a separate test connector, state and audit.

Both entries use the same dependency Python and identical normalized launcher template. Root checked all 274 installed runtime files: only surface_proximity.py differs, by the already reviewed four-line integer fast path. Both plugins must expose the same ordinary human_eye_scene_observe schema, plus the identical common native tool. No write tools are exposed. Each cell has a new plugin process, fresh owned Blender scene and fresh model session; no desktop cache or shared GUI state is used.

## Tasks and fixed denominator

Two previously verified assets, three arms, three repeats: 18 planned model sessions, executed serially with Latin rotation per task. All unsuccessful, unknown and unrun cells remain in the denominator. Exact order is frozen before the first consumer.

1. Reuse native_plugin_complex_003 assembly.initial: rotated concave closed solid with a hole, three candidates, overlapping world bounding boxes, different actual relations. Retain the existing question and completion requirements. This is a spatially nontrivial task with small geometry, not a large asset.
2. Reuse scale_diag_001 D_mid48: Target versus all other mesh objects, asking only the globally nearest unsigned surface distance. The prior independent 47-pair certificates and unique nearest result support this question. Do not expand it to solid penetration or nearest-separated classification.

Suggested second prompt: "只读检查当前场景。以名为 Target 的网格为目标，在场景其余全部网格中找出与它三维表面距离最小的对象。报告对象名称、距离（单位米，绝对误差不超过1e-6 m）、是否完整覆盖候选，以及必要依据。若仍存在未解决的候选，说明范围与原因。自行选择工具，证据充分后直接回答。"

Do not give the model the winning candidate, distance, internal logical IDs, oracle files, management scripts, or a recommended geometry algorithm. Do not require all 47 distances in the answer. The same task prompt and completion rules apply to N/O/C; plugin use and native fallback are the model's choice.

## Common configuration and accounting

Reuse the verified Pro/ChatGPT CLI transport with gpt-6.1-sol, requested medium effort, 450-second consumer deadline, 570-second complete-cell deadline, 32 tool attempts, 1 MiB response budget, 30 seconds per tool, no images and no added consumer retries. Verify the actual CLI hash/version and current existing login; no API keys, Google calls or paid-provider changes. Retain any provider-reported limits or errors rather than bypass them.

Before freeze, root confirmed a common session-level budget notice for all 18 cells: "本轮只读，使用文本和几何数据；图像预算为0。最多32次工具调用，每次30秒，工具响应合计1MiB；代码上限256KiB，模型会话最长450秒。证据充分即可回答。" Task bodies remain unchanged. This notice does not name a preferred tool or argument. Inherit the original 256 KiB code and 128 worker-RPC limits. The 1 MiB budget counts tool-response wire; catalogue, handshake and coordinator QA/close remain separately measured in full cost. Do not silently rewrite an image request to false.

Record prompt-to-final, full cell lifecycle, tool intervals, setup/handshake/catalogue, final readback/cleanup, native fallbacks, physical calls, public bytes and actual reported usage. Failed tool attempts need finally-path records too. Inclusive metrics and cached/reasoning token subsets must not be summed twice. Exact provider request count, dollars or preparation/coordination usage unavailable from the host remain unmeasured. Baseline lab packaging is one-time preparation, separate from per-task execution and not hidden as zero cost.

Reuse existing source helpers and certified assets; no new product optimization or test-suite expectation edits. Do not launch a parallel model/Blender workload during formal sampling. The implementer prepares plan, source/fixture/schema identity and no-model preflight first; root checks that concrete freeze and sends GO before the 18 consumers. No further user approval is required for the authorized isolated test.

## Review and conclusions

Blind-label the final answers for independent correctness/completeness review, preserving original wording. Tool-method wording can reveal the arm, so do not claim perfect blinding. Review generated native code for truth-file access, product reuse or unintended writes; quality cannot be inferred from exit status.

Report each task separately: all three values, medians/ranges, paired results and totals. O/C engine behavior differs only by the fixed arithmetic optimization, but full model-time differences also include tool choice, generation and delivery. Do not attribute all wall-time movement to four lines, claim p95, or generalize two tasks to every complex scene. Prior 003 used a dedicated tool; its times are background only, not a contemporaneous arm.

Hook auto-trigger evidence remains a separate backlog and is absent from all three controlled consumer arms. Shared configuration, original assets and competing branches are unchanged.
