"""Admit the two machine qualifications and at most one serial formal pair."""

from pathlib import Path

from common import ASSET_SHA256, CATALOGUE, DUAL, EXTERNAL, NS, ORDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, SLOTS
from common import load_retained, read, sha


SCHEMA = 'm1-source-region-first-packet-consumption-001-v1'
QUALIFICATION = ('QA', 'QB')
FORMAL = ('A1', 'B1')

prior = load_retained('_first_packet_prior_admission', DUAL/'harness/admission.py')
registered_product = prior.registered_product
publication = prior.publication
can_continue = prior.can_continue


def verify_freeze(path=None):
    expected = NS/'FROZEN.json'
    path = expected if path is None else Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError('only_the_frozen_first_packet_experiment_is_admissible')
    data = read(path)
    if (data['schema'] != SCHEMA or data['slots'] != list(ORDER) or data['product'] != registered_product()
            or data['asset_sha256'] != ASSET_SHA256 or data['offline_preflight_passed'] is not True):
        raise ValueError('fixed_source_or_offline_preflight_changed')
    pins = set()
    for item in data['direct_inputs']:
        target = Path(item['path']).resolve()
        if target in pins or target.stat().st_size != item['bytes'] or sha(target) != item['sha256']:
            raise ValueError('frozen_input_changed/' + str(target))
        pins.add(target)
    required = (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, NS/'inputs/PROMPT.txt', NS/'checks/TRUTH.json',
                NS/'checks/RUBRIC.md', NS/'qualification/PREFLIGHT.json', NS/'consumer/PREFLIGHT.json')
    if not {item.resolve() for item in required} <= pins:
        raise ValueError('required_freeze_input_missing')
    return sha(path)


def validate_admission(label, path):
    if label not in SLOTS:
        raise ValueError('registered_first_packet_slot_required')
    frozen = verify_freeze(path)
    slots = EXTERNAL/'slots'
    predecessors = list(ORDER[:ORDER.index(label)])
    names = {folder.name for folder in slots.iterdir()} if slots.is_dir() else set()
    if names != set(predecessors) or any(not can_continue(*publication(slot, frozen)) for slot in predecessors):
        raise ValueError('unexpected_or_unclosed_predecessor')
    if label in FORMAL:
        for slot in QUALIFICATION:
            result, receipt = publication(slot, frozen)
            qualification = result.get('qualification') or {}
            reopen = read(EXTERNAL/'preflight'/f'{slot}_CLOSED_IMAGES.json')
            if (result['status'] != 'completed' or result['model_consumers'] != 0 or qualification.get('passed') is not True
                    or qualification != read(slots/slot/'QUALIFICATION.json') or reopen.get('passed') is not True
                    or reopen.get('freeze_sha256') != frozen or reopen.get('result_sha256') != receipt['result_sha256']
                    or reopen.get('image') != qualification['product_image']
                    or sha(reopen['image']['path']) != reopen['image']['sha256']):
                raise ValueError('current_qualification_and_closed_original_required/' + slot)
    return {'freeze_sha256': frozen}
