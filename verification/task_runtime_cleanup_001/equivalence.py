"""Compare saved baseline/candidate checks and record every differing leaf."""
import json
from pathlib import Path
import sys
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from timing import normalized
a = json.loads((OUT / 'baseline_checks.json').read_bytes())['rows']
b = json.loads((OUT / 'candidate_checks.json').read_bytes())['rows']
EXCLUDED = {'counts'}
def diff(a, b, path=''):
    if type(a) != type(b): return [(path, a, b)]
    if isinstance(a, dict):
        return sum((diff(a.get(key), b.get(key), path + '/' + key) for key in a.keys() | b.keys()
                    if key not in EXCLUDED), [])
    if isinstance(a, list):
        if len(a) != len(b): return [(path + '/length', len(a), len(b))]
        return sum((diff(x, y, path + '/' + str(i)) for i, (x, y) in enumerate(zip(a, b))), [])
    return [] if a == b else [(path, a, b)]
rows = [{'test': x['test'], 'diff': diff(normalized(x), normalized(y))} for x, y in zip(a, b)]
(OUT / 'EQUIVALENCE.json').write_text(json.dumps(rows, indent=2), encoding='utf8')
print(json.dumps({'paired_rows': len(rows), 'differences': rows}, indent=2))
assert len(a) == len(b) and not any(row['diff'] for row in rows)
