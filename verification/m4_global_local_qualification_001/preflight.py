"""Source-only checks before the fixed fixture and actual requests are frozen."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PRIOR = HERE.with_name('m5_harness_recovery_001')


def main():
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))

    for path in sorted(HERE.rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        ast.parse(path.read_bytes())
        check('parse/' + path.relative_to(HERE).as_posix(), True)
    original = ast.parse((PRIOR / 'harness/owned_runtime.py').read_bytes())
    current = ast.parse((HERE / 'harness/owned_runtime.py').read_bytes())
    for name in ('correlate_archive', 'public_request', '_start_mcp', 'close', 'scene_data'):
        left = next(node for node in ast.walk(original) if isinstance(node, ast.FunctionDef) and node.name == name)
        right = next(node for node in ast.walk(current) if isinstance(node, ast.FunctionDef) and node.name == name)
        check('reviewed_method_AST/' + name, ast.dump(left) == ast.dump(right))
    baseline = json.loads((HERE / 'BASELINE.json').read_bytes())
    for row in baseline['copied_inputs']:
        check('byte_copy/' + row['copy']['path'],
              Path(row['copy']['path']).read_bytes() == Path(row['original']['path']).read_bytes())
    binding = json.loads((HERE / 'B_RUN_BINDING.json').read_bytes())
    for row in binding['source_manifest']:
        check('installed_source/' + row['path'], hashlib.sha256(
            (Path(binding['install_root']) / row['path']).read_bytes()).hexdigest() == row['sha256'])
    for path, expected in json.loads((HERE / 'SHARED_DEPENDENCY.json').read_bytes())['files_sha256'].items():
        check('shared_dependency/' + path, hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected)
    record = dict(schema='m4-global-local-preflight-v1', passed=all(row['passed'] for row in checks),
                  checks=checks, actual_owned_starts=0, actual_rasters=0, model_calls=0,
                  note='Preserved product request, archive correlation, lifecycle and original raw source read methods. Fixed asset context and the direct no-model caller are new.')
    with (HERE / 'PREFLIGHT.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=record['passed'], checks=len(checks))))
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
