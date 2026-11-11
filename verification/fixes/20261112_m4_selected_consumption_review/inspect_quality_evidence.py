import json
import sys
from pathlib import Path

PUB = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_selected_geometry_consumption_001/runtime/handoff_01/public')
rows = json.loads((PUB/'INDEX.json').read_bytes())['answers']
for row in rows[int(sys.argv[1]):int(sys.argv[2])]:
    print(row['anonymous_id'])
    obj = json.loads((PUB/row['directory']/'tool_evidence.json').read_bytes())
    for attempt in obj['owner_attempts']:
        print('REQUEST', attempt['order'], json.dumps(attempt['request']['params'], ensure_ascii=False))
        for response in attempt['responses']:
            value = response['value']
            blocks = value.get('result', {}).get('content', [])
            for block in blocks:
                raw = block.get('text', '')
                try:
                    decoded = json.loads(raw)
                except (ValueError, TypeError):
                    decoded = raw
                if isinstance(decoded, dict) and isinstance(decoded.get('result'), dict) and isinstance(decoded['result'].get('result'), str):
                    raw = decoded['result']['result']
                    try:
                        inner = json.loads(raw)
                        if isinstance(inner, list) and len(inner) == 28:
                            inner = [x for x in inner if x.get('name') in {'N04','N08','N10','N12','N13','N15','N16','N18','N19','N24','N25','N28'}]
                        raw = json.dumps(inner, ensure_ascii=False)
                    except (ValueError, TypeError, AttributeError):
                        pass
                    # Full selected geometry outputs; omit only unrelated catalogue lines.
                    lines = raw.splitlines()
                    if len(lines) >= 28 and 'mesh G' in raw:
                        keep = {'N04','N08','N10','N12','N13','N15','N16','N18','N19','N24','N25','N28'}
                        raw = '\n'.join(x for x in lines if x.split(' ',1)[0] in keep or x.startswith('units'))
                    print('RESPONSE', raw)
                else:
                    if isinstance(decoded, dict) and 'measurement_contracts' in decoded:
                        decoded = {k:v for k,v in decoded.items() if k in {'target','candidates','geometry','selected_geometry','measurement_contracts','status'}}
                        for candidate in decoded.get('candidates', []):
                            for key in list(candidate):
                                if key not in {'name','aabb','closed_solid_relation','surface_proximity','geometry'}:
                                    candidate.pop(key)
                        def short(x):
                            if isinstance(x, float): return round(x, 9)
                            if isinstance(x, list): return [short(v) for v in x]
                            if isinstance(x, dict): return {k:short(v) for k,v in x.items() if k not in {'object_id','instance_id','topology','triangle_scope','publication_tolerance_m'}}
                            return x
                        decoded = short(decoded)
                    print('RESPONSE', json.dumps(decoded, ensure_ascii=False))
