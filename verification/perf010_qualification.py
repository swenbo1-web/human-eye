"""PERF-010 candidate pin on the existing owned R2 broker; no new transport.

Launch with the frozen source SHA and reuse perf000_scene_tool.py unchanged.
Only this process replaces the trial adapter's pin/finite read validation;
historical helpers and sealed receipts are never edited.
"""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from verification.visual004_native import load, save, need


def bind_candidate(pin):
    from human_eye_plugin.runtime_identity import runtime_identity, check_source_drift
    from human_eye_plugin.query_policy import validate_query
    from verification import visual004_product as adapter
    identity = runtime_identity()
    need(identity['source_sha256'] == pin and len(identity['source_files']) == 130
         and check_source_drift()['compatible'], 'perf010_fixed_candidate_pin')
    old_validate = adapter.validate_observe_arguments
    def validate(arguments):
        need(type(arguments) is dict, 'observe_arguments')
        query = arguments.get('query', {})
        if type(query) is dict and query.get('mode') == 'task':
            need(set(arguments) <= {'task_instruction','include_image','query','response_detail'}
                 and arguments.get('include_image') is False, 'perf010_numeric_task_scope')
            validate_query(query)
            return copy.deepcopy(arguments)
        if type(query) is dict and query.get('alignment_evidence') is False:
            need(arguments.get('include_image') is False, 'perf010_numeric_legacy_scope')
            value = copy.deepcopy(arguments); value['query'].pop('alignment_evidence')
            old_validate(value); validate_query(query)
            return copy.deepcopy(arguments)
        return old_validate(arguments)
    def config_for(session):
        # Same trusted launch/config as R2, pinned to these actual candidate
        # bytes. No selectors, solution, inventory or model answer is added.
        current = runtime_identity()
        need(current['source_sha256'] == pin and check_source_drift()['compatible'], 'perf010_runtime_drift')
        need(session.config['condition'] == 'P', 'P_only_product')
        config = dict(schema_version='1.0', enabled=True, observe_on_prompt=False, project_root=str(ROOT),
            state_file=str(session.workspace/'product_state.json'), audit_file=str(session.workspace/'product_audit.jsonl'),
            expected_identity=dict(source_sha256=pin, implementation_revision=current['implementation_revision'], mode='live'),
            request_budget_s=20., native_visual_timeout_s=10.,
            blender=dict(host=session.host, port=session.port, timeout_s=20.))
        path = session.workspace/'PRODUCT_CONFIG.json'
        if path.exists(): need(load(path) == config, 'product_config_changed')
        else: save(path, config)
        return path
    adapter.validate_observe_arguments = validate
    adapter.config_for = config_for
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--condition', choices=('P','N'), required=True)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--expected-asset-sha256', required=True)
    parser.add_argument('--seconds', type=float, default=600.)
    args = parser.parse_args()
    if args.condition == 'P': bind_candidate(args.pin)
    from verification.visual004_session import serve
    serve(asset=args.asset, blender=args.blender, workspace=args.workspace, condition=args.condition,
          seconds=args.seconds, expected_asset_sha256=args.expected_asset_sha256)


if __name__ == '__main__': main()
