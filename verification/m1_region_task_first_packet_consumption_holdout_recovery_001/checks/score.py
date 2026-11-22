"""Run the frozen seven-item grading on an actual recovery slot."""

import argparse
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
E = run_path(str(HERE / 'evidence.py'))
GRADE = run_path(str(E['OLD_NS'] / 'checks/score.py'))['score_answer']


def score_slot(slot, claims):
    truth = E['OLD_NS'] / 'fixture/TRUTH.json'
    item = E['load_slot'](slot, truth)
    return GRADE(item, claims)


def exposure(a, b):
    """Distinguish an exposed standard/evidence pair from actual explicit-full projection."""
    first_a, first_b = (arm['first_matching_task'] for arm in (a, b))
    request_b = first_b['original_arguments'].get('response_detail') if first_b else None
    expected_pair = (first_a is not None and first_a['projection'] == 'full'
                     and first_b is not None and first_b['projection'] == 'brief')
    return {'standard_first_match': first_a, 'evidence_first_match': first_b,
            'standard_full_vs_evidence_packet_observed': expected_pair,
            'explicit_full_projection_observed': bool(expected_pair and request_b == 'full'),
            'evidence_request_detail': request_b,
            'both_answers_pass_frozen_quality': bool(a['all_quality_passed'] and b['all_quality_passed'])}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    result = score_slot(args.slot, E['read'](args.claims))
    with args.output.open('x',encoding='utf8',newline='\n') as handle:
        handle.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
