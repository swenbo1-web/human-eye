"""Finalize cost conclusion with explicit synthetic stdout evidence limits."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
old=json.loads((HERE/'FINAL_RESULTS.json').read_bytes())
correction=json.loads((HERE/'SCHEMA_CLARIFICATION.json').read_bytes())
remaining=correction['failed']
assert len(remaining)==3 and all(r['original_check'].startswith('local/')and r['original_check'].endswith('_raw_len_matches_canonical_event')for r in remaining)
newline=[]
for row in remaining:
    _,arm,kind=row['original_check'].split('/')
    num=int(kind.split('_')[0][4:]);d=BASE/'local/a01'/arm
    events=[json.loads(line)['event']for line in(d/'c/events.jsonl').read_bytes().splitlines()]
    event=[e for e in events if e['type']=='item.completed'and e.get('item',{}).get('type')=='mcp_tool_call'][num-1]
    expected=len(json.dumps(event,ensure_ascii=False).encode('utf8'))+2
    observed=row['detail']['counter']
    assert expected==observed
    newline.append(dict(original_check=row['original_check'],spaced_JSON_plus_CRLF_bytes=expected,recorded_len_raw=observed,
        interpretation='Counter is consistent with Windows Python print CRLF. Raw stdout bytes were not retained, so this is reconstruction/counter consistency, not an exact raw-file comparison.'))
out={k:v for k,v in old.items()if k not in('verdict','corrected_checks','unresolved_cost_discrepancies')}
out.update(verdict='pass_recorded_cost_arithmetic_and_consistency',original_valid_checks=447,
    format_corrections_verified=30,synthetic_stdout_counter_consistency_checks=3,
    author_cost_discrepancies_found=[],remaining_evidence_limits=newline,
    actual_real_model_runs_verified=2,experiment_runs_added_by_reviewer=0,
    reader_note='Use COST_ACCEPTANCE.json as final decision. All preceding failed parser and schema interpretations remain archived, not overwritten.')
out['unmeasured'].append('Exact raw CLI stdout bytes (events are parsed/re-serialized; original len(raw) counters retained and reconstructed separately).')
out['notes'].append('Synthetic fixture uses spaced JSON plus Windows print CRLF; real CLI compact JSON plus LF. Keep these byte scopes separate.')
with(HERE/'COST_ACCEPTANCE.json').open('x',encoding='utf8',newline='\n')as stream:json.dump(out,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(verdict=out['verdict'],checks=447,format_corrections=30,synthetic_CRLF_consistency=3,sha256=hashlib.sha256((HERE/'COST_ACCEPTANCE.json').read_bytes()).hexdigest())))
