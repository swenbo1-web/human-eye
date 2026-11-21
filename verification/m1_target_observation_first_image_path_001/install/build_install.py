"""Build the one target-observation candidate from its committed Git sources."""

import argparse
from functools import partial
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


RUN = Path('D:/he_m1_target_observation_first_image_path_001')
OUTPUT = RUN / 'staging/install'
EXTERNAL = RUN / 'candidate_install'
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
EVIDENCE = 'f74703cbe8d1aca2131e544e29c54a518ee734fe'
BASE = '470a36f111cd5e96845569c258f464d4bbcf2824'
BASE_SOURCE = '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7'
BASE_WHEEL = '78f9626dc30ace6523f4715512a934d1a42ddca977066a614067f3ed61586eb8'
BASE_TOOLS = Path('D:/he_perf050_readonly_product_transfer_001/slots/P1/INSTALLED_TOOLS.json')
BASE_TOOLS_SHA = 'e07874b45ec4ce4e8c38e7eecabdb3a52ce6fc492556d3eb540e67956f5ad365'
VERSION = '9.7.2+m1.target.observation.first.image.path.001'
CHANGED = ('human_eye_plugin/live_spatial_mcp.py',)
DEPENDENCIES = {
    'm4_cross_scale_local_first_view_001/install/build_install.py':
        'd9499aee53b8dfca82b261ec1f189f3319ce63bcab7647f77bafd6b1d34a5c29',
    'm1_source_region_final_image_001/install/PRODUCT_RUN_BINDING.json':
        'd4a23b17afba0f54fab23e0d27f52e9424e0bb7ca45d83b165626dfdc874b72a',
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
