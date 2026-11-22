"""Seal the fixed protocol runs and verify every archived byte."""
import json
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from zipfile import ZIP_DEFLATED, ZipFile

NS = Path(__file__).resolve().parent
ROOT = Path('D:/he_m3_whole_object_rounded_witness_001')


def archive():
    policy = run_path(str(NS.parent / 'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    inspect, digest = policy['check_named_bytes'], policy['digest']
    manifest = json.loads((NS / 'FROZEN.json').read_bytes())
    for item in manifest['source_inputs']:
        data = Path(item['path']).read_bytes()
        if digest(data) != {'sha256': item['sha256'], 'bytes': item['bytes']}:
            raise ValueError('freeze input changed', item['path'])
    build = ROOT / 'candidate_install'
    binding = json.loads((NS / 'install/PRODUCT_RUN_BINDING.json').read_bytes())
    source = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        if build in path.parents and path not in (Path(binding['wheel_path']), build / 'PIP_STDOUT.bin', build / 'PIP_STDERR.bin'):
            continue
        source.append((path.relative_to(ROOT).as_posix(), path))
    index = {}
    target = NS / 'ORIGINAL_RUNTIME.zip'
    with ZipFile(target, 'x', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
        for name, path in source:
            raw = path.read_bytes()
            inspect(name, raw)
            bundle.writestr(name, raw)
            index[name] = digest(raw)
    with ZipFile(target) as bundle:
        if (len(bundle.namelist()) != len(index) or set(bundle.namelist()) != index.keys()
                or any(digest(bundle.read(name)) != row for name, row in index.items())):
            raise ValueError('runtime archive member mismatch')
    output = {'freeze_sha256': sha256((NS/'FROZEN.json').read_bytes()).hexdigest(),
              'archive': {'name': target.name, **digest(target.read_bytes())}, 'member_count': len(index), 'members': index}
    with (NS / 'RAW_INDEX.json').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print('sealed', len(index), 'members', target.stat().st_size, output['archive']['sha256'])


if __name__ == '__main__':
    archive()
