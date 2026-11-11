"""Derive visible byte attribution from the independently verified cost result; no new measurements."""
import hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
raw=(p/'RESULTS.json').read_bytes();d=json.loads(raw);groups={}
for group in ('N','P','G'):
    rows=[r for r in d['cells'] if r['group']==group]
    groups[group]={'tools_list_response_wire_bytes_per_cell':[r['tools_list_response_wire_bytes'][0] for r in rows],
        'tools_list_response_wire_total':sum(r['tools_list_response_wire_bytes'][0] for r in rows),
        'native_tool_response_bytes':sum(t['response_bytes'] for r in rows for t in r['tools'] if t['name']=='execute_blender_code'),
        'relation_tool_response_bytes':sum(t['response_bytes'] for r in rows for t in r['tools'] if t['name']=='human_eye_spatial_relations'),
        'all_tool_response_bytes':sum(r['tool_response_bytes'] for r in rows),
        'actual_input_tokens':sum(r['usage']['input_tokens'] for r in rows),'actual_output_tokens':sum(r['usage']['output_tokens'] for r in rows),
        'cached_input_subset':sum(r['usage']['cached_input_tokens'] for r in rows),
        'uncached_input_arithmetic':sum(r['usage']['input_tokens']-r['usage']['cached_input_tokens'] for r in rows)}
diffs={g:{k:groups['G'][k]-groups[g][k] for k in groups['G'] if not isinstance(groups['G'][k],list)} for g in ('P','N')}
result={'source_RESULTS_sha256':hashlib.sha256(raw).hexdigest(),'groups':groups,'G_minus_reference':diffs,
 'scope':'MCP wire-visible byte differences; not exact provider/model token attribution.',
 'can_conclude':'Both schema and response bytes increase for G; observed total input token differences also depend on repeated context, number of calls, outputs and caching.',
 'cannot_conclude':'No segmented provider usage exists, so no exact number of additional tokens or seconds can be assigned to schema versus geometry responses.',
 'new_runtime_calls':0}
with (p/'VISIBLE_BYTES.json').open('x',encoding='utf8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(result,ensure_ascii=False))
