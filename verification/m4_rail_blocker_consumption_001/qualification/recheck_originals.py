"""Check closed originals through the frozen reviewer and recompute TX SHA from TX.bin."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path[:0] = [str(NS / 'harness'), str(HERE)]
from admission import publication, verify_freeze
from common import EXTERNAL, TRUTH, product_for, read, save, sha
import qualify

SOLE_CORRECTION = """    return reply['result'], {'wire': {name: meter[name] for name in ('TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')},
"""
RECOMPUTE = """    return reply['result'], {'wire': {**{name: meter[name] for name in ('TX_bytes', 'RX_bytes', 'RX_sha256')},
                                      'TX_sha256': sha(transport / 'TX.bin')},
"""


def replay():
    freeze = verify_freeze(NS / 'FROZEN.json')
    gate = NS / 'QUALIFICATION.json'
    original = read(gate)
    if original['passed'] is not False or original['freeze_sha256'] != freeze or (EXTERNAL / 'slots/A1').exists():
        raise ValueError('original_failed_gate_must_stay_unchanged')
    path = HERE / 'qualify.py'
    text = path.read_text(encoding='utf-8')
    if text.count(SOLE_CORRECTION) != 1:
        raise ValueError('frozen_qualification_review_not_as_expected')
    scope = dict(vars(qualify), __name__='_rail_offline_replay')
    exec(compile(text.replace(SOLE_CORRECTION, RECOMPUTE), str(path), 'exec'), scope)
    truth = read(TRUTH)
    all_rows = []
    for label in ('QA', 'QB'):
        folder = EXTERNAL / 'slots' / label
        result, publication_row = publication(label, freeze)
        failed_path = HERE / f'{label}_REVIEW.json'
        failed = read(failed_path)
        if [(issue['type'], issue['detail']) for issue in failed['issues']] != [('KeyError', "'TX_sha256'")]:
            raise ValueError('unexpected_original_review_failure')
        row = {'label': label, 'original_reviewer_sha256': sha(path), 'original_review_sha256': sha(failed_path),
               'original_result_sha256': publication_row['result_sha256'],
               'original_publication_sha256': sha(folder / 'SLOT_PUBLICATION.json'), 'passed': False}
        terminal, lifecycle = qualify.REVIEW['current_source'](folder, result)
        row['source_and_lifecycle'] = lifecycle
        pair = [scope['wire'](folder, recorded, expected)
                for recorded, expected in zip(result['diagnostic_calls'], scope['diagnostic_plan'](), strict=True)]
        row['diagnostic_wires'] = [p[1] for p in pair]
        row['ordinary'] = scope['ordinary'](folder, pair[1][0], truth, terminal)
        row['ordinary_CLI'] = scope['BRIEF_SCHEMA']['cli_stages'](pair[1][0])
        _, installed = product_for(label)
        scope['inspect_product'](folder, pair[0][0], truth, terminal, installed, result['arm'], row)
        row['passed'] = True
        all_rows.append(row)

    a, b = all_rows
    if [item['PNG_sha256'] for item in a['PNG']] != [item['PNG_sha256'] for item in b['PNG']]:
        raise ValueError('actual_qualification_images_differ_across_arms')
    if any(len(exact['cases']) != 4 for exact in all_rows) or a['ordinary'] != b['ordinary']:
        raise ValueError('actual_geometry_facts_differ_across_arms')
    outfile = HERE / 'OFFLINE_RECHECK.json'
    save(outfile, {'schema': 'm4-rail-blocker-offline-recheck-v1', 'passed_offline': True,
         'original_qualification_passed': False, 'qualification_gate_sha256': sha(gate), 'freeze_sha256': freeze,
         'live_replacements': 0, 'model_runs': 0, 'original_failed_reviews_unchanged': True, 'slots': all_rows})
    print('Read-only offline reconciliation passed for QA QB. Original gate preserved.', sha(outfile))


if __name__ == '__main__':
    replay()
