"""Build one isolated wheel from the committed joint region measurement projection."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
RETAINED = VERIFICATION / 'm4_bound_blocker_evidence_001/install/build_install.py'
BASE_BINDING = VERIFICATION / 'm4_dense_raster_cross_001/install/PRODUCT_RUN_BINDING.json'
BASE_TOOLS = Path('D:/he_m4_dense_raster_cross_001/slots/B1/INSTALLED_TOOLS.json')
EXTERNAL = Path('D:/he_m5_joint_brief_source_projection_001/install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '9552d5c7103d9d8a08799adde96534990c6815f9'
BASE_SOURCE = '301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6'
VERSION = '9.7.2+m5.joint.brief.source.projection.001'
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

    spec = importlib.util.spec_from_file_location('_retained_isolated_wheel_build', RETAINED)
    retained = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retained)
    retained.HERE = HERE
    retained.EXTERNAL = EXTERNAL
    retained.BASE = BASE
    retained.BASE_SOURCE = BASE_SOURCE
    retained.BASE_BINDING = BASE_BINDING
    retained.BASE_BINDING_SHA = '84034374649c9cb7a598d4c5393c2ac6f2010aba043821660e2416507c5e232a'
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
