"""Bind the asset, unchanged product, diagnostic bridge and offline contract."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_cross_scale_live_qualification_001')
BINDING = ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
PRODUCT_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
PLAN_SHA = 'c1970ebbe7adbe6caf2753524d7d53b18231e2833ae1d1b0767bbab600e34c92'
EXES = {'D:/Tools/blender5.2/blender.exe': '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb',
        'C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe':
            '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6',
        sys.executable: '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def freeze(offline, reused):
    started = time.perf_counter_ns()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned interpreter -I -B required')
    require(not (RUN / 'slots').exists(), 'the live slot already started')
    prepared = read(NS / 'PREPARED.json')
    require(sha(NS / 'inputs/PLAN.md') == prepared['plan_sha256'] == PLAN_SHA, 'planning bytes changed')
    require(sha(NS / 'inputs/REQUEST.json') == prepared['request_sha256'], 'registered request bytes changed')
    require(read(NS / 'inputs/REQUEST.json') == {'include_image': True, 'query': {'mode': 'active_observation',
            'region_task': {'area_min_m2': 0.0078125, 'area_max_m2': 0.03125, 'normal_z_min': 0.75}}},
            'registered request has a selection or unsupported field')
    files = set()
    for name, expected in {**EXES, **prepared['source_identities']}.items():
        f = ROOT / name
        require(sha(f) == expected, 'pinned input changed ' + name)
        files.add(f)
    binding = read(BINDING)
    require(len(binding['source_manifest']) == 143 and binding['source_sha256'] == PRODUCT_SHA,
            'wrong isolated product generation')
    for row in binding['source_manifest']:
        f = Path(binding['install_root']) / row['path']
        require(sha(f) == row['sha256'], 'installed source changed ' + str(f))
        files.add(f)
    dependencies = Path(binding['dependency_root']).resolve()
    for package in ('numpy', 'PIL'):
        files.add(dependencies / package / '__init__.py')
    schema = NS / 'inputs/PRODUCT_SCHEMA.json'
    require(read(schema)['name'] == 'human_eye_scene_observe', 'fixed actual product schema required')
    require(read(offline)['passed'] is True, 'complete offline transport preflight required')
    files.add(offline)
    require(any((NS / 'scoring').glob('*.py')) and any((NS / 'scoring').glob('*.md')),
            'fixed independent acceptance method required')
    files.update(reused)
    for f in NS.rglob('*'):
        if f.is_file() and f.name != 'FROZEN.json':
            require(f.suffix != '.pyc', 'unexpected bytecode in evidence')
            if f.suffix == '.py':
                ast.parse(f.read_bytes(), filename=str(f))
            files.add(f)
    direct = [{'path': str(f), 'sha256': sha(f), 'bytes': f.stat().st_size}
              for f in sorted({item.resolve() for item in files})]
    value = {'schema': 'm4-cross-scale-live-qualification-freeze-v1', 'slot': 'Q1', 'source_sha256': PRODUCT_SHA,
             'started_ns': started, 'closed_ns': time.perf_counter_ns(), 'direct_inputs': direct,
             'limits': {'owned_Blender': 1, 'business_requests': 2, 'raster_constructions': 6,
                        'consumers': 0, 'replacements': 0, 'cash_fees': 0},
             'CLI_content_policy': 'offline reconstruction from pinned Codex CLI 0.152.1 sources',
             'actual_model_and_provider_calls_before_freeze': 0}
    with (NS / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print('Frozen', len(direct), 'inputs', sha(NS / 'FROZEN.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('offline', type=Path)
    parser.add_argument('reused', type=Path, nargs='+')
    args = parser.parse_args()
    freeze(args.offline, args.reused)
