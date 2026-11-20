"""Derive formal admission from the four original QA/QB tool deliveries."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[1] / 'm4_rail_blocker_consumption_001'
RUNTIME = Path('D:/he_m4_rail_blocker_consumption_001')
ARCHIVE = RUNTIME / 'ORIGINAL_RUNTIME.zip'
PRIOR_COMMIT = '69c48d35f581b72ef8762ccf5cdae545adaaf882'
ARCHIVE_SHA = '57520912bef199a0b89514f92eff6deacce502f65f68c2a575226b9db4093086'
ANCHORS = {
    'FROZEN.json': '2162f98f38568f9510db6db6aa11e8cb720556e9915fbe93d30f83d4272d2fce',
    'QUALIFICATION.json': '1fb49ee3f47fb91769fbadbf7962b483cba8de72a2844f6716a7cd3900eec507',
    'CONTENT_MANIFEST.json': 'f5fa1b1ebdef579ad4b8f863abbfb2539a80542b0faf0f4183e6878557bb314d',
    'DECISION.json': '60f89cd0e216b9e9e3b4f88dd53c3f7712f75b5c9b086f5779e4bbE3f0e926aa'.lower(),
    'RUNTIME_INDEX.json': 'cfc8cf5177f8628bb79080c8e93ca2784546581b4dc4c58c5bc97af1d504a527',
    'RUNTIME_REVIEW.json': 'b647e580b8718f958a4ee9a4450e91809aa387fc2ec77f52cf4e3b26b9ea054b',
    'qualification/OFFLINE_RECHECK.json': '274fc81611ef8e85806f121feac4e4afb7f99044fc5bd027083deacab9ee431f',
    'truth/QUALIFICATION_ORIGINALS_REVIEW.json': '15ce1b1ab914f8b86a035562930fe319b0510ba9ac18e637327597aa3272c75c',
    'truth/CURRENT_TRUTH.json': 'd4daeb84945dddb0b1d511dd0931dc38adcbaae7eb2e7c68080fd068a972ebe0',
}
SCHEMA = 'm4-rail-blocker-consumption-formal-derived-qualification-v1'
LABELS = ('QA', 'QB')
TOOLS = ('human_eye_scene_observe', 'execute_python')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, data):
    with path.open('x', newline='\n', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True)
        stream.write('\n')


def pin(path, digest_value, size):
    return {'path': str(path.resolve()), 'sha256': digest_value, 'bytes': size}


def clean_binding(original, frozen, archived_record):
    label = original['label']
    require(label in LABELS and original['passed'] is False and
            original['result_sha256'] == archived_record[f'slots/{label}/SLOT_RESULT.json']['sha256'] and
            original['publication_sha256'] == archived_record[f'slots/{label}/SLOT_PUBLICATION.json']['sha256'] and
            original['review_sha256'] == sha(PRIOR / 'qualification' / f'{label}_REVIEW.json'),
            'original_qualification_slot_binding_changed/' + label)
    review = read(PRIOR / 'qualification' / f'{label}_REVIEW.json')
    require(review['label'] == label and review['passed'] is False and review['freeze_sha256'] == frozen and
            review['slot_result_sha256'] == original['result_sha256'] and
            review['publication_sha256'] == original['publication_sha256'] and
            [(v['type'], v['detail']) for v in review['issues']] == [('KeyError', "'TX_sha256'")],
            'original_qualification_failure_changed/' + label)


def original_identity(verify_full=False):
    pins = {}
    for name, expected in ANCHORS.items():
        path = PRIOR / name
        require(sha(path) == expected, 'prior_anchor_changed/' + name)
        pins[path.resolve()] = pin(path, expected, path.stat().st_size)

    manifest = read(PRIOR / 'CONTENT_MANIFEST.json')
    members = manifest['files']
    require(len(members) == manifest['count'] == len({x['path'] for x in members}),
            'prior_evidence_manifest_duplicate_or_size')
    for row in members:
        path = (PRIOR / row['path']).resolve()
        require(path.is_relative_to(PRIOR.resolve()) and not path.is_symlink(), 'prior_manifest_file_escape')
        if verify_full:
            require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                    'prior_evidence_member_changed/' + row['path'])
        pins[path] = pin(path, row['sha256'], row['bytes'])

    index = read(PRIOR / 'RUNTIME_INDEX.json')
    archive = index['archive']
    require(archive['sha256'] == ARCHIVE_SHA and Path(archive['path']).resolve() == ARCHIVE.resolve() and
            ARCHIVE.stat().st_size == archive['bytes'] and sha(ARCHIVE) == ARCHIVE_SHA,
            'original_runtime_archive_changed')
    pins[ARCHIVE.resolve()] = pin(ARCHIVE, ARCHIVE_SHA, archive['bytes'])
    source = index['files']
    mapped = {row['path']: row for row in source}
    require(index['count'] == len(source) == len(mapped) == 357 and
            set(path.name for path in (RUNTIME / 'slots').iterdir()) == set(LABELS), 'original_runtime_roster_changed')

    for row in source:
        path = (RUNTIME / row['path']).resolve()
        require(path.is_relative_to(RUNTIME.resolve()) and not path.is_symlink(), 'original_runtime_path_escape')
        pins[path] = pin(path, row['sha256'], row['bytes'])
    if verify_full:
        with ZipFile(ARCHIVE) as frozen_runtime:
            require(len(frozen_runtime.infolist()) == len(mapped) and set(frozen_runtime.namelist()) == mapped.keys(),
                    'original_runtime_archive_members_changed')
            for name, row in mapped.items():
                actual = (RUNTIME / name).read_bytes()
                require(len(actual) == row['bytes'] and digest(actual) == row['sha256'] and
                        frozen_runtime.read(name) == actual, 'actual_runtime_original_differs_from_ZIP/' + name)

    original = read(PRIOR / 'QUALIFICATION.json')
    frozen = ANCHORS['FROZEN.json']
    decision = read(PRIOR / 'DECISION.json')
    require(original['passed'] is decision['original_qualification_passed'] is False and
            original['freeze_sha256'] == decision['freeze_sha256'] == frozen and decision['formal_unrun'] == 6 and
            [v['label'] for v in original['slots']] == list(LABELS), 'original_failed_gate_changed')
    for row in original['slots']:
        clean_binding(row, frozen, mapped)
        if not verify_full:
            for kind, expected in (('RESULT', row['result_sha256']), ('PUBLICATION', row['publication_sha256'])):
                require(sha(RUNTIME / 'slots' / row['label'] / f'SLOT_{kind}.json') == expected,
                        'original_qualification_publication_changed/' + row['label'])

    return {
        'old_evidence_commit': PRIOR_COMMIT,
        'old_freeze_sha256': frozen,
        'old_gate_sha256': ANCHORS['QUALIFICATION.json'],
        'old_gate_passed': False,
        'old_formal_unrun': 6,
        'old_archive_sha256': ARCHIVE_SHA,
        'old_runtime_index_sha256': ANCHORS['RUNTIME_INDEX.json'],
        'old_offline_recheck_sha256': ANCHORS['qualification/OFFLINE_RECHECK.json'],
        'old_independent_review_sha256': ANCHORS['truth/QUALIFICATION_ORIGINALS_REVIEW.json'],
        'truth_sha256': ANCHORS['truth/CURRENT_TRUTH.json'],
        'source_pins': [pins[path] for path in sorted(pins)],
    }, original['slots']


def read_delivery(slot, ordinal, index):
    call = slot / 'client' / f'call_{ordinal:02d}'
    owner = slot / 'owner' / f'tool_{ordinal:02d}'
    transport = slot / 'client/transport' / f'rpc_{index:02d}'
    relay, = (slot / 'client/attachments').glob(f'bridge_*/{index:03d}')
    return {
        'TX': [(folder / file).read_bytes() for folder, file in
               ((transport, 'TX.bin'), (relay, 'TX.bin'), (owner, 'REQUEST.json'))],
        'RX': [(folder / file).read_bytes() for folder, file in
               ((transport, 'RX.bin'), (relay, 'RX.bin'), (owner, 'RESPONSE.json'))],
        'request': (call / 'REQUEST.json').read_bytes(),
        'response': (call / 'RESPONSE.json').read_bytes(),
        'readback': (call / 'delivered/READBACK.json').read_bytes(),
        'client_receipt': read(call / 'RECEIPT.json'),
        'transport_receipt': read(transport / 'RECEIPT.json'),
        'relay_receipt': read(relay / 'RECEIPT.json'),
        'owner_receipt': read(owner / 'RECEIPT.json'),
    }


def check_delivery(delivery, logged, expected, session):
    transport, relay, owner = (delivery[f'{layer}_receipt'] for layer in ('transport', 'relay', 'owner'))
    tx, rx = (delivery[kind][0] for kind in ('TX', 'RX'))
    for kind in ('TX', 'RX'):
        layers = delivery[kind]
        require(layers[0] == layers[1] == layers[2], 'original_delivery_bytes_changed/' + kind)
    request, reply = json.loads(tx), json.loads(rx)
    ordinal, index = logged['ordinal'], logged['transport_index']
    rpc_id = f'diagnostic-{ordinal}'
    require(request == {'jsonrpc': '2.0', 'id': rpc_id, 'method': 'tools/call', 'params': expected} and
            set(reply) == {'jsonrpc', 'id', 'result'} and reply['jsonrpc'] == '2.0' and reply['id'] == rpc_id and
            reply['result']['isError'] is False and type(reply['result']['content']) is list,
            'original_diagnostic_JSON_RPC_mismatch')
    require(transport == delivery['client_receipt'] and not transport['error'] and
            owner['is_error'] is False and owner['status'] == 'returned' and relay['origin'] == 'owner' and
            relay['owner_TCP_attempted'] is True and transport['id'] == relay['RPC_id'] == owner['RPC_id'] == rpc_id and
            transport['index'] == relay['sequence'] == index and relay['attempt'] == owner['attempt'] == ordinal and
            transport['method'] == relay['method'] == request['method'] and owner['name'] == logged['name'] == expected['name'],
            'original_diagnostic_receipt_binding_mismatch')
    tx_sha, rx_sha = digest(tx), digest(rx)
    require(len(tx) == transport['TX_bytes'] == relay['request_bytes'] and
            len(rx) == transport['RX_bytes'] == relay['response_bytes'] == owner['response_bytes'] and
            rx_sha == transport['RX_sha256'], 'original_diagnostic_receipt_size_or_RX_digest_mismatch')
    has_tx = 'TX_sha256' in transport
    require(not has_tx or transport['TX_sha256'] == tx_sha, 'original_diagnostic_TX_digest_mismatch')
    require(logged['tool_error'] is False and json.loads(delivery['request']) == request and
            json.loads(delivery['response']) == reply and digest(delivery['request']) == logged['request_sha256'] and
            digest(delivery['response']) == logged['response_sha256'] and
            digest(delivery['readback']) == logged['readback_sha256'], 'original_diagnostic_canonical_log_mismatch')
    clocks = [session['ready_ns'], session['diagnostic_ready_ns'], logged['started_ns'], transport['started_ns'],
              transport['stdin_flushed_ns'], relay['received_ns'], owner['started_ns'], owner['response_ready_ns'],
              owner['closed_ns'], relay['flush_completed_ns'], relay['closed_ns'], transport['received_complete_ns'],
              transport['consumer_json_decoded_ns'], transport['closed_ns'], logged['returned_ns'],
              session['diagnostic_close']['closed_ns'], session['cleanup_started_ns'], session['published_ns'],
              session['owned_deadline_ns']]
    require(all(type(value) is int for value in clocks) and clocks == sorted(clocks) and
            logged['returned_ns'] < session['task_deadline_ns'] < session['owned_deadline_ns'] and
            transport['elapsed_ns'] == transport['closed_ns'] - transport['started_ns'],
            'original_diagnostic_clock_window_mismatch')
    content = reply['result']['content']
    require(sum(len(block['text'].encode()) for block in content if block['type'] == 'text') ==
            logged['text_UTF8_bytes'] == owner['content_metrics']['text_UTF8_bytes'] and
            sum(block['type'] == 'image' for block in content) == logged['images'] ==
            owner['content_metrics']['image_blocks'] and owner['content_metrics']['PNG_bytes'] ==
            logged['delivered_PNG_bytes'], 'original_diagnostic_content_metrics_mismatch')
    return reply['result'], {'ordinal': ordinal, 'transport_index': index, 'tool': expected['name'], 'RPC_id': rpc_id,
            'TX_bytes': len(tx), 'RX_bytes': len(rx), 'TX_sha256': tx_sha,
            'TX_sha256_source': 'receipt' if has_tx else 'derived_from_three_original_TX_byte_streams',
            'RX_sha256': rx_sha, 'RX_sha256_source': 'original_receipt_and_three_original_RX_byte_streams'}


@contextmanager
def prior_reviewer():
    # Temporarily select the old imports under their own names. A formal
    # launcher can already have its own modules named common and admission.
    before = dict(sys.modules)
    paths = sys.path[:]
    try:
        for name in ('common', 'admission', 'budget', 'diagnostic'):
            sys.modules.pop(name, None)
        yield runpy.run_path(str(PRIOR / 'qualification/qualify.py'))
    finally:
        sys.path[:] = paths
        for name in ('common', 'admission', 'budget', 'diagnostic'):
            if name in before:
                sys.modules[name] = before[name]
            else:
                sys.modules.pop(name, None)


def stable_recheck(arm, full, forensic, original_recheck, original_forensic):
    keys = ('body_UTF8_bytes', 'PNG_bytes', 'PNG', 'producer_archive_sha256', 'constructed_frames',
            'cases', 'blocker_evidence', 'ordinary', 'ordinary_CLI', 'CLI', 'source_and_lifecycle')
    require(all(full[key] == original_recheck[key] for key in keys),
            'original_offline_replay_differs/' + arm)
    require(forensic == original_forensic and forensic['actual_frames'] == 3,
            'original_independent_forensic_review_differs/' + arm)


def reject(name, expected_reason, fn):
    try:
        fn()
    except ValueError as exc:
        require(str(exc).startswith(expected_reason), 'wrong_negative_rejection/' + name + '/' + str(exc))
    else:
        raise ValueError('negative_control_was_accepted/' + name)
    return {'control': name, 'rejected': True, 'reason': expected_reason}


def wire_controls(original, logged, args, session, receipt):
    def edit_raw(raw):
        changed = bytearray(raw)
        changed[0] ^= 1
        return bytes(changed)

    cases = []
    for direction in ('TX', 'RX'):
        altered = deepcopy(original)
        altered[direction][1] = edit_raw(altered[direction][1])
        cases.append(reject('changed_relay_' + direction, 'original_delivery_bytes_changed/' + direction,
                            lambda: check_delivery(altered, logged, args, session)))

    altered = deepcopy(original)
    wrong_id = altered['RX'][0].replace(receipt['RPC_id'].encode(), b'unexpected-x', 1)
    require(wrong_id != altered['RX'][0], 'missing_actual_RPC_id_for_negative_control')
    altered['RX'] = [wrong_id] * 3
    cases.append(reject('three_matching_Rx_layers_but_wrong_JSON_RPC_id', 'original_diagnostic_JSON_RPC_mismatch',
                       lambda: check_delivery(altered, logged, args, session)))
    altered = deepcopy(original)
    altered['owner_receipt']['RPC_id'] = 'wrong-host-id'
    cases.append(reject('owner_receipt_cross_bound', 'original_diagnostic_receipt_binding_mismatch',
                       lambda: check_delivery(altered, logged, args, session)))
    altered = deepcopy(original)
    wrong_clock = altered['owner_receipt']
    wrong_clock['response_ready_ns'] = wrong_clock['started_ns'] - 1
    cases.append(reject('owner_clock_backs_up', 'original_diagnostic_clock_window_mismatch',
                       lambda: check_delivery(altered, logged, args, session)))
    altered = deepcopy(original)
    for key in ('client_receipt', 'transport_receipt'):
        altered[key]['RX_sha256'] = '0' * 64
    cases.append(reject('original_RX_hash_mismatch', 'original_diagnostic_receipt_size_or_RX_digest_mismatch',
                       lambda: check_delivery(altered, logged, args, session)))
    altered = deepcopy(original)
    for key in ('client_receipt', 'transport_receipt'):
        altered[key]['TX_sha256'] = '0' * 64
    cases.append(reject('present_but_incorrect_TX_hash_cannot_use_missing_field_path',
                       'original_diagnostic_TX_digest_mismatch', lambda: check_delivery(altered, logged, args, session)))
    return cases


def derive():
    bound, records = original_identity(verify_full=True)
    historical = read(PRIOR / 'qualification/OFFLINE_RECHECK.json')
    independent = read(PRIOR / 'truth/QUALIFICATION_ORIGINALS_REVIEW.json')
    require(historical['passed_offline'] is independent['verified_local_images_and_blockers'] is True and
            historical['original_qualification_passed'] is independent['original_gate_passed'] is False and
            historical['freeze_sha256'] == bound['old_freeze_sha256'] and
            historical['qualification_gate_sha256'] == bound['old_gate_sha256'] and
            independent['truth_sha256'] == bound['truth_sha256'], 'original_recheck_or_independent_source_changed')
    checked, controls = [], []
    with prior_reviewer() as review:
        require(review['verify_freeze'](PRIOR / 'FROZEN.json') == bound['old_freeze_sha256'],
                'original_frozen_input_validation_failed')
        truth = read(review['TRUTH'])
        forensic = runpy.run_path(str(PRIOR / 'truth/review_qualification_originals.py'))
        pixels = runpy.run_path(str(forensic['PIXELS']))
        geometry = runpy.run_path(str(forensic['GEOMETRY']))
        prior_product = review['inspect_product']
        saved_cli = prior_product.__globals__['BRIEF_REVIEW']
        for record, historic, specimen in zip(records, historical['slots'], independent['closed_slots'], strict=True):
            label = record['label']
            slot = RUNTIME / 'slots' / label
            result, publication = review['publication'](label, bound['old_freeze_sha256'])
            require(review['host_clean'](result, publication) and result['status'] == publication['status'] == 'completed'
                    and result['model_consumers'] == result['paid_API_calls'] == 0 and result['actual_model_admitted'] is False
                    and result['errors'] == [] and result['diagnostic_close']['confirmed'] is True
                    and result['diagnostic_close']['exit_code'] == 0 and result['diagnostic_close']['forced_kill'] is False,
                    'original_qualification_host_not_clean/' + label)
            session = {**result, 'published_ns': publication['published_ns']}
            deliveries, tool_facts = [], []
            for ordinal, (logged, expected) in enumerate(zip(result['diagnostic_calls'], review['diagnostic_plan'](),
                                                               strict=True), 1):
                require(logged['ordinal'] == ordinal and expected['name'] == TOOLS[ordinal - 1],
                        'original_qualification_tool_order_changed')
                original = read_delivery(slot, ordinal, logged['transport_index'])
                raw, receipt = check_delivery(original, logged, expected, session)
                require(receipt['TX_sha256_source'] == 'derived_from_three_original_TX_byte_streams',
                        'original_transport_missing_TX_hash_contract_changed')
                deliveries.append(receipt)
                tool_facts.append(raw)
                controls.extend({'label': label, 'tool': expected['name'], **v}
                                for v in wire_controls(original, logged, expected, session, receipt))
            require(len(deliveries) == 2, 'missing_original_diagnostic_tool_deliveries')
            for receipt, prior in zip(deliveries, historic['diagnostic_wires'], strict=True):
                require(all(receipt[field] == prior['wire'][field]
                            for field in ('TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')),
                        'original_three_way_TX_RX_digest_differs_from_retained_review')
            terminal, lifecycle = review['REVIEW']['current_source'](slot, result)
            full = {'source_and_lifecycle': lifecycle, 'ordinary': review['ordinary'](slot, tool_facts[1], truth, terminal),
                    'ordinary_CLI': review['BRIEF_SCHEMA']['cli_stages'](tool_facts[1])}
            _, installed = review['product_for'](label)
            out = HERE / 'CLI_REPLAY' / label
            check_cli = saved_cli['check_cli']
            prior_product.__globals__['BRIEF_REVIEW'] = {**saved_cli,
                'check_cli': lambda raw, images, _original_output: check_cli(raw, images, out)}
            try:
                prior_product(slot, tool_facts[0], truth, terminal, installed, result['arm'], full)
            finally:
                prior_product.__globals__['BRIEF_REVIEW'] = saved_cli
            replay = forensic['check'](label, truth, pixels, geometry)
            stable_recheck(label, full, replay, historic, specimen)
            pins = [relative_pin(path) for path in sorted(out.iterdir())]
            checked.append({**record, 'passed': True, 'old_passed': False, 'arm': result['arm'],
                            'product_git': result['product_git'], 'product_source_sha256': result['product_source_sha256'],
                            'product_binding_sha256': result['product_binding_sha256'],
                            'initial_sha256': result['initial_source']['sha256'],
                            'terminal_sha256': result['terminal_source']['sha256'],
                            'closure': result['closure_verification'], 'deliveries': deliveries,
                            'independent_facts': replay, 'ordinary': full['ordinary'], 'CLI': full['CLI'],
                            'archived_cli_replay': pins})
    return {**bound, 'schema': SCHEMA, 'passed': True, 'new_qualifications': 0, 'new_Blender_starts': 0,
            'model_runs': 0, 'slots': checked}, {
        'passed': True, 'replayed_original_deliveries': 4, 'new_qualifications': 0, 'model_runs': 0, 'controls': controls}


def relative_pin(path):
    return {'path': path.relative_to(HERE).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}


def verify_sealed():
    bound, originals = original_identity()
    derived = read(HERE / 'DERIVED.json')
    require(all(derived.get(key) == value for key, value in bound.items()) and
            derived['schema'] == SCHEMA and derived['passed'] is True and
            derived['new_qualifications'] == derived['model_runs'] == derived['new_Blender_starts'] == 0 and
            len(derived['slots']) == len(originals), 'sealed_formal_qualification_ancestry_changed')
    for slot, old in zip(derived['slots'], originals, strict=True):
        require(all(slot[key] == old[key] for key in ('label', 'result_sha256', 'review_sha256', 'publication_sha256')) and
                slot['passed'] is True and slot['old_passed'] is False and
                [row['tool'] for row in slot['deliveries']] == list(TOOLS) and
                all(row['TX_sha256_source'] == 'derived_from_three_original_TX_byte_streams' for row in slot['deliveries']),
                'sealed_formal_qualification_slot_binding_changed')
        for replay in slot['archived_cli_replay']:
            target = HERE / replay['path']
            require(target.resolve().is_relative_to(HERE / 'CLI_REPLAY') and
                    relative_pin(target) == replay, 'sealed_cli_replay_binding_changed')
    return derived


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    if parser.parse_args().verify:
        verified = verify_sealed()
        print('Verified sealed prior qualification', sha(HERE / 'DERIVED.json'), len(verified['source_pins']))
        return
    require(not (HERE / 'DERIVED.json').exists() and not (HERE / 'PREFLIGHT.json').exists(),
            'derived_qualification_already_published')
    gate, offline = derive()
    save(HERE / 'DERIVED.json', gate)
    save(HERE / 'PREFLIGHT.json', {**offline, 'derived_sha256': sha(HERE / 'DERIVED.json')})
    print('Derived original QA/QB admission', sha(HERE / 'DERIVED.json'), len(offline['controls']))


if __name__ == '__main__':
    main()
