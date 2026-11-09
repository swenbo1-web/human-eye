# Independent read-only review

Reviewer: `/root/m5_product_review`, bound to this M5 task. No product/test import,
product/test execution or Blender process was started by the reviewer.

Product diff review passes. Execute still captures fresh state before using a
plan handoff and checks fingerprint, host identity, final request/caps and
readback tolerance. Original dispatcher, nonce/CAS, cancellation and deadline
checks remain. Current and projected geometry and clearance/collision demand
options are kept separate. Inflight and completion express distinct facts;
completion callback failure attempts to save known execution before propagating;
failed persistence retains a blocking state. The
review identified optional final presentation preceding durable completion;
that order was corrected and independently rechecked before final candidate QA.

Independent stdlib-only raw audit passes:

- Both 133-member runtime generations match their fixed product Git commits,
  disk, before/after identities and canonical digests. All six default worker
  expressions have the correct root, verified loader pin and full source manifest.
- All raw TX/RX request IDs, commands, parameters and results match
  `host_requests.jsonl`. Loop byte counts recompute exactly from the raw line
  interval. All six accepted owned replies close with `closed:true` and exit 0.
- Each fixture matches its before/after bytes and the corresponding other
  variant. Independent native matrix/vertex checks give the same physical
  zero/one/four-step outcome; all three non-target objects are unchanged.
  Actual `_assign_translation` entries are 0/1/4, `_assign_matrix` is 0, and
  rollback and unknown-event counts are 0.
- End-motion snapshots include the final status/end captures. Actual host
  `_capture` entries are 25/31/46 to 15/21/36. Actual MeshEntity constructors
  are counted separately from `from_dict`; no uncalibrated C-call zero is used.
- Distinct completed child-content versions are 0/3/9 to 0/1/4. Every candidate
  step's first completion contains actual motion and matching end revision, and
  its final step is already satisfied. Separate inflight/submitting snapshots
  remain 0/1/4. Final disk ledgers match those completed receipts and motions.
- `_save` function entries are 10/13/22 to 8/9/15. The raw observer's historical
  normal-return flag is not treated as proof of every atomic write. Whole-loop
  atomic write counts remain unknown.

No blocking issue remains. The main and actual QA reports correctly distinguish
loop/lifecycle time, synthetic oracle scope, nested profile costs, baseline
instrumentation failure, retained unittest fixture failures, and unmeasured
nonresident geometry work. The next optimization remains for coordinator review;
the current evidence does not label every remaining physical-meter or journal
boundary redundant.
