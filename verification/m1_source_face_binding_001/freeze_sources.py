"""Publish versioned preparation freezes while preserving the task raster ledger."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_m1_freeze_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    if args.revision < 1 or (launcher.EXTERNAL / 'formal').exists():
        raise ValueError('preformal_positive_freeze_revision_required')
    snapshot = HERE / ('FROZEN_R' + str(args.revision).zfill(2) + '.json')
    if snapshot.exists():
        raise FileExistsError('freeze_revision_is_exclusive')
    current = HERE / 'FROZEN.json'
    if current.exists():
        prior = launcher.read(current)
        prior_snapshot = HERE / ('FROZEN_R' + str(prior['revision']).zfill(2) + '.json')
        if prior_snapshot.read_bytes() != current.read_bytes() or args.revision != prior['revision'] + 1:
            raise ValueError('prior_frozen_revision_must_be_retained')
    elif args.revision != 1:
        raise ValueError('first_freeze_revision_one')
    for p in HERE.glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
    for name in ('TRUTH.json', 'SCORING_CONTRACT.json', 'NORMALIZATION_SCHEMA.json'):
        if not (HERE / 'admin' / name).is_file():
            raise ValueError('private_contract_missing:' + name)
    plan = launcher.read(HERE / 'PLAN.json')
    sources = launcher.source_file_list(plan)
    intents = [launcher.read(p) for p in sorted((launcher.EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    if len(intents) > 12 or any(r['phase'] != 'preparation' for r in intents):
        raise ValueError('cumulative_qualification_phase_only_before_freeze')
    value = dict(schema='source-face-binding-source-freeze-v1', task=plan['task'], revision=args.revision,
        files_sha256=dict(sorted(sources.items())), product_bindings=plan['products'],
        cumulative_qualification_rasters_before_freeze=len(intents),
        persistent_ledger_root=str(launcher.EXTERNAL / 'raster_budget'),
        limits=dict(qualification_models=0, formal_models=6, qualification_rasters=12,
            formal_rasters=36, whole_rasters=48, seconds_per_slot=450, tools_per_slot=12,
            rasters_per_slot=6, outer_retries=0), before_publication_ns=time.perf_counter_ns())
    launcher.save(snapshot, value, exclusive=True)
    launcher.save(current, value)
    print(json.dumps(dict(revision=args.revision, frozen_files=len(sources), freeze_sha256=launcher.sha(current))))


if __name__ == '__main__':
    main()
