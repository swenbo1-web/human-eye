"""Check existing fixed evidence and index bytes; no product or Blender execution."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    batch = Path(__file__).resolve().parent
    root = batch.parents[1]
    cpu = read(batch / 'cpu_final_03/RESULT.json')
    native = read(batch / 'native_01/RESULT.json')
    audit = read(batch / 'INDEPENDENT_NATIVE_AUDIT.json')
    assert cpu['passed'] and cpu['tests'] == 47
    assert cpu['failures'] == cpu['errors'] == cpu['skips'] == 0
    assert cpu['before_sha256'] == cpu['after_sha256']
    for name, digest in cpu['after_sha256'].items():
        assert sha(root / name) == digest, name
    assert native['passed'] and native['source_unchanged']
    assert native['source_before'] == native['source_after']
    for member in native['source_before']['source_files']:
        assert sha(root / member['path']) == member['sha256'], member
    assert audit['passed'] and audit['checks'] == 7739
    assert sha(batch / 'audit_execution.py') == audit['script_sha256']
    for name, digest in audit['input_sha256'].items():
        assert sha(root / name.replace('\\', '/')) == digest, name
    for case in audit['cases']:
        record = next(c for c in native['cases'] if c['case_id'] == case['case_id'])
        assert record['result']['status'] == case['status']
    assert native['product_work'] == audit['actual_product_work'] == {
        'mutation_rpc': 8, 'setter_attempts': 8, 'setter_returns': 8,
        'preview_calls': 8, 'source_captures': 12,
    }
    assert native['model_calls'] == native['qa_candidate_assignments'] == 0
    assert native['process_exit']['closed']
    assert native['process_exit']['returncode'] == 0
    assert native['blend_sha256_before'] == native['blend_sha256_after']
    members = {}
    for path in sorted(batch.rglob('*')):
        if not path.is_file() or path.name == 'EVIDENCE_INDEX.json':
            continue
        assert '__pycache__' not in path.parts and path.suffix != '.pyc', path
        name = path.relative_to(root).as_posix()
        members[name] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    products = {name: value for name, value in cpu['after_sha256'].items()
                if name.startswith('human_eye_plugin/')}
    index = {
        'schema': 'arm-correction-execution-evidence-index-v1',
        'base_commit': '159c243c26576129830bea7eed16ec79207f7ffa',
        'passed': True, 'cpu_methods': 47, 'native_tasks': 8,
        'independent_checks': 7739,
        'runtime_source_sha256': audit['runtime_source_sha256'],
        'product_and_unchanged_dependency_sha256': products,
        'files': members,
        'exclusions': ['EVIDENCE_INDEX.json (self reference)'],
        'new_product_calls': 0, 'new_Blender_runs': 0,
    }
    (batch / 'EVIDENCE_INDEX.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8', newline='\n')
    print(json.dumps({'passed': True, 'indexed_files': len(members),
                      'index_sha256': sha(batch / 'EVIDENCE_INDEX.json')}))


if __name__ == '__main__':
    main()
