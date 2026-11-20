"""Record what the original files prove while preserving the first failed checks."""

from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, verify_freeze
from common import EXTERNAL, ORDER, read, save, sha


def seal():
    freeze = verify_freeze(NS / 'FROZEN.json')
    first, replay, costs, archive = (NS / name for name in (
        'checks/LIVE_REVIEW.json', 'checks/OFFLINE_LIVE_RECONCILIATION.json',
        'RESOURCE_RECHECK.json', 'RUNTIME_INDEX.json'))
    failure, review, resources = (read(path) for path in (first, replay, costs))
    if (failure['passed'] is not False or review['original_frozen_qualification_passed'] is not False
            or review['original_frozen_review_sha256'] != sha(first)
            or any(row['freeze_sha256'] != freeze for row in (failure, review, resources))
            or resources['first_resource_review_sha256'] != sha(NS / 'RESOURCE_REVIEW.json')):
        raise ValueError('original_failed_reviews_are_not_preserved')
    factual = {}
    for label, quality, cost in zip(ORDER, review['slots'], resources['rows'], strict=True):
        result, receipt = publication(label, freeze)
        if result['model_consumers'] != 0 or result['paid_API_calls'] != 0:
            raise ValueError('unexpected_external_consumer')
        factual[label] = {'result_sha256': receipt['result_sha256'],
                          'publication_sha256': sha(EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json'),
                          'quality_passed_in_offline_reconciliation': quality['label'] == label and quality['passed'],
                          'cost_reconciled': cost['label'] == label and cost['result_sha256'] == receipt['result_sha256']
                            and len(cost.get('outer_batches', [])) == 1 and not cost['cost_issues']
                            and len(cost.get('public_packets', [])) == (2 if label == 'A' else 1)
                            and cost['independently_recorded_kernel_solves'] == 1}
    expected = {'registered_owned': 2, 'owned_slot_directories': 2, 'original_public_requests': 3,
                'original_outer_batches': 2, 'proven_actual_frames': 6, 'model_consumers': 0}
    passed = (review['passed'] is True and review['denominators'] == expected and all(
        entry['quality_passed_in_offline_reconciliation'] and entry['cost_reconciled']
        for entry in factual.values()))
    save(NS / 'OFFLINE_DECISION.json', {'schema': 'm5-global-observe-measure-original-reconciliation-v1',
        'passed_offline_reconciliation': passed, 'original_frozen_gate_passed': False, 'freeze_sha256': freeze,
        'slots': factual, 'denominators': review['denominators'], 'new_Blender_slots': 0,
        'new_model_runs': 0, 'original_archive_index_sha256': sha(archive),
        'original_frozen_review_sha256': sha(first), 'offline_evidence_sha256': sha(replay),
        'offline_resource_review_sha256': sha(costs)})


if __name__ == '__main__':
    seal()
