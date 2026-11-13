"""Resolve one documented reviewer schema error, preserving initial output verbatim."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_003')
OUT=Path(r'D:/hefe/verification/fixes/20261113_m4_active_coverage_003_review/cost')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=read(OUT/'RESULTS.json')
assert len(r['failures'])==1 and r['failures'][0]['name']=='control_B.BACK_64'
cameras=read(ROOT/'inputs/CAMERAS_PIXEL_SHORTFALL.json')
main=read(ROOT/'runs/main_p01_B/RESULT.json')['frames'][1]['pose']
control=read(ROOT/'runs/control_B/RESULT.json')['frames'][1]['pose']
checks=[
 {'name':'preregistered_span_factor_64','passed':cameras['pixel_shortfall_control']['span_factor']==64},
 {'name':'resolution_unchanged_512','passed':control['size_px']==main['size_px']==[512,512]},
 {'name':'actual_binary64_span_exact_scale_64','passed':Fraction.from_float(control['span'])==64*Fraction.from_float(main['span'])},
 {'name':'actual_binary64_halfspan_exact_scale_64','passed':Fraction.from_float(control['half_span_m'])==64*Fraction.from_float(main['half_span_m'])},
 {'name':'registered_control_camera_matches','passed':next(v for v in cameras['views'] if v['name']=='BACK')==control},
]
assert all(c['passed'] for c in checks)
qcost={}
for case in ['normal','nonzero','timeout','receipt_failure']:
    folder=ROOT/'qualification'/case
    files=[p for p in folder.rglob('*') if p.is_file()]
    qcost[case]={'stored_files':len(files),'stored_bytes':sum(p.stat().st_size for p in files),
                'stdout_bytes':(folder/'stdout.bin').stat().st_size,'stderr_bytes':(folder/'stderr.bin').stat().st_size,
                'PNG_files':len(list(folder.rglob('*.png'))),'NPZ_files':len(list(folder.rglob('*.npz')))}
qcost['whole_qualification_directory']={'stored_files':sum(p.is_file() for p in (ROOT/'qualification').rglob('*')),
  'stored_bytes':sum(p.stat().st_size for p in (ROOT/'qualification').rglob('*') if p.is_file())}
supp={'reason':'Reviewer initially interpreted BACK64 as 64 pixels. Registered input and REPORT state that the orthographic span is enlarged by 64 while the image remains 512x512. This is a reviewer expectation error, not an author experiment failure.',
      'original_failure_preserved_in':'RESULTS.json and CHECKS.json','original_failure':r['failures'][0],
      'original_script_sha256':digest(OUT/'audit_cost.py'),'original_results_sha256':digest(OUT/'RESULTS.json'),
      'corrective_checks':checks,'qualification_storage':qcost,
      'modified_experiment_files':0,'new_engine_image_performance_model_runs':0,
      'disposition':'Initial 7339 valid checks passed; the one invalid expectation is replaced by these five explicit checks. No experiment rerun or denominator change.'}
save('CONTROL_CLARIFICATION.json',supp)
final={'cost_record_audit':'pass','scope':'Recorded file/counter/timing consistency and exact cost arithmetic only. Full acceptance requires root source/geometry/pixel review.',
       'valid_initial_checks_passed':r['checks_passed'],'invalid_initial_expectations':1,'corrective_checks_passed':len(checks),'unresolved_author_cost_discrepancies':[],
       'initial_results':'RESULTS.json','clarification':'CONTROL_CLARIFICATION.json','author_commit':r['author_commit'],
       'median_pair_B_over_A':r['median_pair_B_over_A'],'timing':r['timing'],'groups':r['groups'],'unmeasured':r['unmeasured'],
       'reviewer_run_count':2,'reviewer_run_count_scope':'One offline original cost audit and one offline schema clarification only. No author function invoked.'}
save('FINAL_RESULTS.json',final)
t=r['timing'];a=r['groups']['main_A'];b=r['groups']['main_B'];allr=r['groups']['all_003']
lines=[
 '# Independent cost review — M4-ACTIVE-COVERAGE-003',
 '',
 f"Fixed author commit: `{r['author_commit']}`. This review only reads existing records and binary payloads. It does not import the author's runner, validator, scorer or cost review, and runs no renderer, Blender, model or performance sample.",
 '',
 '**Verdict: recorded cost arithmetic and per-run provenance/timing/count consistency pass.** The full geometry/pixel and source-identity decision belongs to the root review.',
 '',
 'The initial audit passed 7,339 valid checks and recorded one reviewer schema mistake: BACK64 means a 64× orthographic span, not a 64×64 image. Both registered input and actual control remain 512×512. The original failure and script are retained unchanged; CONTROL_CLARIFICATION.json supplies five passing explicit corrective checks. No result, threshold, sample or denominator was changed.',
 '',
 '## Exact paired result',
 '',
 'All 12 preregistered main runs completed in alternating AB/BA order, forming six pairs. Both controls completed separately. There are no discarded or added 003 runs.',
 '',
 '| Pair | A full interval (ms) | B full interval (ms) | B/A |',
 '|---:|---:|---:|---:|',
 ]
for p in r['pairs']:lines.append(f"| {p['pair']} | {p['A_ns']/1e6:.4f} | {p['B_ns']/1e6:.4f} | {p['B_over_A']['decimal']:.9f} |")
lines += [
 '',
 'Median of paired B/A ratios = **231227282996199 / 313740308347526 = 0.7370021538324989**, a **26.2998%** reduction. All six pairs favor B. A median = 1223.2421 ms; B median = 916.05375 ms. Ratio of arm medians = 0.7488736285319153, a 25.1126% reduction; this is a different statistic.',
 '',
 'Primary time starts immediately before Popen and ends after process exit, owned-handle cleanup and parent result/PNG/NPZ/trace verification. Command/output-directory preparation and frozen-source checks outside that interval remain in the separate whole-batch window. Every recorded stage and trace event is inside its original process interval; actual result/launch/trace PID, output directory, scene/camera hashes and published result digests agree.',
 '',
 '## Count and byte ledger',
 '',
 '| Cost, six main runs per arm | A | B |',
 '|---|---:|---:|',
 f"| New full-scene renders | {a['render_attempts']} | {b['render_attempts']} |",
 f"| Returned child pixel rows | {a['pixel_rows_returned']} | {b['pixel_rows_returned']} |",
 f"| PNG bytes | {a['PNG_bytes']} | {b['PNG_bytes']} |",
 f"| Compressed NPZ bytes | {a['NPZ_bytes']} | {b['NPZ_bytes']} |",
 f"| Raw ndarray payload bytes | {a['array_payload_bytes']} | {b['array_payload_bytes']} |",
 f"| RESULT + TRACE + frame metadata + publication bytes | {a['text_artifact_bytes']} | {b['text_artifact_bytes']} |",
 f"| All stored per-run artifact bytes | {a['stored_payload_bytes']} | {b['stored_payload_bytes']} |",
 '',
 'Both main arms report six discovered regions, five actually covered and one unresolved region outside the finite camera pool. A uses SCENE/TOP/LEFT/RIGHT/FRONT/BACK; B uses SCENE/BACK. Same-version repeat query generates zero additional images. These set/count claims agree between raw records; independent pixel/geometry correctness is reviewed separately.',
 '',
 'Controls cost 10 additional renders (A six; B four). B follows SCENE→BACK→LEFT→TOP, adding 2/0/2/1 regions. BACK has three geometric-complete candidates but zero readable pixel rows; its history of three shortfalls remains while final pixel shortfall is empty. New 003 cost is **58 renders**, below 60. The failed 002 retains its six renders, making **64/66** across the two batches.',
 '',
 f"All 14 new runs store {allr['PNG_bytes']} PNG bytes, {allr['NPZ_bytes']} NPZ bytes, {allr['text_artifact_bytes']} text-artifact bytes and {allr['array_payload_bytes']} raw array payload bytes. All formal stdout/stderr files are empty. Raw payload is the sum of generated arrays, not peak resident memory. Local text bytes are not model tokens.",
 '',
 'Four no-image qualification processes are accounted separately, each once: normal, nonzero, timeout and receipt failure. Actual Popen/child/handshake/environment PID agrees for all four; cleanup/streams/handle closure records are consistent. Timeout keeps its original 250 ms post-handshake deadline. Receipt failure retains the one executed harmless marker and does not retry it. Qualification storage detail is in CONTROL_CLARIFICATION.json.',
 '',
 '## Full recorded windows and exclusions',
 '',
 '| Window | Seconds |',
 '|---|---:|',
 ]
for label,key in [('12 main full process intervals','main_primary_sum_ns'),('2 control full process intervals','control_primary_sum_ns'),('Formal whole batch through analysis','formal_whole_batch_through_analysis_ns'),('Formal common parent setup, included above','formal_common_setup_ns'),('Formal overhead outside primary intervals, included above','formal_outside_primary_total_ns'),('Qualification incl. RESULTS write/close','qualification_including_RESULTS_writeclose_ns'),('Qualification + formal recorded windows','qualification_plus_formal_recorded_windows_ns'),('Unclassified gap after qualification before formal batch','gap_qualification_end_to_formal_start_ns'),('Wall-clock span from qualification start through formal analysis','span_from_qualification_start_to_formal_analysis_end_ns'),('Old failed 002 whole batch, separately retained','old_002_whole_window_ns'),('002 + 003 sum of recorded active windows','cross_002_003_recorded_windows_ns')]:
    lines.append(f"| {label} | {t[key]/1e9:.7f} |")
lines += [
 '',
 '**19.6571529 seconds is the sum of two measured windows, not the entire development/preparation/model end-to-end time.** The intervening 128.6634619-second wall-clock gap has no reliable compute attribution. Controller startup/initial imports/FROZEN read, final self-publication, development and review time are not measured. They must not be silently described as zero.',
 '',
 'The old 002 still has one failed main slot, eleven unrun main slots and two unrun controls; failed-slot time 1.0759542 s and batch time 1.2057816 s remain charged. Its PID ancestry remains unknown. It is not merged into the successful 003 denominator or retroactively relabeled passed.',
 '',
 '## What this establishes',
 '',
 'For this fixed small rectangular-region / six-camera engineering workload, two selected views reduce complete child-process time by about 26% and the render count by two thirds, despite paying the same startup, import and geometry-index work. Summed dependency imports remain 2.9005 s for A and 2.9510 s for B across six runs; B does not gain by bypassing these costs. This is evidence for acquisition efficiency, not a measured native-model comparison or generic human-like visual understanding.',
 '',
 'Not measured: model answer quality, model input/output tokens, rounds, inference latency and price; semantic texture recognition; generic task coverage; peak RSS/heap; OS-cold-cache behavior. No external model/API/Blender call was added in this review or in the registered 003 experiment.',
 '',
 'Reproduction: run audit_cost.py in a fresh output directory or change its output destination; it writes exclusively and will not overwrite these audit records. The follow-up clarification only resolves the explicitly preserved reviewer schema error. All original evidence remains read-only.',
 ]
with (OUT/'REVIEW.md').open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'verdict':final['cost_record_audit'],'corrective_checks':checks,'qualification_storage':qcost,'report':str(OUT/'REVIEW.md')},ensure_ascii=False,indent=2))
