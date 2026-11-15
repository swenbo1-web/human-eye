"""Freeze prepared sources once, before any qualification raster or model."""

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    if (HERE/'FROZEN.json').exists() or (HERE/'QUALIFICATION_STARTED.json').exists():
        raise FileExistsError('unused_prequalification_freeze_required')
    spec = importlib.util.spec_from_file_location('_transfer_freeze_launcher', HERE/'launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    if (launcher.EXTERNAL/'preparation').exists() or (launcher.EXTERNAL/'formal').exists():
        raise FileExistsError('no_previous_scene_execution')
    plan = launcher.read(HERE/'PLAN.json')
    sources = launcher.source_file_list(plan)
    for path in HERE.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
            sources[str(path.resolve())] = launcher.sha(path)
    runtime_check = launcher.read(HERE/'RUNTIME_INTERFACE_CHECK.json')
    if runtime_check.get('passed') is not True:
        raise ValueError('actual_offline_interface_check_required')
    for path, expected in sources.items():
        if launcher.sha(path) != expected:
            raise ValueError('source_changed_before_freeze:' + path)
    frozen = dict(schema='occluded-scene-transfer-source-freeze-v1', task=plan['task'],
        baseline_git=plan['baseline_commit'], product_git=plan['product_commit'],
        before_freeze_git=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        product_source_sha256=launcher.PRODUCT_SHA256, files_sha256=dict(sorted(sources.items())),
        prompt_sha256=plan['expected_prompt_sha256'], sequence=plan['sequence'],
        limits=dict(qualification_models=0,formal_models=6,seconds_per_slot=450,
            business_admissions_per_slot=12,actual_rasters_per_slot=6,qualification_rasters=12,
            formal_rasters=36,total_rasters=48,outer_retries=0),
        scope='Prepared inputs, common tools/dependencies, independent oracle and pixel algorithms. No prior product/raster/model run on the new scene.',
        before_publication_ns=time.perf_counter_ns())
    launcher.save(HERE/'FROZEN.json',frozen,exclusive=True)
    print(json.dumps(dict(files=len(sources),freeze_sha256=launcher.sha(HERE/'FROZEN.json'))))


if __name__ == '__main__':
    main()
