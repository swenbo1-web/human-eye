"""Verify the CF delivery's source archives and all recorded artifact identities."""

from hashlib import file_digest, sha256
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / 'artifacts/cf/formal_001'
OUT = ROOT / 'artifacts/cf/root_formal_review_001'


def identity(path):
    with path.open('rb') as stream:
        return {'sha256': file_digest(stream, 'sha256').hexdigest(), 'bytes': path.stat().st_size}


def load(path):
    return json.loads(path.read_bytes())


def check(path, expected):
    actual = identity(path)
    assert all(actual[key] == expected[key] for key in ('sha256', 'bytes')), str(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert identity(FORMAL / 'summary.json')['sha256'] == 'edb14212406bff3e4d995f37286945b6da8f21e6130f596cbba343fdaeebfe9a'
    assert identity(FORMAL / 'delivery-identity.json')['sha256'] == '14c247e4ea6846e9c8207137921859439ed3a9995e73e1b04804443001a7a254'
    delivery = load(FORMAL / 'delivery-identity.json')
    for entry in delivery['sources'].values():
        check(ROOT / entry['path'], entry)
    stages, archive_files, output_files, input_files = [], 0, 0, 0
    for seed, details in delivery['seeds'].items():
        frozen = details['frozen']
        check(ROOT / frozen['path'], frozen)
        for stage, entry in details['stages'].items():
            receipt = entry['receipt']
            path = ROOT / receipt['path']
            check(path, receipt)
            process = load(path)
            assert process['exit_code'] == entry['exit_code']
            assert process['sources_stable'] and process['inputs_stable']
            assert process['exit_code'] == (1 if seed == '20261105' and stage == 'evaluation' else 0)
            for rel, expected in process['outputs'].items():
                check(path.parent / rel, expected)
                output_files += 1
            launch = load(path.parent / 'launch.json')
            for name, expected in launch['file_whitelist'].items():
                check(Path(name), expected)
                input_files += 1
            source = load(path.parent / 'source.json')
            differences = []
            with ZipFile(path.parent / 'source.zip') as archive:
                assert set(archive.namelist()) == set(source)
                for name, expected in source.items():
                    data = archive.read(name)
                    assert {'sha256': sha256(data).hexdigest(), 'bytes': len(data)} == expected
                    archive_files += 1
                    if identity(ROOT / name) != expected:
                        differences.append(name)
            stages.append({'seed': seed, 'stage': stage, 'exit_code': process['exit_code'],
                           'historical_source_differs_from_current': differences})
    native = ROOT / 'artifacts/cf/root_formal_native_001'
    replay = load(native / 'process.json')
    assert replay['exit_code'] == 0 and replay['sources_stable'] and replay['inputs_stable']
    for rel, expected in replay['outputs'].items():
        check(native / rel, expected)
    controls = ROOT / 'artifacts/cf/root_formal_controls_002'
    continuation = load(controls / 'process.json')
    assert continuation['exit_code'] == 0 and continuation['sources_stable'] and continuation['inputs_stable']
    for rel, expected in continuation['outputs'].items():
        check(controls / rel, expected)
    result = {'status': 'PASS', 'delivery_identity': identity(FORMAL / 'delivery-identity.json'),
              'summary_identity': identity(FORMAL / 'summary.json'), 'source_files': len(delivery['sources']),
              'stage_count': len(stages), 'archive_source_files_checked': archive_files,
              'output_files_checked': output_files, 'input_files_checked': input_files,
              'stages': stages, 'native_replay': load(native / 'result.json'),
              'continuation_replay': load(controls / 'result.json'),
              'scope': 'Identity integrity only; algorithm, quality and statistical reviews separate.'}
    (OUT / 'identity_review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('stages', 'native_replay', 'continuation_replay')}, indent=2))


if __name__ == '__main__':
    main()
