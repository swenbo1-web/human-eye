"""Assemble final public audit measurements; no answer interpretation or replay."""
import hashlib
import json
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
OUT = RUN / 'actual_invocation_001'
counts = json.loads((OUT / 'COUNTS_AUDIT.json').read_bytes())
outer = counts['outer_controller']
assert outer['process_reaped'] is True
assert counts['scheduled_slots'] == 8
clock_rows = []
for slot in counts['slots']:
    clock = slot.get('clocks', {})
    seconds = lambda key: None if clock.get(key) is None else clock[key]/1e9
    clock_rows.append(f"| {slot['ordinal']} | {slot.get('task_id')} | {slot.get('arm')} | "
                      f"{seconds('whole_cell_ns')} | {seconds('consumer_wall_ns')} |")
public_text = sum(slot.get('ledger', {}).get('public_text_bytes', 0) for slot in counts['slots'])
logical_final = sum(slot.get('final_artifact', {}).get('logical_final_ledger_utf8_bytes', 0) for slot in counts['slots'])
artifact_final = sum(slot.get('final_artifact', {}).get('bytes', 0) for slot in counts['slots'])
counts_md = (OUT / 'COUNTS_AUDIT.md').read_text(encoding='utf8')
counts_md = counts_md.replace('# RUN004 counts audit', '## Frozen counts and calls', 1)
counts_md = counts_md.replace('## P entry and subsequent native call ordering', '### P entry and subsequent native call ordering')
cleanup_md = (OUT / 'CLEANUP_AUDIT.md').read_text(encoding='utf8')
cleanup_md = cleanup_md.replace('# RUN-004 cleanup audit', '## Resource closure', 1)
report = f"""# CONSUMPTION-RUN-004 actual delivery

One authorized frozen eight-slot invocation is finished. The original result states are {counts['slot_status_counts']}; received/saved finals {counts['answers_received']}/{counts['final_artifacts']}; frozen valid completions {counts['valid_completion_count']}. These are program checks, not quality scores. No final answer or truth was interpreted here, and no engine-benefit or comparative-cost conclusion is made before root scoring.

The six prepared files, including this run's new PRODUCT_BYTES.zip, were copied byte-for-byte. M1's description is the only product variable: generic name/aabb to resolved binding.objects[0].object_id to surface_nearest. Fixed prompts, assets, NP/PN/NP/PN ordering, native capability, model/settings, original 180-second answer deadlines and budgets were retained. No extra features/mock/qualification consumer, operator trial retry, replacement answer, inline controller repair or further wording candidate occurred.

Standing user authorization and the matching granted window supersede the historical pending-approval notes in the unchanged prepared package. Both approved tools remain scoped to isolated test copies and per-process settings. Google/paid API, original/shared assets, GUI/default9876, competitor branches and global settings were untouched.

{counts_md}

## Complete time and byte boundaries

Outer controller start {outer['started_utc']}; end {outer['ended_utc']}. Complete Popen/wait/reap wall is {outer['wall_ns']/1e9:.7f} seconds; runner wall through result construction is {counts['runner_wall_ns']/1e9:.7f} seconds. The full argv/approval/owned PID are in STARTED, OWNED_PROCESS and RESULT. Outer stdout/stderr are empty; original consumer diagnostics and redaction/unavailable fields remain preserved.

| Slot | Task | Arm | Whole cell seconds | Consumer entry through cleanup seconds |
|---|---|---|---:|---:|
{chr(10).join(clock_rows)}

Each slot's startup, public-tool receive, final receive, process exit and cleanup timestamps remain in COUNTS_AUDIT. These are nested local observations and must not be summed. MANAGEMENT_START and MANAGEMENT_CLOCK separately give the management turn's start, preparation before dispatch and elapsed lower bound through sealing. Final commit/callback tail and earlier preparation turns are outside that cutoff. PREPARATION_DIAGNOSTICS records a corrected metadata-helper JSON/null error outside the trial; it did not restart the controller/consumer, and its cost is already inside management elapsed time.

Physical RPC wire totals: TX {counts['physical_RPC_TX_bytes']} B, RX {counts['physical_RPC_RX_bytes']} B. Public-text ledger totals {public_text} B. Logical final text totals {logical_final} UTF-8 B; final artifacts total {artifact_final} B, with Windows CRLF expansions recorded separately. Local catalogue/wire/text bytes are separate boundaries and are not provider-token equivalents. Description UTF-8 length and serialized descriptor bytes are also separate; the actually observed catalogue/descriptor sizes above are retained without inferring them from M1's 18-byte text reduction. Effective model-delivered schema remains unexposed/null.

Observed image payload blocks and bytes are zero; no image construction/delivery CPU duration is inferred. Input/cached/output usage above counts each context's terminal event once; cached is a subset of input. Actual backend, provider request count and fees are unexposed/null. Configured gpt-6.1-sol/ultra/openai_http/default and existing Pro login do not expose those missing values.

{cleanup_md}

## Identity and sealed evidence

Baseline/candidate commit c9594c5534ddc215bb574d8cb65cbcb47f9a701d; 131-source canonical c389562d402f9177feefb9dd77621ed701a88369278c62826036ba641298fca6. SOURCE_AUDIT independently checks all six prepared files, 17 runtime components, new ZIP/disk source bytes, four original assets and helper. This batch uses PRODUCT_BYTES.zip SHA256 2005bbf9d94c3aaddeca6e266aca1546978b2d84ce2205d4b2f5011ff6e5fc19, not the old RUN-001 product archive.

PACKAGE SHA256 7a5f1ce38647993ee3235a72d9310a362420a3023c062200e7d1322240492b69; PLAN f85ead30c6a51cfe18bfe720f2182a8592069b246e876f0d5b88268781bbae30; approval bea0c7d95e0cdd355c12ba4e5d3d3a65aaa262a4597763ac228472f3c39e490b. PRECHECK, standing authorization, approval, root plan, M1 review and assignment snapshots preserve the current authority and original prepared bytes. STATE/window release belongs to root; this task did not write STATE.

NEUTRAL_RAW.zip and its member index preserve every file in this run's private neutral root; no source was deleted or moved. PRESERVATION pins the raw original RUN-004 outputs and old tracked marker files. RUN-001/002/003 and M1 evidence are unchanged; no old result or false cleanup flag is rewritten. EVIDENCE_INDEX covers all new evidence except itself and bytecode/cache, and the final commit/index/report hashes are supplied in the one delivery callback after Git-blob verification. This batch ends here; root independently scores before combining costs and selecting further work.
"""
(RUN / 'REPORT.md').write_text(report, encoding='utf8', newline='\n')
print(json.dumps(dict(report_sha256=hashlib.sha256((RUN/'REPORT.md').read_bytes()).hexdigest(),
                      public_text_ledger_bytes=public_text, logical_final_utf8_bytes=logical_final,
                      final_artifact_bytes=artifact_final)))
