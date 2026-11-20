"""Build one isolated global-index candidate from the direct product Git child."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
PRIOR = VERIFICATION / 'm4_cross_scale_local_first_view_001/install'
PRIOR_HELPER = PRIOR / 'build_install.py'
PRIOR_HELPER_SHA = 'd9499aee53b8dfca82b261ec1f189f3319ce63bcab7647f77bafd6b1d34a5c29'
BASE_BINDING_SHA = '34f29216712186e174f5821ee491a554890f10f9cedada68d54f814592ad02a8'
BASE_TOOLS_SHA = 'e07874b45ec4ce4e8c38e7eecabdb3a52ce6fc492556d3eb540e67956f5ad365'
BASE_BINDING = PRIOR / 'PRODUCT_RUN_BINDING.json'
BASE_TOOLS = Path('D:/he_m4_cross_scale_local_first_view_001/slots/B1/INSTALLED_TOOLS.json')
EXTERNAL = Path('D:/he_m4_cross_scale_global_index_reuse_001/install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '1dd2f77ecf19d51ba52aa5757e861ed930a58135'
BASE_SOURCE = '58c310d53abbf6ceac9a7c5273fc3119ffbedc1b632b27eb8c49988ca90a7d33'
VERSION = '9.7.2+m4.cross.scale.global.index.reuse.001'


def configured_helper(changed=()):
    for path, expected in ((PRIOR_HELPER, PRIOR_HELPER_SHA), (BASE_BINDING, BASE_BINDING_SHA),
                           (BASE_TOOLS, BASE_TOOLS_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('historical_direct_build_input_changed/' + str(path))
    spec = importlib.util.spec_from_file_location('_verified_local_first_direct_build', PRIOR_HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.HERE = HERE
    helper.EXTERNAL = EXTERNAL
    helper.BASE = BASE
    helper.BASE_SOURCE = BASE_SOURCE
    helper.BASE_BINDING = BASE_BINDING
    helper.BASE_BINDING_SHA = BASE_BINDING_SHA
    helper.BASE_WHEEL = Path(json.loads(BASE_BINDING.read_bytes())['wheel_path'])
    helper.BASE_TOOLS = BASE_TOOLS
    helper.VERSION = VERSION
    helper.CHANGED = changed
    helper.probe = probe
    return helper


def probe(binding, name):
    command = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    for stream_name, raw in (('STDOUT', result.stdout), ('STDERR', result.stderr)):
        with (EXTERNAL / f'{name}_{stream_name}.bin').open('xb') as sink:
            sink.write(raw)
    result.check_returncode()
    return command, json.loads(result.stdout)


def build(candidate, changed_files):
    changed = tuple(sorted(changed_files))
    if (not changed or len(set(changed)) != len(changed)
            or any(not path.startswith('human_eye_plugin/') or path.count('/') != 1
                   or not path.endswith('.py') for path in changed)):
        raise ValueError('supply the registered candidate product modules once')
    helper = configured_helper(changed)
    commits = helper.git('rev-list', '--parents', '-n', '1', candidate).decode().split()
    if commits != [candidate, BASE]:
        raise ValueError('candidate must be the direct child of the installed local-first baseline')
    raw_scope = helper.git('diff', '--name-only', '-z', BASE, candidate)
    scope = tuple(raw_scope.decode().rstrip('\0').split('\0'))
    if scope != changed:
        raise ValueError('candidate Git scope differs from the registered modules')
    helper.build(candidate)


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('use the fixed local build interpreter with -I -B')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    action.add_argument('--verify-baseline', action='store_true')
    parser.add_argument('--changed', nargs='+', default=())
    args = parser.parse_args()
    if args.candidate:
        build(args.candidate, args.changed)
    elif args.inspect:
        configured_helper().inspect(args.inspect)
    else:
        helper = configured_helper()
        builder = helper.load('_local_first_wheel_builder', VERIFICATION / 'build_candidate_release.py')
        original, _, proof = helper.verify_baseline(builder)
        print(json.dumps({'baseline_sources_verified': len(original['source_manifest']),
                          'baseline_wheel_record_verified': proof['all_hashes_verified'],
                          'source_sha256': original['source_sha256']}))


if __name__ == '__main__':
    main()
