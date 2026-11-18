"""Freeze paired product, asset, entry and scoring sources before formal launch."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
EXTERNAL = Path('D:/he_m4_assembly_evidence_consumption_001')
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
DISPLAY = ROOT / 'verification/m4_source_region_display_001'
SOURCES = {'A': '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b',
           'B': '99d9b5e93ae10294309df2258b0582405861c0189ab15d659ae9b9e26df6ec9a'}
BINDINGS = {'A': ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json',
            'B': ROOT / 'verification/m4_assembly_evidence_first_001/install/OPTIMIZED_BINDING.json'}
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
PY_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def freeze(receipts):
    started = time.perf_counter_ns()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use the pinned isolated -I -B interpreter')
    require(sha(sys.executable) == PY_SHA and sha(CLI) == CLI_SHA and sha(BLENDER) == BLENDER_SHA,
            'executables differ from the reviewed assembly runtime')
    require(not (EXTERNAL / 'slots').exists(), 'formal slots already started')
    prepared = read(NS / 'PREPARED.json')
    require(sha(NS / 'inputs/PLAN.md') == prepared['plan_sha256'], 'plan pin mismatch')
    require(sha(NS / 'inputs/ASSEMBLY.json') == prepared['assembly_sha256'], 'operands pin mismatch')
    external = {BLENDER, CLI, Path(sys.executable)}
    for name, expected in prepared['source_identities'].items():
        path = ROOT / name
        require(sha(path) == expected, 'prepared input hash mismatch ' + name)
        external.add(path)
    for group, path in BINDINGS.items():
        binding = read(path)
        require(binding['source_sha256'] == SOURCES[group] and len(binding['source_manifest']) == 143,
                'unexpected product binding ' + group)
        for entry in binding['source_manifest']:
            f = Path(binding['install_root']) / entry['path']
            require(sha(f) == entry['sha256'], 'installed source drift ' + str(f))
            external.add(f)
    dependency = Path(binding['dependency_root']).resolve()
    shared_manifest = ROOT / 'verification/m5_harness_recovery_001/SHARED_DEPENDENCY.json'
    shared = read(shared_manifest)
    external.add(shared_manifest)
    for name, expected in shared['files_sha256'].items():
        require(sha(name) == expected, 'shared dependency changed ' + name)
        external.add(Path(name))
    sys.path[:0] = [str(NS), str(dependency), shared['dependency_root']]
    import numpy
    import PIL
    import shapely
    from shapely.geometry import box
    require(Path(shapely.__file__).resolve().is_relative_to(Path(shared['dependency_root']).resolve())
            and box(0, 0, 1, 1).area == 1, 'isolated geometry dependency smoke failed')
    from consumer_adapter import consumer_adapter
    _, adapter = consumer_adapter()
    for row in adapter['execution_sources']:
        f = Path(row['path'])
        require(sha(f) == row['sha256'] and f.stat().st_size == row['bytes'], 'consumer source changed')
        external.add(f)
    external.update(Path(module.__file__) for module in (numpy, PIL, shapely))
    external.update(DISPLAY / 'harness' / name for name in ('state_owned_native.py', 'reused/process_proof.py',
                                                          'reused/stdio_checks.py', 'reused/wire_meter.py'))
    prior_harness = ROOT / 'verification/m4_live_assembly_relation_task_001/harness'
    external.update(prior_harness / name for name in ('device_capture.py', 'reused/wire_meter.py',
                                                      'reused/verified_bootstrap.py'))
    external.update(ROOT / 'verification/m4_target_task_consumption_001' / name
                    for name in ('native_consumer_audit.py', 'native_tools.py'))
    external.add(ROOT / 'verification/m4_assembly_evidence_first_001/scoring/verify.py')
    require({path.parent.name for path in receipts} == {'A1', 'B1'} and len(receipts) == 2,
            'one finalized offline receipt per arm required')
    for path in receipts:
        require(path.resolve().is_relative_to(EXTERNAL.resolve()), 'offline receipt is outside this batch')
        require(read(path)['passed'] is True, 'offline receipt failed ' + str(path))
        external.add(path)
    for group in ('A', 'B'):
        schema = NS / f'inputs/PRODUCT_SCHEMA_{group}.json'
        replay_dir = EXTERNAL / f'preflight/install/{group}/second_assembly/brief'
        require(schema.read_bytes() == (replay_dir / 'TOOL_SCHEMA.json').read_bytes(), 'actual schema differs')
        installed = read(replay_dir / 'RUN.json')
        require(installed['passed'] and installed['capture_count'] == 1 and
                installed['source_sha256'] == SOURCES[group] and
                not any(installed[k] for k in ('Blender_starts', 'model_starts', 'API_calls')),
                'actual installed replay is not ready')
        external.update(replay_dir / name for name in ('RUN.json', 'PUBLIC.json', 'REQUEST.json'))
    require((NS / 'inputs/PROMPT.txt').stat().st_size > 0 and (NS / 'inputs/ENTRY.txt').stat().st_size > 0,
            'common prompt and entry required')
    require(any((NS / 'scoring').glob('*.py')) and any((NS / 'scoring').glob('*.md')),
            'frozen scorer and scoring method required')
    version = subprocess.run([str(CLI), '--version'], capture_output=True, timeout=15, check=True)
    auth = subprocess.run([str(CLI), 'login', 'status'], capture_output=True, timeout=15, check=True)
    require(version.stdout.strip() == b'codex-cli 0.152.1' and b'Logged in using ChatGPT' in auth.stdout + auth.stderr,
            'pinned CLI and ChatGPT login required')
    tracked = [f for f in NS.rglob('*') if f.is_file() and f.name != 'FROZEN.json']
    for f in tracked:
        require(f.suffix != '.pyc', 'unexpected bytecode in freeze')
        if f.suffix == '.py':
            ast.parse(f.read_bytes(), filename=str(f))
    pins = [{'path': str(f), 'sha256': sha(f), 'bytes': f.stat().st_size}
            for f in sorted({f.resolve() for f in [*external, *tracked]})]
    result = {'schema': 'm4-assembly-evidence-consumption-freeze-v1', 'direct_inputs': pins,
              'slots': ['A1', 'B1'], 'applies_to': ['A1', 'B1'], 'started_ns': started,
              'finished_ns': time.perf_counter_ns(), 'profile': ['0.152.1', 'gpt-6.1-sol', 'medium', 'default'],
              'limits': {'real_consumers': 2, 'owned_Blender': 2, 'tools_per_slot': 12, 'images_per_slot': 0,
                         'raster_per_slot': 0, 'task_seconds': 450, 'owned_seconds': 600, 'replacement': 0},
              'sources': SOURCES, 'shared_dependency_root': shared['dependency_root'],
              'consumer_execution_sources': adapter['execution_sources'], 'inference_started': 0,
              'existing_owned_Blender_starts': 0, 'login_status_chatgpt': True,
              'libraries': {s.__name__: s.__version__ for s in (numpy, PIL, shapely)}}
    with (NS / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Frozen', len(pins), 'direct inputs', sha(NS / 'FROZEN.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('offline_receipts', type=Path, nargs='+')
    freeze(parser.parse_args().offline_receipts)
