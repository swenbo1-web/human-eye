# M4-DEFAULT-LATENCY-ATTRIBUTION-001 frozen experiment

## Question and fixed sources

Measure the original default relation request under the same request history with the owned Blender QA profiler enabled or disabled. The previous a81 observation of +1.341 ms remains sealed. This experiment describes one controlled condition and keeps the previous admission decision intact.

Version B is e077fce38b5951efff8166b3b688d05ffa2ebf04, 137 sources, canonical 53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732. Version C is a81e530a03460f93846e3bef4c45ebaa9347531b, 137 sources, canonical 9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504. Reuse their existing accepted isolated installation receipts and wheels. Verify every installed runtime source, entry, dependency identity and loaded identity. The implementation checkout remains 00b13060 / 4ebc3910. That schema revision is outside this performance matrix.

The asset is the original owned-copy scene.blend, SHA-256 91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85. Every business call uses the existing compact human_eye_spatial_relations interface with target N16, candidates N13/N08/N28, and the existing two mandatory relation facts. SCHEDULE.json fixes the exact request template and all 88 request positions.

## Fixed order and boundaries

Run four sequential fresh owned sessions B, C, C, B. Each has one cold request and one separate warmup, both with the QA profiler OFF. Then run ten pairs of identical business requests. Odd pairs use the session's initial ordering, even pairs reverse it. Sessions 1 and 2 begin ON then OFF. Sessions 3 and 4 begin OFF then ON. Each session therefore has ten measured ON requests and ten measured OFF requests, five in each pair position per state.

Worker sequences 1..22 correspond one-to-one to these business requests. Sequence 23 is the ordinary close operation with the profiler OFF. Initialization, initialized notification, tools/list and ping are the four fixed metadata stdio messages. They require zero Blender RPC. All control traffic and any unexpected traffic remain in the accounting. Unexpected worker traffic stops the matrix.

The first owned Blender launch reservation starts the measurement matrix. There are at most four launch attempts. Preparation errors before that boundary may be corrected with their records retained. Once measurement begins, a failed launch or session ends the matrix. Subsequent planned sessions remain unrun. There are no replacement sessions or additional samples.

## Sole QA state change

Keep the existing host_work sampling, scene fingerprints, source and file protections, time limits, response publication, event writing and process cleanup. Both modes construct the same before/after sampling state and callback closure. ON installs the original counting callback. OFF skips callback installation and marks Python/C callback counts null and not_collected. Existing residency and product trace counters remain available in either mode.

Inspect and record sys.getprofile before each request. An initial value other than None causes a recorded stop while preserving that profile. ON restores its initial state in the protected exit path. If another callback replaces the owned callback, preserve the observed foreign callback and stop. A callback exception, lost callback, failed restoration, pre-probe failure or post-probe failure also records a stop. State must be attached to the worker event before any operation that could fail. Before/after exceptions must enter owned-process cleanup.

The ON and OFF records have their natural count representations. Consequently, their measured difference includes the QA profiler state and its count-recording path. Keep this distinction when interpreting timings. The profile_scope interval includes host execution, so it remains an inclusive duration in the report.

Profile schedule selection happens in the QA worker using its frozen sequence. The product request and sources are read-only. Validate each completed business call immediately against its worker sequence, planned and actual profile state, restoration record, source identity, capture generation, facts and expected response. An exception or mismatch ends the matrix. Existing shared GUI sessions alone do not constitute a resource conflict. A concrete owned-resource conflict or unexplained state change is recorded and stops execution.

## Evidence and timing

Before the first session, commit this contract, the exact QA sources, their input pins, SCHEDULE.json, analysis/ANALYSIS_RULES.json and passing static/unit records. Unit checks cover OFF sampling, ON callback behavior, an existing foreign profiler, business and callback exceptions, restoration mismatch and protected cleanup. Review the worker diff to establish continued fingerprint, protection, timing and lifecycle paths.

Save each actual stdio request/response and host receipt. Record source version, worker sequence, capture generation, phase, pair index, pair position, current and previous logical profile mode, initial/active/final profiler state, cache flags, host residency counts, available callback counts and product trace spans. Callback counts in OFF remain uncollected. The prior limitation of invisible bpy C method names remains explicit.

The existing Peer receipt records its interval before final receipt and RPC-log publication. The outer entry interval includes that publication. Record these nested durations separately. Subsequent immediate QA validation has its own duration and contributes to total session time. In this QA helper, before_probe includes profile installation and its state checks, after_probe includes restoration checks, and profile_scope starts when the state is created before sampling. These inclusive intervals overlap. Their exact boundaries belong to this batch. Report them separately, preserve their overlap and keep comparisons within this experiment.

Record complete preparation, source validation, owned Blender startup, product startup, metadata, PID proof, business request, immediate verification and cleanup wall times. Reuse the existing Windows process-handle proof for the actual product runtime PID from its startup trace, and verify exit using that same handle. Blender READY remains bound to its owned Popen PID. These operations add no host RPC. Report process-lifetime peak RSS where available and its scope.

If actual runtime exit remains unconfirmed, preserve its original PID, creation time and verified ownership proof. Stop the matrix and let the root finish that owned child's cleanup within the original deadline, rechecking identity before termination. Record the cleanup outcome separately. A stopped experiment alone does not establish completed process cleanup.

## Frozen analysis and exit

Check facts, provenance, one-to-one RPC mapping, profile state, restoration and expected cold/warm work before interpreting timing. Show all cold and warmup rows separately. For each session, report the ten ON values and ten OFF values, medians, ranges and ten paired ON-minus-OFF differences. Show pair position and previous-profile strata to expose carryover.

Use the two sessions per version as the version-level units. Compare matching initial-order blocks B1/C2 and B4/C3, reporting ON and OFF version differences. Their interaction is the difference between those two mode-specific version differences. Also report equal-weight session summaries and the raw per-session values. A median of paired differences and a difference of group medians are distinct quantities.

Keep all samples, make no stable p95 estimate and introduce no significance-based equivalence or new allowed percentage. A one-time finding may be persistent difference, profile/order dependence or unresolved attribution. The previous experiment remains unaltered, and the new 4eb source does not acquire same-version performance validation from these old installations.

This batch has zero new installations, model consumers, images, paid API calls or product edits. Protect existing assets, defaults, shared GUI and other branches. After the fixed matrix or its stopping condition, save and commit all evidence, send ATTRIBUTION_READY to the administrator and end this batch. Further performance changes, consumers and modules require a new delegated task.
