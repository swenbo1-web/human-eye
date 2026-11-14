"""Freeze the planned source bytes without launching qualification or a model."""

import argparse
import importlib.util
from pathlib import Path

_launcher_spec = importlib.util.spec_from_file_location(
    '_complete_witness_freeze_launcher', Path(__file__).resolve().with_name('launcher.py'))
launcher = importlib.util.module_from_spec(_launcher_spec)
_launcher_spec.loader.exec_module(launcher)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    plan = launcher.read(launcher.HERE/'PLAN.json')
    sources = launcher.source_file_list(plan)
    value = dict(schema='complete-witness-source-freeze-v1', task=plan['task'],
                 preparation_git=args.preparation_git, product_source_sha256=launcher.PRODUCT_SHA256,
                 prompt_sha256=plan['expected_prompt_sha256'], files_sha256=sources,
                 limits=dict(qualification_models=0, formal_models=1, qualification_rasters=6,
                             formal_rasters=6, total_rasters=12, tools_per_owner=12, outer_retries=0))
    launcher.save(launcher.HERE/'FROZEN.json', value, exclusive=True)


if __name__ == '__main__':
    main()
