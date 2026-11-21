"""Build the one narrowed joint full scope candidate from its committed Git sources."""

import argparse
from functools import partial
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


RUN = Path('D:/he_m1_joint_full_task_tail_scope_001')
OUTPUT = Path(__file__).resolve().parent
EXTERNAL = RUN / 'candidate_install'
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
EVIDENCE = '54f3a797439164dee79305f7e94f55f5863d55c1'
BASE = '475ae93a03780c1781c62c8372ee6cfe41792cad'
BASE_SOURCE = '5da861b729604309aa2c7aff7b0974d1ed08bfe7c95b8d8956f0c86241d09e8a'
BASE_WHEEL = '73e1a6a36d605921764d48f98ded047bee6dc500f384b6f9682fd38211f8de74'
BASE_TOOLS = Path(__file__).resolve().parents[2] / 'm1_joint_full_task_tail_001/install/TOOLS_SCHEMA.json'
BASE_TOOLS_SHA = '09713ffdb844e0df83b50612b864ec870207c565aae21a270ccc85bab90bd350'
VERSION = '9.7.2+m1.joint.full.task.tail.scope.001'
CHANGED = ('human_eye_plugin/live_spatial_mcp.py',)
DEPENDENCIES = {
    'm4_cross_scale_local_first_view_001/install/build_install.py':
        'd9499aee53b8dfca82b261ec1f189f3319ce63bcab7647f77bafd6b1d34a5c29',
    'm1_joint_full_task_tail_001/install/PRODUCT_RUN_BINDING.json':
        'bb8d228ecfab1638cca05297edd7e2f6aa75a586d8cb0baf681176d63c0fcd52',
    'build_candidate_release.py':
        '78a588104f8a11bf173e1faab3ac01900f1629c3de9625c742aded55a4e05855',
    'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py':
        '786673c9fa81a74f8ae729874f540d2a475ae9d9a62aac277d5789be661457a6',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def verify_lineage(repo, candidate):
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('one_exact_candidate_commit_required')
    lineage = git(repo, 'rev-list', '--parents', '-n', '1', candidate).decode().split()
    delta = git(repo, 'diff', '--name-only', '-z', BASE, candidate).decode().split('\0')[:-1]
    if lineage != [candidate, BASE] or tuple(delta) != CHANGED:
        raise ValueError('expected_direct_child_and_only_serializer_delta')


def probe(repo, output, binding, name):
    argv = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--repo', str(repo),
            '--output', str(output), '--inspect', str(binding)]
    process = subprocess.run(argv, capture_output=True, timeout=60)
    for stream, raw in (('STDOUT', process.stdout), ('STDERR', process.stderr)):
        with (EXTERNAL / f'{name}_{stream}.bin').open('xb') as sink:
            sink.write(raw)
    process.check_returncode()
    return argv, json.loads(process.stdout)


def load_helper(repo, output):
    audit_inputs = RUN / 'build_inputs'
    paths = []
    for name, expected in DEPENDENCIES.items():
        target = audit_inputs / name
        if not target.exists():
            raw = git(repo, 'show', EVIDENCE + ':verification/' + name)
            if digest(raw) != expected:
                raise ValueError('historical_build_input_mismatch/' + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
        if digest(target.read_bytes()) != expected:
            raise ValueError('historical_build_input_mismatch/' + name)
        paths.append(target)
    source, binding, builder, bootstrap = paths
    baseline = json.loads(binding.read_bytes())
    if digest(BASE_TOOLS.read_bytes()) != BASE_TOOLS_SHA or baseline['wheel_sha256'] != BASE_WHEEL:
        raise ValueError('historical_tools_or_wheel_binding_mismatch')
    spec = importlib.util.spec_from_file_location('_verified_target_observation_build', source)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.ROOT = repo
    helper.HERE = output
    helper.EXTERNAL = EXTERNAL
    helper.VERIFICATION = audit_inputs
    helper.BOOTSTRAP = bootstrap
    helper.BASE = BASE
    helper.BASE_SOURCE = BASE_SOURCE
    helper.BASE_BINDING = binding
    helper.BASE_BINDING_SHA = digest(binding.read_bytes())
    helper.BASE_WHEEL = Path(baseline['wheel_path'])
    helper.BASE_TOOLS = BASE_TOOLS
    helper.VERSION = VERSION
    helper.CHANGED = CHANGED
    helper.probe = partial(probe, repo, output)
    return helper, builder


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('fixed_build_interpreter_and_I_B_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, default=OUTPUT)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    action.add_argument('--verify-baseline', action='store_true')
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if args.candidate:
        verify_lineage(repo, args.candidate)
    helper, builder = load_helper(repo, output)
    if args.inspect:
        helper.inspect(args.inspect)
    elif args.verify_baseline:
        historical, _, proof = helper.verify_baseline(helper.load('_target_wheel_builder', builder))
        print(json.dumps({'baseline_git': historical['preparation_git'], 'baseline_source': historical['source_sha256'],
                          'source_count': len(historical['source_manifest']), 'wheel_sha256': historical['wheel_sha256'],
                          'verified_RECORD': proof['all_hashes_verified'], 'candidate_builds': 0}))
    else:
        output.mkdir(parents=True, exist_ok=True)
        helper.build(args.candidate)


if __name__ == '__main__':
    main()
