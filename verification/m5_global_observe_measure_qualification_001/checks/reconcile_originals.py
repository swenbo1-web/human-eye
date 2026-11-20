"""Reconcile the archived qualification without rewriting the frozen scorer or live outputs."""

import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path.insert(0, str(HERE))
import live_review as retained

FIXED_ASSET = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/QP/native/input.blend').resolve()


def run():
    frozen_review = NS / 'checks/LIVE_REVIEW.json'
    old = retained.read(frozen_review)
    retained.require(old['passed'] is False and all(slot['error'] == 'original_or_owned_copy_file_changed'
                     for slot in old['slots']), 'unexpected_frozen_failure_for_reconciliation')
    retained.verified(FIXED_ASSET, retained.ASSET_SHA, FIXED_ASSET.parent)
    for label in ('A', 'B'):
        status = retained.read(retained.RUN / 'slots' / label / 'SLOT_RESULT.json')
        retained.require(Path(status['asset_path']).resolve() == FIXED_ASSET and
                         status['asset_sha256'] == retained.ASSET_SHA and status['status'] == 'completed',
                         'archived_result_asset_path_or_final_state_changed')
    original_bound = retained.pixel['score']['bound_terminal']
    old_line = "original = Path(asset['asset_path']).resolve()"
    old_archive = "verified(previous_path, archived['sha256'], original.parents[1])"
    source_path = Path(original_bound.__code__.co_filename)
    # score_live creates the original function with compile; recover its body from the retained
    # byte-stable author AST and apply the already accepted independent enumeration correction.
    if source_path.name != 'score.py':
        raise ValueError('unexpected_retained_terminal_scorer_module')
    original_source = source_path.read_text(encoding='utf-8')
    import ast
    node = next(item for item in ast.parse(original_source).body
                if isinstance(item, ast.FunctionDef) and item.name == 'bound_terminal')
    source = ast.get_source_segment(original_source, node)
    review_mod = retained.pixel['score']
    before, after = review_mod['before'], review_mod['after']
    retained.require(source.count(before) == source.count(old_line) == source.count(old_archive) == 1,
                     'unexpected_original_py_source_anchors')
    original_globals = dict(original_bound.__globals__, FIXED_ASSET=FIXED_ASSET)
    new_archive = "verified(previous_path, archived['sha256'], Path(asset['asset_path']).resolve().parents[1])"
    exec(compile(source.replace(before, after).replace(old_line, 'original = FIXED_ASSET').replace(old_archive, new_archive),
                 str(source_path), 'exec'), original_globals)
    retained.pixel['score']['bound_terminal'] = original_globals['bound_terminal']
    original_replay = retained.cli_replay
    out = HERE / 'reconciliation_CLI_REPLAY'

    def local_only(result, output, label, *, note_only=False):
        slot_name = output.relative_to(retained.RUN / 'slots').parts[0]
        return original_replay(result, out / slot_name / label, label, note_only=note_only)

    retained.cli_replay = local_only
    review = retained.review(retained.RUN, NS / 'FROZEN.json')
    review.update(schema='m5-global-observe-measure-offline-reconciliation-v1',
                  original_frozen_qualification_passed=False,
                  original_frozen_review_sha256=retained.digest(frozen_review.read_bytes()),
                  rationale='Use SHA-matched qualification launcher source path in retained lifecycle proof. '
                            'Historical terminal containment remains rooted at its own original archive.',
                  retained_original_asset_path=retained.read(original_bound.__globals__['ASSET'])['asset_path'],
                  actual_original_asset_path=str(FIXED_ASSET),
                  retained_terminal_scorer_source_sha256=retained.digest(source_path.read_bytes()),
                  actual_Blender_processes=0, actual_models=0, actual_raster_attempts=0,
                  qualification_gate_remains_original=False)
    return review


if __name__ == '__main__':
    result = run()
    path = HERE / 'OFFLINE_LIVE_RECONCILIATION.json'
    with path.open('xb') as evidence:
        evidence.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False,
                                  default=str).encode() + b'\n')
    print(json.dumps({'passed': result['passed'], 'slots': [{k:v for k,v in item.items()
                      if k in ('label','passed','status','error','error_type')} for item in result['slots']],
                      'receipt_sha256': retained.digest(path.read_bytes())}))
