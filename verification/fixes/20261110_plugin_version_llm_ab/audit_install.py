"""Compare both isolated installations and wheel members directly to Git."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).parent
EXPECTED = {
    'A': ('a3a72b929f55c40f195ff5e1a9f64ceb303b6360', 'e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0'),
    'B': ('d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d', 'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    file = ROOT / 'verification/plugin_version_llm_ab_001/INSTALL_RESULT.json'
    report = json.loads(file.read_text(encoding='utf-8'))
    results = []
    for label, (commit, canonical) in EXPECTED.items():
        version = report['versions'][label]
        checks = []
        def need(value, message):
            checks.append({'check': message, 'passed': bool(value)})
        need(version['commit'] == commit, 'fixed commit')
        proof = version['proof']
        identity = proof['runtime_identity']
        need(identity['source_sha256'] == canonical, 'expected canonical source')
        need(proof['isolated'] and proof['source_kind'] == 'installed_distribution', 'isolated installed import')
        installed = Path(version['installed_root'])
        need(installed == Path(proof['site_root']), 'installation root')
        need(all(Path(proof[k]).is_relative_to(installed) for k in ('plugin_file', 'goal_task_file', 'scheduler_file', 'numpy_file', 'pillow_file')), 'actual import locations')
        names = sorted(version['source_members'])
        blobs = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
                               input=''.join(commit + ':' + n + '\n' for n in names).encode(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        stream = io.BytesIO(blobs)
        wheel = ROOT / version['wheel']
        need(sha(wheel.read_bytes()) == version['wheel_sha256'], 'saved wheel digest')
        runtime_count = 0
        with zipfile.ZipFile(wheel) as archive:
            for name in names:
                header = stream.readline().split()
                assert len(header) == 3 and header[1] == b'blob', header
                blob = stream.read(int(header[2]))
                assert stream.read(1) == b'\n'
                member = version['source_members'][name]
                need(sha(blob) == member['sha256'] and len(blob) == member['bytes'], 'Git materialization ' + name)
                if member['runtime']:
                    runtime_count += 1
                    need(archive.read(name) == blob, 'wheel source ' + name)
                    need((installed / name).read_bytes() == blob, 'installed source ' + name)
                    need(next(x['sha256'] for x in identity['source_files'] if x['path'] == name) == sha(blob), 'runtime manifest ' + name)
        need(runtime_count == len(identity['source_files']) == 137, 'complete source count')
        need(proof['numpy_version'] == '2.3.5' and proof['pillow_version'] == '12.3.0', 'same dependency versions')
        results.append({'label': label, 'commit': commit, 'canonical': canonical,
                        'checks': checks, 'passed': all(c['passed'] for c in checks)})
    need_distinct = report['versions']['A']['installed_root'] != report['versions']['B']['installed_root']
    out = {'schema': 'root-plugin-ab-install-review-v1', 'input_sha256': sha(file.read_bytes()),
           'distinct_installations': need_distinct, 'versions': results,
           'passed': need_distinct and all(x['passed'] for x in results),
           'scope': 'Git/wheel/installed source and saved import proof; actual worker checked with run evidence later'}
    (HERE / 'INSTALL_REVIEW.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': out['passed'], 'checks': sum(len(x['checks']) for x in results), 'versions': len(results)}))
    raise SystemExit(0 if out['passed'] else 1)


if __name__ == '__main__':
    main()
