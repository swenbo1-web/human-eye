"""Build and verify one pixel-evidence candidate directly from committed Git bytes."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
HELPER = VERIFICATION / 'm4_cross_scale_local_first_view_001/install/build_install.py'
HELPER_SHA = 'd9499aee53b8dfca82b261ec1f189f3319ce63bcab7647f77bafd6b1d34a5c29'
BASE_BINDING = VERIFICATION / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
BASE_BINDING_SHA = 'f19f417d9d7a468626941a45bef997d5cc5902b9fb0fe743a9b476d6990e5cea'
BASE_TOOLS = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1/INSTALLED_TOOLS.json')
BASE_TOOLS_SHA = 'e07874b45ec4ce4e8c38e7eecabdb3a52ce6fc492556d3eb540e67956f5ad365'
EXTERNAL = Path('D:/he_m4_cross_scale_pixel_evidence_001/install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '21e608db565cf20d21fca735f913ae780e231470'
BASE_SOURCE = 'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7'
VERSION = '9.7.2+m4.cross.scale.pixel.evidence.001'
CHANGED = ('human_eye_plugin/live_spatial_mcp.py',)


def build_helper():
    for path, expected in ((HELPER, HELPER_SHA), (BASE_BINDING, BASE_BINDING_SHA), (BASE_TOOLS, BASE_TOOLS_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('historical build input changed/' + str(path))
    spec = importlib.util.spec_from_file_location('_verified_direct_wheel_build', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.EXTERNAL = EXTERNAL
    module.BASE = BASE
    module.BASE_SOURCE = BASE_SOURCE
    module.BASE_BINDING = BASE_BINDING
    module.BASE_BINDING_SHA = BASE_BINDING_SHA
    module.BASE_WHEEL = Path(json.loads(BASE_BINDING.read_bytes())['wheel_path'])
    module.BASE_TOOLS = BASE_TOOLS
    module.VERSION = VERSION
    module.CHANGED = CHANGED
    module.probe = probe
    return module


def probe(binding, name):
    command = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    for stream, raw in (('STDOUT', result.stdout), ('STDERR', result.stderr)):
        with (EXTERNAL / f'{name}_{stream}.bin').open('xb') as sink:
            sink.write(raw)
    result.check_returncode()
    return command, json.loads(result.stdout)


def build(helper, candidate):
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('one exact candidate commit is required')
    lineage = helper.git('rev-list', '--parents', '-n', '1', candidate).decode().split()
    if lineage != [candidate, BASE]:
        raise ValueError('candidate must be the direct child of the installed cold-frustum baseline')
    helper.build(candidate)


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('use the fixed local build interpreter with -I -B')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    action.add_argument('--verify-baseline', action='store_true')
    args = parser.parse_args()
    helper = build_helper()
    if args.candidate:
        build(helper, args.candidate)
    elif args.inspect:
        helper.inspect(args.inspect)
    else:
        builder = helper.load('_pixel_evidence_wheel_builder', VERIFICATION / 'build_candidate_release.py')
        baseline, _, proof = helper.verify_baseline(builder)
        print(json.dumps({'baseline_sources_verified': len(baseline['source_manifest']),
                          'baseline_wheel_record_verified': proof['all_hashes_verified'],
                          'source_sha256': baseline['source_sha256']}))


if __name__ == '__main__':
    main()
