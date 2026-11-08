"""Report finished RUN006 public accounting; no answer scoring or replay."""
from pathlib import Path
import hashlib
import json

RUN = Path(__file__).resolve().parents[1]
OUT = RUN / 'actual_invocation_001'
load = lambda name: json.loads((OUT / name).read_bytes())


def main():
    counts = load('COUNTS_AUDIT.json')
    outer = counts['outer_controller']
    assert outer['process_reaped'] is True
    assert counts['scheduled_slots'] == 8
    rows = []
    for slot in counts['slots']:
        clock = slot.get('clocks', {})
        seconds = lambda key: None if clock.get(key) is None else clock[key] / 1e9
        rows.append(f"| {slot['ordinal']} | {slot.get('task_id')} | {slot.get('arm')} | "
                    f"{slot.get('status')} | {seconds('whole_cell_ns')} | {seconds('consumer_wall_ns')} |")
    public = sum(s.get('ledger', {}).get('public_text_bytes', 0) for s in counts['slots'])
    logical = sum(s.get('final_artifact', {}).get('logical_final_ledger_utf8_bytes', 0) for s in counts['slots'])
    artifacts = sum(s.get('final_artifact', {}).get('bytes', 0) for s in counts['slots'])
    preparation = json.loads((RUN / 'PREPARATION.json').read_bytes())
    precheck = load('PRECHECK.json')
    sections = []
    for filename in ('COUNTS_AUDIT.md', 'COLLAB_AUDIT.md', 'CLEANUP_AUDIT.md'):
        text = (OUT / filename).read_text(encoding='utf8')
        lines = text.splitlines()
        if lines and lines[0].startswith('# '):
            lines[0] = '#' + lines[0]
        sections.append('\n'.join(lines))
    report = f"""# CONSUMPTION-RUN-006 actual delivery

The single authorized frozen eight-slot invocation is finished. Original result states: {counts['slot_status_counts']}. Received/saved finals: {counts['answers_received']}/{counts['final_artifacts']}; frozen valid completions: {counts['valid_completion_count']}. These are controller checks. This author did not interpret final answers or truth, assign quality scores, or conclude engine benefit. Root must assess answer quality before combining costs.

All seven prepared files were copied exactly. Fixed candidate 0ad59befeee43c2fad752e3bad2ee69f87af3136 retains each original triangle face as its closed point/segment/triangle hull in the accepted exact kernel. Name entry, prompts and the accepted public collaboration meter are unchanged. This single comparison examines T04 HE completion and subsequent native call ordering; T01-T03 are shared-kernel controls. Original four tasks, N/P order NP/PN/NP/PN, native Python/image capability, gpt-6.1-sol/ultra/openai_http/default, existing Pro login, 180-second answer deadlines and budgets were retained. The eight contexts are scheduled slots. No additional qualification consumer, mock, retry, replacement answer, wording candidate or inline runtime repair was performed.

Standing user authorization and the granted fixed window supply current execution authority. Historical pending-window text in the exact copied package is retained. The approved two tools apply to isolated copies and per-process settings. Google/paid API remains paused. Original/shared assets, GUI/default9876, competitor branches and global settings were untouched. This task did not write STATE or release root's window.

{sections[0]}

The counts audit's public-tool count covers regular experiment/MCP actions. The dedicated collaboration projection reports its additional identifiable calls and lifecycle-event counts separately. Neither establishes a complete backend request count.

## Time and byte boundaries

Outer controller: {outer['started_utc']} to {outer['ended_utc']}; complete Popen/wait/reap wall {outer['wall_ns']/1e9:.7f}s. Runner wall through result construction: {counts['runner_wall_ns']/1e9:.7f}s. STARTED, OWNED_PROCESS and RESULT preserve exact argv, approval and owner receipt. Original diagnostics, failures, unavailable fields and follow-up calls remain in the raw evidence.

| Slot | Task | Arm | Original status | Whole cell seconds | Consumer through cleanup seconds |
|---|---|---|---|---:|---:|
{chr(10).join(rows)}

Slot startup/tool/final/exit/cleanup clocks are nested local observations. They must not be added to the enclosing wall. Root package preparation measured {preparation['elapsed_ns']/1e9:.7f}s; local exact-copy/precheck measured {precheck['elapsed_ns']/1e9:.7f}s. Those are separate operations and do not represent all project preparation. MANAGEMENT_START and MANAGEMENT_CLOCK record this management turn's elapsed lower bound through sealing, including preparation, the nested invocation and parallel audits. Commit/callback tail and earlier turns remain outside that cutoff. Author/reviewer tokens and fees are unmeasured.

Physical RPC wire totals TX/RX: {counts['physical_RPC_TX_bytes']}/{counts['physical_RPC_RX_bytes']} B. Public-text ledger: {public} B; logical final UTF-8: {logical} B; saved final artifact: {artifacts} B. CRLF expansion is a storage boundary. Catalogue/schema, descriptor, transport, public text and saved artifact sizes are distinct, overlapping observations; none is inferred to equal provider tokens. Effective model-delivered schema remains unexposed.

Terminal main-context input/cached/output usage is counted once per context; cached is part of input. Collaboration usage is incomplete as detailed below. Provider request count, actual backend and fees remain null/unexposed. No Pro dollar estimate or unknown-to-zero conversion is made. Image observations, including any zero counts, are limited to the recorded public image boundary.

{sections[1]}

{sections[2]}

## Identity, preservation and scope

Baseline HEAD b24e277ceb315289ed1028913e1dc61972651f7b; fixed product commit 0ad59befeee43c2fad752e3bad2ee69f87af3136. The 131-source canonical SHA256 is 82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6. SOURCE_AUDIT checks seven exact prepared files, 17 dependencies, new ZIP/current source bytes and protected assets/helper. New PRODUCT_BYTES.zip SHA256: 7c0e84065e7390a711c49010a911b05bb836a8b617cf73e2f1d83baa0fa99590.

PACKAGE SHA256 de0404bc2641287fef9927a956bcf4a8e6e77a044e839bff42b86006401eadec; PLAN e5e4ce88f2b29618523a7779568ab66117f8c6512b04f9042bb390e0d2de1d00; approval ea8c7f1cb73d024169936564e4e1e33b7c0474dd57e75be19e3aab1ccd830b68. PREPARATION and six authority/review/assignment snapshots retain their exact original bytes.

NEUTRAL_RAW.zip and its member index preserve all files in this run's private neutral root. No source was deleted or moved. PRESERVATION pins this run's unmodified original outputs and older tracked markers. RUN001–005, both M1 offline attempts/raw QA and the degenerate-surface first/final audit originals remain unchanged. EVIDENCE_INDEX covers new evidence except itself and bytecode/cache. Final Git HEAD and report/index hashes follow in the single completion callback after verifying staged and committed blobs. This bounded batch ends with that callback; root independently scores and selects any next work.
"""
    (RUN / 'REPORT.md').write_text(report, encoding='utf8', newline='\n')
    print(json.dumps(dict(report_sha256=hashlib.sha256((RUN / 'REPORT.md').read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
