"""Bind the only native qualification and the six ordered consumers."""

from pathlib import Path

from budget import LIMITS
from common import (ASSET_SHA256, BRIEF, EXTERNAL, NS, ORDER, PRODUCT_BINDING, PRODUCT_GIT,
                    QP_EXTERNAL, SLOTS, SOURCE_SHA, TRUTH_SHA256, read, sha)


SCHEMA = 'm4-dense-panel-sweep-formal-v1'
GATE_SCHEMA = 'm4-dense-panel-sweep-formal-qualification-v1'
# The earlier QP supplied by the accepted region brief batch is immutable.
QP_FREEZE_SHA = 'b0660b1eb64afec1c6f8a6c78e208dbe194c117efc9a36ccbae30213186a0f50'
QP_RESULT_SHA = 'ab3ac0b8c307902ebac7bba66e0d1597f49fde0ae7b0bffd15ab30952bf68ca9'
QP_REVIEW_SHA = 'dfb3caf6a4709c667bb13b7f592cfcda81b482b2708d87185f26bfcffe72824a'
QP_ARCHIVE_SHA = '0afc0e820eaef19efcf5c2c4c502191c3d69e0852d9f6d732da04312713deb42'


def registered_external_qp():
    slot = QP_EXTERNAL / 'slots/QP'
    result, publication, review, archive = (slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json',
        BRIEF / 'checks/LIVE_REVIEW.json', QP_EXTERNAL / 'ORIGINAL_RUNTIME.zip')
    value = read(result)
    pub = read(publication)
    verdict = read(review)
    binding_sha = sha(PRODUCT_BINDING)
    pub_sha = sha(publication)
    if (sha(result) != QP_RESULT_SHA or sha(review) != QP_REVIEW_SHA or sha(archive) != QP_ARCHIVE_SHA
            or sha(BRIEF / 'FROZEN.json') != QP_FREEZE_SHA
            or any(row['label'] != 'QP' for row in (value, pub, verdict))
            or pub['status'] != 'completed' or value['status'] != 'completed'
            or pub['result_sha256'] != QP_RESULT_SHA or verdict['slot_result_sha256'] != QP_RESULT_SHA
            or verdict['publication_sha256'] != pub_sha or verdict['passed'] is not True
            or value['freeze_sha256'] != QP_FREEZE_SHA or verdict['freeze_sha256'] != QP_FREEZE_SHA
            or value['asset_sha256'] != ASSET_SHA256 or verdict['independent_truth_sha256'] != TRUTH_SHA256
            or value['product_source_sha256'] != SOURCE_SHA or value['product_binding_sha256'] != binding_sha
            or verdict['installed_product']['commit'] != PRODUCT_GIT
            or verdict['installed_product']['source_sha256'] != SOURCE_SHA
            or value['model_consumers'] != 0 or value['paid_API_calls'] != 0):
        raise ValueError('accepted_external_product_qualification_binding_changed')
    return {'label': 'QP', 'passed': True, 'asset_sha256': ASSET_SHA256, 'truth_sha256': TRUTH_SHA256,
            'product_git': PRODUCT_GIT, 'product_source_sha256': SOURCE_SHA, 'product_binding_sha256': binding_sha,
            'prior_freeze_sha256': QP_FREEZE_SHA, 'result_sha256': QP_RESULT_SHA, 'publication_sha256': pub_sha,
            'review_sha256': QP_REVIEW_SHA, 'original_archive_sha256': QP_ARCHIVE_SHA,
            'result_path': str(result.resolve()), 'publication_path': str(publication.resolve()),
            'review_path': str(review.resolve()), 'original_archive_path': str(archive.resolve())}


def verify_freeze(path):
    if path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_dense_panel_formal_freeze_required')
    frozen = read(path)
    external = registered_external_qp()
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER) or frozen['ledger_limits'] != LIMITS
            or frozen['product_git'] != PRODUCT_GIT or frozen['product_source_sha256'] != SOURCE_SHA
            or frozen['external_qp'] != external):
        raise ValueError('original_dense_panel_formal_limits_or_product_changed')
    pins = set()
    for row in frozen['direct_inputs']:
        source = Path(row['path']).resolve()
        if not source.is_file() or source.stat().st_size != row['bytes'] or sha(source) != row['sha256']:
            raise ValueError('dense_panel_formal_frozen_input_changed/' + str(source))
        pins.add(source)
    required = {PRODUCT_BINDING.resolve(), *[Path(external[field]).resolve() for field in
        ('result_path', 'publication_path', 'review_path', 'original_archive_path')]}
    if not required <= pins:
        raise ValueError('accepted_external_product_qualification_not_pinned')
    return sha(path)


