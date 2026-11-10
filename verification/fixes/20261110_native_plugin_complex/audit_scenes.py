"""Independent comparison of fresh readbacks against the frozen initial source."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_bytes())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def oriented_faces(faces):
    return Counter(min(tuple(f[i:] + f[:i]) for i in range(len(f))) for f in faces)

def compare(reference, observed):
    checks = {'unit_scale_m': reference['unit_scale_m'] == observed['unit_scale_m']}
    expected = {o['name']: o for o in reference['objects']}
    actual = {o['name']: o for o in observed['objects']}
    checks['object_set'] = set(expected) == set(actual)
    for name, wanted in expected.items():
        if name not in actual:
            continue
        got = actual[name]
        for key in ('vertices_local', 'matrix_world'):
            checks[name + '.' + key] = wanted[key] == got[key]
        checks[name + '.oriented_faces'] = oriented_faces(wanted['faces']) == oriented_faces(got['faces'])
        scale = observed['unit_scale_m']
        matrix = got['matrix_world']
        world = [[(sum(matrix[i][j] * v[j] for j in range(3)) + matrix[i][3]) * scale
                  for i in range(3)] for v in got['vertices_local']]
        checks[name + '.world_vertices'] = world == wanted['world_vertices']
    return {'passed': all(checks.values()), 'checks': checks}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    source = args.evidence / 'private' / 'author_mesh_snapshots.json'
    assert digest(source) == '5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14'
    reference = read(source)['initial']
    rows = []
    for filename in ('INITIAL.json', 'FINAL.json'):
        for path in sorted(args.evidence.rglob(filename)):
            observed = read(path)
            if not isinstance(observed, dict) or 'objects' not in observed:
                continue
            rows.append({'path': str(path), 'sha256': digest(path), **compare(reference, observed)})
    result = {'method': 'independent stdlib source comparison, no author comparison function imported',
              'source_sha256': digest(source), 'observations': len(rows),
              'all_observed_passed': bool(rows) and all(row['passed'] for row in rows), 'rows': rows}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))

if __name__ == '__main__':
    main()
