# Frozen execution design review

Reviewer /root/plugin_ab_design_review independently read the broker, inherited NativeSession and thin stdio client, driver, model transport, prompt, plan and freeze. No model or Blender process was launched by the reviewer.

FREEZE contains 11 files; all actual hashes matched. Root independently repeated the file binding check in FREEZE_REVIEW.json.

- Fixed 9 fresh sessions: NAB / ABN / BNA; same task and scene, requested gpt-6.1-sol medium, prompt, native tool and budget.
- All arms retain normal Python, NumPy, BVH, self-written algorithms and persistent namespace. A/B add the installed real HE tool; the broker does not solve or substitute answers.
- HE and native share the same owned Blender host/port. Management snapshots are not delivered to the consumer.
- Thin stdio EOF does not close the scene. Parent-held NativeSession retains the original Popen, reads final geometry, requests closure, checks WORKER_CLOSED and waits for actual exit.
- Initial constructor cleanup issue was identified before consumers and fixed: Owner.__new__ retains the partial object and cleanup checks whether native exists.
- Independent cell failure remains in the denominator; after confirmed cleanup the next planned cell continues. Common auth/quota/permission blockage or unconfirmed geometry/backend stops later cells. No failed-cell resampling.
- Full task wall time includes preparation before the CLI, CLI/model/tool lifecycle, final readback and cleanup. Raw usage fields, cache write if exposed, and prompt-to-final remain separate. Missing fees/provider-internal metrics are not estimated as observed.
- A/B spatial paths are identical; any observed A/B timing difference is not evidence of a new spatial algorithm.

Frozen hashes:

- driver.py: c1125ef39231a51c1b8b73032e30a521b24e33900567388a944e2966850f27a5
- consumer_transport.py: 3cf0d79b962067dd41cbbfa7ddc51cca26886bd095eecb191428f0f057a25db5
- actor.py: f8fcb8f3afa44fccbbd3af33cba70bba20700cb8b05999f12d72fe02ebe4b85c

The above establishes the frozen design and routing, not success of future consumer answers. Current-run initial and final geometry and observed tools still require review.