def publication(label, frozen):
    folder = EXTERNAL / 'slots' / label
    raw = folder / 'SLOT_RESULT.json'
    result = read(raw)
    receipt = read(folder / 'SLOT_PUBLICATION.json')
    if (result['label'] != label or receipt['label'] != label or receipt['result_sha256'] != sha(raw)
            or result['freeze_sha256'] != frozen or result['asset_sha256'] != ASSET_SHA256
            or result['product_source_sha256'] != SOURCE_SHA
            or result['product_binding_sha256'] != sha(PRODUCT_BINDING)
            or (result['group'], result['phase']) != SLOTS[label]):
        raise ValueError('original_slot_result_publication_changed/' + label)
    return result, receipt


def host_clean(result, receipt):
    owner = result.get('owner_close') or {}
    closure = result.get('closure_verification') or {}
    before_after = result.get('independent_before_after') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (receipt.get('owned_budget_passed') is True and owner.get('confirmed') is True
            and owner.get('errors') == owner.get('transport_errors') == []
            and closure.get('status') == 'ready_closed' and closure.get('passed') is True
            and closure.get('mcp_closure_required') == (result['group'] == 'P')
            and before_after.get('passed') is True and before_after.get('same_owned_scene') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0)


def can_continue(result, receipt):
    if not host_clean(result, receipt) or not result.get('consumer'):
        return False
    consumer = result['consumer']
    exit_ = consumer.get('runtime_exit') or {}
    actual_consumer = (result.get('model_consumers') == 1 and consumer.get('safe_to_continue') is True
                       and consumer.get('process_reaped') is True and consumer.get('readers_stopped') is True
                       and all(exit_.get(key) is True for key in ('confirmed', 'exited', 'handle_closed')))
    if not actual_consumer:
        return False
    if result['status'] == receipt['status'] == 'completed':
        return consumer.get('valid_completion') is True and result.get('errors') == []
    return (result['status'] == receipt['status'] == 'failed' and bool(result.get('errors'))
            and all(error.get('stage') == 'consumer' for error in result['errors'])
            and not any(error.get('stage') in ('raw_archive', 'business_original_binding')
                        for error in consumer.get('errors', [])))


def check_schedule(label, frozen):
    index = ORDER.index(label)
    expected = ORDER[:index]
    slots = EXTERNAL / 'slots'
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(expected):
        raise ValueError('original_schedule_or_replacement_changed')
    for earlier in expected:
        result, receipt = publication(earlier, frozen)
        if earlier == 'QN':
            if (receipt['status'] != result['status'] or result['status'] != 'completed'
                    or result['model_consumers'] != 0 or not host_clean(result, receipt)):
                raise ValueError('native_qualification_not_closed/' + earlier)
        elif not can_continue(result, receipt):
            raise ValueError('previous_slot_has_host_or_unknown_state/' + earlier)


def qualification_rows(frozen):
    result, pub = publication('QN', frozen)
    native = NS / 'qualification/NATIVE_REVIEW.json'
    review = read(native)
    if review['passed'] is not True or not host_clean(result, pub):
        raise ValueError('native_qualification_review_failed')
    local = EXTERNAL / 'slots/QN'
    external = registered_external_qp()
    return [{'label': 'QN', 'passed': True, 'result_sha256': sha(local / 'SLOT_RESULT.json'),
             'publication_sha256': sha(local / 'SLOT_PUBLICATION.json'), 'review_sha256': sha(native)},
            {key: external[key] for key in ('label', 'passed', 'result_sha256', 'publication_sha256', 'review_sha256')}]


def validate_admission(label, freeze_path):
    frozen = verify_freeze(freeze_path)
    check_schedule(label, frozen)
    if label == 'QN':
        return {'freeze_sha256': frozen}
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path)
    if (gate['schema'] != GATE_SCHEMA or gate['passed'] is not True or gate['freeze_sha256'] != frozen
            or gate['external_QP_reused'] is not True or gate['slots'] != qualification_rows(frozen)):
        raise ValueError('original_native_and_external_product_qualifications_required')
    return {'freeze_sha256': frozen, 'qualification_sha256': sha(gate_path)}
