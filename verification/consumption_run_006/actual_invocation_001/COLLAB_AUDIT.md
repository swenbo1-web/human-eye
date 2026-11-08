# RUN006 public collaboration metadata audit

All 8/8 available consumer projections match an independent recount.

| Measure | Observed value |
|---|---:|
| Projected events | 0 |
| Identifiable calls, summed per-consume item.id | 0 |
| Events without usable item.id | 0 |
| Observed thread IDs, union | 0 |
| Calls lacking observed terminal event | 0 |
| Calls with conflicting terminal statuses | 0 |
| Calls with conflicting tool values | 0 |

| Slot | Task/arm | Status | Events | Identifiable calls | No-ID events | Observed IDs |
|---|---|---|---:|---:|---:|---:|
| 01 | T01/N | completed | 0 | 0 | 0 | 0 |
| 02 | T01/P | completed | 0 | 0 | 0 | 0 |
| 03 | T02/P | completed | 0 | 0 | 0 | 0 |
| 04 | T02/N | completed | 0 | 0 | 0 | 0 |
| 05 | T03/N | completed | 0 | 0 | 0 | 0 |
| 06 | T03/P | completed | 0 | 0 | 0 | 0 |
| 07 | T04/P | completed | 0 | 0 | 0 | 0 |
| 08 | T04/N | completed | 0 | 0 | 0 | 0 |

Interpretation and limits:

- Events, item.id calls within each consume, missing-ID events, and observed thread IDs are different measures.
- Observed IDs include senders; they are not new/successful agent counts or a complete participant count.
- The collector only sees its verified public projection; zero projected events is not proof of no backend collaboration.
- Original discarded counters remain independently retained, including collab_tool_call if present.
- Main-context usage is retained once per context for reference and is the same source as the counts audit; do not add the audits together.
- Extra participant count and usage, provider requests and fees stay null. Accounting remains incomplete; backend stays unexposed.
- No private collaboration prompts/messages/arguments/results/errors, hidden bodies, final answers, truth, auth, or global private logs were used.

The JSON preserves each original projected collaboration object and discarded-event counter unchanged. It preserves main-context usage once per slot without estimating extra participant usage. No additional experiment execution was performed.
