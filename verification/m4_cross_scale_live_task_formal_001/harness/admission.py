"""Bind a new formal slot to the sealed recovery evidence and current freeze."""

from pathlib import Path

from common import EXTERNAL, NS, RECOVERY, RECOVERY_EXTERNAL, SLOTS, SOURCE_SHA, asset_identity, read, sha


def verify_file(path, digest, length=None):
    if (not path.is_file() or (length is not None and path.stat().st_size != length)
            or sha(path) != digest):
        raise ValueError('formal_admission_file_changed/' + str(path))


def validate_admission(label, freeze_path):
    if label not in SLOTS or freeze_path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_formal_slot_and_freeze_required')
    frozen = sha(freeze_path)
    frozen_record = read(freeze_path)
    anchors = {}
    for row in frozen_record['direct_inputs']:
        path = Path(row['path']).resolve()
        verify_file(path, row['sha256'], row['bytes'])
        if path in anchors:
            raise ValueError('ambiguous_frozen_input/' + str(path))
        anchors[path] = (row['sha256'], row['bytes'])

    gate_path = NS / 'ADMISSION.json'
    gate = read(gate_path)
    asset, asset_sha = asset_identity()
    if (gate['passed'] is not True or gate['freeze_sha256'] != frozen
            or gate['asset_sha256'] != asset_sha or gate['product_source_sha256'] != SOURCE_SHA
            or gate['slots'] != list(SLOTS) or frozen_record['slots'] != list(SLOTS)
            or asset.resolve() not in anchors or anchors[asset.resolve()][0] != asset_sha):
        raise ValueError('new_formal_pair_admission_not_bound')

    evidence_pin = gate['evidence']
    evidence = Path(evidence_pin['path']).resolve()
    if (evidence != (NS / 'checks/OFFLINE_EVIDENCE.json').resolve()
            or anchors.get(evidence) != (evidence_pin['sha256'], evidence_pin['bytes'])):
        raise ValueError('offline_qualification_evidence_not_pinned')
    checked = read(evidence)
    original_freeze = gate['previous_freeze_sha256']
    original_qualification = gate['previous_qualification_sha256']
    if (checked['passed'] is not True or checked['original_freeze_sha256'] != original_freeze
            or checked['original_qualification_sha256'] != original_qualification):
        raise ValueError('offline_qualification_evidence_does_not_bind_prior_gate')
    for row in checked['source_pins']:
        path = Path(row['path']).resolve()
        if anchors.get(path) != (row['sha256'], row['bytes']):
            raise ValueError('offline_admission_source_not_frozen/' + str(path))

    verify_file(RECOVERY / 'FROZEN.json', original_freeze)
    verify_file(RECOVERY / 'QUALIFICATION.json', original_qualification)
    prior = read(RECOVERY / 'QUALIFICATION.json')
    if prior['passed'] is not False or prior['freeze_sha256'] != original_freeze:
        raise ValueError('original_qualification_outcome_not_preserved')
    statuses = {'QN': 'failed', 'QP': 'completed'}
    old_rows, new_rows, seals = (rowset for rowset in (
        prior['slots'], checked['slots'], gate['qualification_seals']))
    if any([r['label'] for r in rows] != list(statuses) for rows in (old_rows, new_rows, seals)):
        raise ValueError('original_two_qualification_denominators_required')
    for old, independently_checked, seal in zip(old_rows, new_rows, seals, strict=True):
        name = seal['label']
        folder = RECOVERY_EXTERNAL / 'slots' / name
        result = folder / 'SLOT_RESULT.json'
        response = folder / 'client/call_01/RESPONSE.json'
        published = read(folder / 'SLOT_PUBLICATION.json')
        if (old['original_status'] != statuses[name] or published['status'] != statuses[name]
                or old['result_sha256'] != published['result_sha256']
                or any(independently_checked[key] != seal[key] for key in ('result_sha256', 'response_sha256'))
                or published['result_sha256'] != seal['result_sha256']):
            raise ValueError('qualifying_original_and_derived_evidence_mismatch/' + name)
        verify_file(result, seal['result_sha256'])
        verify_file(response, seal['response_sha256'])
        result_record = read(result)
        if (result_record['status'] != statuses[name] or result_record['freeze_sha256'] != original_freeze
                or result_record['diagnostic_calls'][0]['response_sha256'] != seal['response_sha256']):
            raise ValueError('qualification_result_receipt_binding_failed/' + name)

    admission_sha = sha(gate_path)
    if label == 'P1':
        previous = EXTERNAL / 'slots/N1'
        original = previous / 'SLOT_RESULT.json'
        publication = read(previous / 'SLOT_PUBLICATION.json')
        slot = read(original)
        if (publication['label'] != 'N1' or publication['result_sha256'] != sha(original)
                or slot['label'] != 'N1' or slot['freeze_sha256'] != frozen
                or slot['admission_sha256'] != admission_sha):
            raise ValueError('P1_requires_same_admission_N1_publication')
    return {'freeze_sha256': frozen, 'admission_sha256': admission_sha}
