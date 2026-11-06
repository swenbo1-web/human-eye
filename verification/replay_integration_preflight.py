"""Source-bound independent replay of the fixed integration preflight cases."""

from argparse import ArgumentParser
from hashlib import sha256, file_digest
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'artifacts/cf/formal_001/20261105/seal/frozen.npz'


def identity(path):
    with path.open('rb') as stream:
        return {'sha256': file_digest(stream, 'sha256').hexdigest(), 'bytes': path.stat().st_size}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    source_paths = list((ROOT / 'human_eye_fast').glob('*.py'))
    source_paths += list((ROOT / 'verification').glob('integration_*.py'))
    source_paths += [ROOT / 'verification' / name for name in (
        'test_integration_preflight.py', 'cf_training.py', 'cf_baselines.py',
        'cf_visual_acceptance.py', 'vg_acceptance.py', 'test_blender_control.py',
        'test_bc_acceptance.py', 'test_fast_affordance_out.py', 'ao_public_consumer.py')]
    source_paths += list((ROOT / 'docs').glob('ENGINE_INTEGRATION*_DRAFT.md'))
    source_paths += [Path(__file__).resolve()]
    sources = {path.relative_to(ROOT).as_posix(): identity(path) for path in source_paths}
    write(out / 'source.json', sources)
    with ZipFile(out / 'source.zip', 'w', compression=ZIP_DEFLATED) as archive:
        for name in sources:
            archive.write(ROOT / name, name)
    cmd = [r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
           '--background', '--factory-startup', '--disable-autoexec', '--threads', '1',
           '--python-exit-code', '10', '--python', str(ROOT / 'verification/test_integration_preflight.py'),
           '--', '--out', str(out / 'native'), '--snapshot', str(SEED), '--pillow-python',
           r'D:\human eye\venv\Scripts\python.exe']
    env = {**os.environ, **{key: '1' for key in ('PYTHONDONTWRITEBYTECODE', 'OPENBLAS_NUM_THREADS',
                                              'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}}
    inputs = {str(SEED): identity(SEED)}
    write(out / 'launch.json', {'argv': cmd, 'inputs': inputs, 'fixed_main_ordinals': [0, 1, 20],
                              'controls': ['contact-zero', 'empty-reference', 'already-reached', 'nonbasis-key']})
    with (out / 'worker.log').open('wb') as stream:
        result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    stable = all(identity(ROOT / name) == value for name, value in sources.items())
    inputs_stable = all(identity(Path(name)) == value for name, value in inputs.items())
    write(out / 'process.json', {'exit_code': result.returncode, 'sources_stable': stable,
                                'inputs_stable': inputs_stable,
                                'outputs': {path.relative_to(out).as_posix(): identity(path)
                                            for path in out.rglob('*') if path.is_file()}})
    assert result.returncode == 0 and stable and inputs_stable
    original = ROOT / 'artifacts/integration/preflight_001/native_002'
    pairs = []
    for path in (out / 'native').rglob('*'):
        if path.suffix == '.png' or path.name.endswith('.ao.json') or path.name == 'schema.json':
            rel = path.relative_to(out / 'native')
            assert path.read_bytes() == (original / rel).read_bytes(), str(rel)
            pairs.append(str(rel))
    scores = []
    for path in (out / 'native').rglob('*.visual.json'):
        data = json.loads(path.read_bytes())
        prior = json.loads((original / path.relative_to(out / 'native')).read_bytes())
        assert data['score'] == prior['score']
        scores.append({'case': path.parent.name, 'observation': path.name, 'passed': data['score']['passed'],
                       'failed_checks': [name for name, value in data['score']['checks'].items() if not value]})
    write(out / 'replay.json', {'status': 'EXACT_PUBLIC_REPLAY', 'identical_public_files': pairs,
                              'scores': scores, 'passed_scores': sum(row['passed'] for row in scores),
                              'scope': 'Fixed stage-one replay. Preserves the known negative; not full quality or performance acceptance.'})
    print(json.dumps({'status': 'EXACT_PUBLIC_REPLAY', 'public_files': len(pairs),
                      'scores': len(scores), 'passed': sum(row['passed'] for row in scores)}))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    main(args.out.resolve())
