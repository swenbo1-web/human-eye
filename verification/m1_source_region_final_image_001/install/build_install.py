"""Install one exact product commit for the zero-model serializer qualification."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
RETAINED = VERIFICATION / 'm4_bound_blocker_evidence_001/install/build_install.py'
BASE_BINDING = VERIFICATION / 'm4_source_region_active_view_001/install/PRODUCT_RUN_BINDING.json'
BASE_TOOLS = Path('D:/he_m4_source_region_active_view_001/slots/B/INSTALLED_TOOLS.json')
EXTERNAL = Path('D:/he_m1_source_region_final_image_install_001')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '30c9cfc121bbdee72b61afda59cbcf23e9080b67'
BASE_SOURCE = '2ad989728b7229934d164cf4c763eeb89b28e86d6fbfe7b90bace82055b2683c'
VERSION = '9.7.2+m1.source.region.final.image.001'
CHANGED = ('human_eye_plugin/live_spatial_mcp.py',)


def probe(binding, label):
    argv = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    process = subprocess.run(argv, capture_output=True, timeout=60)
    for key, raw in (('STDOUT', process.stdout), ('STDERR', process.stderr)):
        with (EXTERNAL / f'{label}_{key}.bin').open('xb') as sink:
            sink.write(raw)
    process.check_returncode()
    return argv, json.loads(process.stdout)


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('fixed_build_interpreter_and_I_B_required')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    args = parser.parse_args()
    if args.candidate is not None:
        candidate = args.candidate
        if not re.fullmatch('[0-9a-f]{40}', candidate):
            raise ValueError('one_exact_candidate_commit_required')
        lineage = subprocess.check_output(['git', 'rev-list', '--parents', '-n', '1', candidate]).decode().split()
        delta = tuple(subprocess.check_output(['git', 'diff', '--name-only', BASE, candidate]).decode().splitlines())
        if lineage != [candidate, BASE] or delta != CHANGED:
            raise ValueError('expected_direct_child_only_in_the_existing_serializer')

    spec = importlib.util.spec_from_file_location('_verified_final_image_build', RETAINED)
    retained = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retained)
    retained.HERE = HERE
    retained.EXTERNAL = EXTERNAL
    retained.BASE = BASE
    retained.BASE_SOURCE = BASE_SOURCE
    retained.BASE_BINDING = BASE_BINDING
    retained.BASE_BINDING_SHA = 'aa853347bbe3e8e79f1bc8897f3ca7ca0c2f826276578fdccdc55fe4fe91b5ff'
    retained.BASE_TOOLS = BASE_TOOLS
    retained.BASE_TOOLS_SHA = 'e07874b45ec4ce4e8c38e7eecabdb3a52ce6fc492556d3eb540e67956f5ad365'
    retained.VERSION = VERSION
    retained.CHANGED = CHANGED
    retained.probe = probe
    helper = retained.build_helper()
    if args.candidate is not None:
        retained.build(helper, args.candidate)
    else:
        helper.inspect(args.inspect)


if __name__ == '__main__':
    main()
