"""Collect wall-clock spans, observed content sizes and raw CLI usage for six new slots."""

from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
OLD = NS.parent / 'm4_rail_blocker_consumption_001'
sys.path.insert(0, str(NS / 'harness'))
from admission import verify_freeze
from common import ARMS, EXTERNAL, ORDER, load, read, save, sha


def summarize():
    path = NS / 'FROZEN.json'
    freeze = verify_freeze(path)
    prior = load('_prior_rail_cost_reader', OLD / 'costs.py')
    prior.NS, prior.EXTERNAL = NS, EXTERNAL
    # Exact-template comparison still reads the original input directly.
    shared = load('_prior_formal_cost_reader', prior.RETAINED)
    shared.EXTERNAL, shared.NS = EXTERNAL, OLD
    slots = []
    for label in ORDER:
        folder = EXTERNAL / 'slots' / label
        if folder.exists() and not (folder / 'SLOT_PUBLICATION.json').is_file():
            slots.append({'label': label, 'arm': ARMS[label], 'phase': 'formal',
                          'status': 'unconfirmed', 'model_consumers': None})
            continue
        row = prior.summarize(label, freeze, shared)
        if row['status'] != 'unrun':
            result = read(folder / 'SLOT_RESULT.json')
            receipt = read(folder / 'SLOT_PUBLICATION.json')
            envelope = folder / 'consumer/CONSUMER.json'
            consumer = read(envelope) if envelope.is_file() else {}
            row.update(admission_verification_ms=result['admission_verification_ns'] / 1e6,
                       shutdown_to_publication_ms=shared.elapsed(result['cleanup_started_ns'], receipt['published_ns']),
                       ready_to_prompt_ms=shared.elapsed(result.get('ready_ns'), consumer.get('prompt_submitted_ns')))
        slots.append(row)
    original = OLD / 'RUNTIME_REVIEW.json'
    original_slots = [row for row in read(original)['slots'] if row['phase'] == 'qualification']
    frozen = read(path)
    save(NS / 'RUNTIME_REVIEW.json', {
        'schema': 'm4-rail-blocker-consumption-formal-runtime-v1',
        'freeze_sha256': freeze, 'qualification_sha256': frozen['derived_qualification_sha256'],
        'freeze_registration_ms': (frozen['completed_ns'] - frozen['started_ns']) / 1e6,
        'old_qualification_only': {'source_sha256': sha(original), 'slots': original_slots},
        'slots': slots, 'formal_comparison': prior.comparison(slots), 'new_qualifications': 0,
        'new_asset_builds': 0, 'additional_paid_API_calls': 0, 'cash_fees': None,
        'actual_internal_provider_input': None, 'model_internal_timing': None,
    })


if __name__ == '__main__':
    summarize()
