"""Admit the derived historical QA and one new QB before the two consumers."""

from pathlib import Path

from common import ASSET, EXTERNAL, NS, ORDER, PRODUCT, PRODUCT_BINDING, SLOTS, read, sha


SCHEMA = 'm1-region-task-first-packet-consumption-holdout-recovery-001-v1'
QUALIFICATION = ('QB',)
OLD_RESULT = '60b8226ac165ff5d0086833ed3f7e21571fb4706275b20dec9ab99527bdfda9e'
OLD_FREEZE = '2342ecb10d104ee000999b1d0d67e35545cf2516b50a45ac642a7ed6d54b14fc'
OLD_ARCHIVE = 'e4e1ce943c3a0fdbd96100d8fbcb7269b849f62de4146d5743d4d5dfca75c6aa'
DERIVED = NS/'qualification/QA_DERIVED_ADMISSION.json'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def registered_product():
    binding = read(PRODUCT_BINDING)
    require({'commit':binding['preparation_git'],'source_sha256':binding['source_sha256'],
             'wheel_sha256':binding['wheel_sha256']} == PRODUCT and len(binding['source_manifest']) == 143,
            'fixed_existing_product_install_required')
    return dict(PRODUCT)


def derived_qa(path=DERIVED):
    gate = read(path)
    require(gate['passed'] is True and gate['scope'] == 'derived_closed_QA_only'
            and gate['old_freeze_sha256'] == OLD_FREEZE and gate['old_archive_sha256'] == OLD_ARCHIVE
            and gate['old_result_sha256'] == OLD_RESULT and gate['old_gate_passed'] is False
            and gate['original_published_ns'] < gate['original_owned_deadline_ns']
            and gate['review_started_ns'] > gate['original_published_ns']
            and gate['review_closed_ns'] >= gate['review_started_ns'] and gate['review_live_slots'] == 0,
            'historical_QA_derived_admission_required')
    checks = {'old_result_path':OLD_RESULT,'old_freeze_path':OLD_FREEZE,'old_archive_path':OLD_ARCHIVE,
              'corrected_verifier_path':gate['corrected_verifier_sha256'],'qualification_proof_path':gate['qualification_proof_sha256']}
    for key, expected in checks.items():
        require(sha(gate[key]) == expected, 'derived_QA_binding_changed/' + key)
    require(not Path(gate['old_gate_path']).exists(),'original_QA_gate_must_remain_absent')
    return gate


def verify_freeze(path=None):
    expected = NS/'FROZEN.json'
    chosen = Path(path).resolve() if path else expected.resolve()
    require(expected.resolve() == chosen,'current_recovery_freeze_required')
    frozen = read(chosen)
    require(frozen['schema'] == SCHEMA and frozen['slots'] == list(ORDER)
            and frozen['product'] == registered_product()
            and Path(frozen['asset_path']).resolve() == ASSET.resolve(strict=True)
            and frozen['asset_sha256'] == sha(ASSET) and frozen['passed_offline_preflight'] is True
            and frozen['derived_qa_sha256'] == sha(DERIVED),'recovery_freeze_changed')
    paths = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve(strict=True)
        require(source not in paths and source.stat().st_size == pin['bytes'] and sha(source) == pin['sha256'],
                'frozen_source_changed/' + str(source))
        paths.add(source)
    required = (PRODUCT_BINDING,ASSET,DERIVED,NS/'inputs/PROMPT.txt',NS/'inputs/PRODUCT_SCHEMA.json',
                NS/'inputs/STANDARD_TOOLS_SCHEMA.json',NS/'inputs/EVIDENCE_TOOLS_SCHEMA.json',
                NS/'qualification/PREFLIGHT.json',NS/'harness/HOST_PREFLIGHT.json',
                NS/'qualification/GATE_PREFLIGHT.json',NS/'checks/evidence.py')
    require({item.resolve() for item in required} <= paths,'incomplete_frozen_recovery_inputs')
    derived_qa()
    return sha(chosen)


def publication(label, freeze):
    require(label in SLOTS,'registered_slot_required')
    slot = EXTERNAL/'slots'/label
    path = slot/'SLOT_RESULT.json'
    result, receipt = read(path), read(slot/'SLOT_PUBLICATION.json')
    require(result['label'] == receipt['label'] == label and receipt['result_sha256'] == sha(path)
            and (result['group'],result['phase']) == SLOTS[label]
            and result['asset_sha256'] == read(NS/'FROZEN.json')['asset_sha256']
            and result['product_binding_sha256'] == sha(PRODUCT_BINDING) and result['freeze_sha256'] == freeze,
            'original_slot_publication_binding_changed/' + label)
    return result, receipt


def can_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    owner = result.get('owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    independent = result.get('independent_before_after') or {}
    consumer = result.get('consumer') or {}
    return (receipt.get('owned_budget_passed') is True and result['status'] == receipt['status']
            and result['paid_API_calls'] == 0 and closure.get('passed') is True
            and closure.get('status') == 'ready_closed' and closure.get('mcp_closure_required') is True
            and owner.get('confirmed') is True and not owner.get('errors') and not owner.get('transport_errors')
            and independent.get('passed') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0
            and (not result.get('actual_model_admitted') or consumer.get('safe_to_continue') is True))


def qualified(label, freeze):
    require(label == 'QB','only_new_QB_may_publish_live_qualification')
    result, receipt = publication(label,freeze)
    base = EXTERNAL/'preflight'
    proof = base/f'{label}_CLOSED_PROOF.json'
    gate = read(base/f'{label}_CLOSED_GATE.json')
    require(can_continue(result,receipt) and result['status'] == 'completed'
            and result['model_consumers'] == 0 and gate['passed'] is True and read(proof)['passed'] is True
            and gate['freeze_sha256'] == freeze and gate['result_sha256'] == receipt['result_sha256']
            and gate['proof_sha256'] == sha(proof) and gate['derived_qa_sha256'] == sha(DERIVED)
            and gate['verified_ns'] < result['owned_deadline_ns'],
            'active_slot_missing_closed_qualification/' + label)
    for image in gate['original_images']:
        path = Path(image['path']).resolve(strict=True)
        require(path.is_relative_to((EXTERNAL/'slots'/label).resolve()) and sha(path) == image['sha256'],
                'current_qualified_readback_changed/' + label)
    require(len({row['ref'] for row in gate['original_images']}) >= 2,'current_two_complete_region_image_refs_required')
    return gate


def prior_labels(label, freeze):
    slots = EXTERNAL/'slots'
    prior = list(ORDER[:ORDER.index(label)])
    names = {item.name for item in slots.iterdir()} if slots.is_dir() else set()
    require(names == set(prior)
            and all(result['status'] == 'completed' and can_continue(result,receipt)
                    for result,receipt in (publication(name,freeze) for name in prior)),
            'unexpected_slot_order_or_unconfirmed_predecessor')
    if SLOTS[label][1] == 'formal':
        qualified('QB',freeze)
    return prior


def validate_admission(label, path):
    require(label in SLOTS,'registered_slot_required')
    token = verify_freeze(path)
    prior_labels(label, token)
    return {'freeze_sha256':token}
