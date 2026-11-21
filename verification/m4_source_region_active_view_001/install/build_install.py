"""Build and verify one candidate wheel from the exact committed product source."""

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
BASE_BINDING = VERIFICATION / 'm5_joint_brief_source_projection_001/install/PRODUCT_RUN_BINDING.json'
BASE_TOOLS = Path('D:/he_perf050_readonly_product_pilot_001/slots/P1/INSTALLED_TOOLS.json')
EXTERNAL = Path('D:/he_m4_source_region_active_view_install_001')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '3e6a41afc151162bdde1d4ba2247541a4c9616b4'
BASE_SOURCE = '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd'
VERSION = '9.7.2+m4.source.region.active.view.001'
ALLOWED = {'human_eye_plugin/source_region.py', 'human_eye_plugin/active_observation.py',
           'human_eye_plugin/live_spatial_mcp.py'}


def probe(binding, label):
    argv = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    process = subprocess.run(argv, capture_output=True, timeout=60)
    for key, raw in (('STDOUT', process.stdout), ('STDERR', process.stderr)):
        with (EXTERNAL / f'{label}_{key}.bin').open('xb') as sink:
            sink.write(raw)
    process.check_returncode()
    return argv, json.loads(process.stdout)


def changed_paths(candidate):
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('one_exact_candidate_commit_required')
    lineage = subprocess.check_output(['git', 'rev-list', '--parents', '-n', '1', candidate]).decode().split()
    changed = tuple(subprocess.check_output(
        ['git', 'diff', '--name-only', BASE, candidate]).decode().splitlines())
    if (lineage != [candidate, BASE] or not set(changed) <= ALLOWED
            or 'human_eye_plugin/source_region.py' not in changed):
        raise ValueError('expected_direct_child_with_only_source_region_changes')
    return changed


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('fixed_build_interpreter_and_I_B_required')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('_verified_source_region_build', RETAINED)
    retained = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retained)
    retained.HERE = HERE
    retained.EXTERNAL = EXTERNAL
    retained.BASE = BASE
    retained.BASE_SOURCE = BASE_SOURCE
    retained.BASE_BINDING = BASE_BINDING
    retained.BASE_BINDING_SHA = '06f89a28f76d3d4c830de9f95b2370eb10e2a32e6ff20813919766dc7d22b358'
    retained.BASE_TOOLS = BASE_TOOLS
    retained.BASE_TOOLS_SHA = 'e07874b45ec4ce4e8c38e7eecabdb3a52ce6fc492556d3eb540e67956f5ad365'
    retained.VERSION = VERSION
    retained.CHANGED = changed_paths(args.candidate) if args.candidate is not None else ()
    retained.probe = probe
    helper = retained.build_helper()
    if args.candidate is not None:
        retained.build(helper, args.candidate)
    else:
        helper.inspect(args.inspect)


if __name__ == '__main__':
    main()
