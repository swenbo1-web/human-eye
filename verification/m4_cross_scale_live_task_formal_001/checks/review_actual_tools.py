"""Bind the public formal tool evidence to original same-slot deliveries."""

import argparse
import base64
import hashlib
import json
from pathlib import Path


NS = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_m4_cross_scale_live_task_formal_001')
LABELS = ('N1', 'P1')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def read_jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def exact(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def facts_from_first(body):
    if not body or body[0].get('type') != 'text':
        return {}
    try:
        value = json.loads(body[0]['text'])
    except ValueError:
        return {}
    return value if type(value) is dict else {}


def product_evidence(folder, owner, request, response):
    args, receipt = (owner / name for name in ('PRODUCT_REQUEST.json', 'PRODUCT_RECEIPT.json'))
    if not args.is_file() or not receipt.is_file():
        return None
    req, row = read(args), read(receipt)
    entries = [x for x in read_jsonl(folder / 'PUBLIC_REQUESTS.jsonl') if x['request']['id'] == req['id']]
    require(len(entries) == 1 and entries[0]['request'] == req, 'actual_product_request_ordinal_not_bound')
    observation = entries[0]
    business_params = {key: val for key, val in request['params'].items() if key != '_meta'}
    require(business_params == req['params'], 'forwarded_product_parameters_changed')
    require(row['receipt'] == observation['receipt'] and row['producer_archive'] == observation['producer_archive'],
            'installed_product_wire_receipt_changed')
    result = {'request': exact(args), 'receipt': exact(receipt), 'installed_original_id': req['id'],
              'arguments': req['params']['arguments'], 'producer_delivery': None}
    reply = owner / 'PRODUCT_RESPONSE.json'
    if not reply.is_file():
        return result
    require(read(reply) == observation['response'] and
            ('result' not in observation['response'] or response.get('result') == observation['response']['result']),
            'installed_product_delivery_not_original_unchanged_reply')
    result['response'] = exact(reply)
    archive = observation.get('producer_archive')
    if not archive:
        return result
    producer = Path(archive['path']).resolve()
    require(producer.is_relative_to(folder.resolve()) and exact(producer)['sha256'] == archive['sha256'],
            'actual_producer_archive_identity_changed')
    value = read(producer)
    work = value.get('work') or {}
    stages = value.get('stages') or {}
    elapsed_ms = {key: span['elapsed_ns'] / 1e6 for key, span in stages.items()}
    rows = (value.get('facts') or {}).get('region_task', {}).get('rows', [])
    names = {row['host_id']: row['object_name'] for row in rows}
    scopes = {scope['scope_id']: names.get((scope['binding'].get('region_source') or {}).get('host_id'))
              for scope in value.get('scopes', [])}
    selected = {frame['frame_identity'] for frame in value.get('frames', [])}
    constructed = []
    if work.get('raster_attempts'):
        for frame in value.get('constructed_frames', []):
            frame_key = frame['frame_identity']
            scope_id, direction = frame['scope_id'], frame['view_name']
            constructed.append({'ref': frame['image_ref'], 'view': direction, 'scope': scope_id,
                                'object': scopes.get(frame['scope_id']), 'selected': frame_key in selected,
                                'render_and_publish_ms': elapsed_ms.get(f'render_and_publish_{scope_id}_{direction}'),
                                'feedback_ms': elapsed_ms.get(f'feedback_{scope_id}_{direction}'),
                                'stage_ms': {key: span['elapsed_ns'] / 1e6 for key, span in frame['stages'].items()}})
    result['producer_delivery'] = {'path': exact(producer), 'raster_attempts': work.get('raster_attempts'),
        'frame_reuses': work.get('frame_reuses'), 'constructed_frames': constructed,
        'result_cache_hit': work.get('result_cache_hit'),
        'service_total_ms': elapsed_ms.get('service_total'),
        'global_index_ms': elapsed_ms.get('index_global'),
        'region_facts': [{k: row.get(k) for k in ('object_name', 'status', 'reason', 'source_triangle_indices',
                         'view_reasons', 'complete_witness')} for row in rows]}
    return result


def audit_slot(seal):
    label = seal['slot']
    folder = RUNTIME / 'slots' / label
    paths = {'result': folder / 'SLOT_RESULT.json', 'published': folder / 'SLOT_PUBLICATION.json',
             'model_delivery': folder / 'consumer/BUSINESS_SOURCE_BINDING.json',
             'device_evidence': folder / 'DEVICE_EVIDENCE.json',
             'product_public_trace': folder / 'PUBLIC_REQUESTS.jsonl'}
    source = read(paths['result'])
    result_sha = exact(paths['result'])['sha256']
    require(source['slot'] == label and source['status'] == seal['status'] and
            result_sha == seal['slot_result_sha256'] == read(paths['published'])['result_sha256'],
            'original_slot_answer_seal_does_not_match')
    attestation = read(paths['model_delivery']) if paths['model_delivery'].is_file() else {}
    contracts = {row['attempt']: row for row in attestation.get('result_contracts', [])}
    wires = {}
    for tx in (folder / 'consumer/attachments').glob('bridge_*/*/TX.bin'):
        request = read(tx)
        if request.get('method') == 'tools/call':
            receipt = read(tx.with_name('RECEIPT.json'))
            ordinal = receipt['attempt']
            require(ordinal not in wires, 'duplicate_public_business_attempt_ordinal')
            wires[ordinal] = (tx, tx.with_name('RX.bin'), receipt)

    device_evidence = paths['device_evidence']
    device = read(device_evidence) if device_evidence.is_file() else {}
    attempted = []
    for ordinal, (tx, rx, receipt) in sorted(wires.items()):
        request, response = read(tx), read(rx)
        body = response.get('result', {}).get('content', [])
        owner = folder / 'owner' / f'tool_{ordinal:02d}'
        tx_file, rx_file = exact(tx), exact(rx)
        if receipt['origin'] == 'owner':
            require(read(owner / 'REQUEST.json') == request and read(owner / 'RESPONSE.json') == response,
                    'actual_owner_and_stdio_content_differs')
        contract = contracts.get(ordinal)
        if contract:
            require((tx_file['sha256'], rx_file['sha256']) == (contract['TX_sha256'], contract['RX_sha256']),
                    'actual_origin_wire_sha_differs_from_CLI_receipt')
        facts = facts_from_first(body)
        images = []
        for index, block in enumerate(body):
            if block['type'] != 'image':
                continue
            raw = base64.b64decode(block['data'], validate=True)
            sha = digest(raw)
            frames = [{k: f[k] for k in ('ref', 'scope_id', 'frame_identity', 'view', 'origin', 'source_ref') if k in f}
                      for f in device.get('frames', []) if f.get('PNG_sha256') == sha]
            images.append({'content_index': index, 'sha256': sha, 'bytes': len(raw), 'matching_device_frames': frames})
        attempted.append({'attempt': ordinal, 'tool': request['params']['name'], 'TX': tx_file, 'RX': rx_file,
                          'stdio_receipt': exact(tx.with_name('RECEIPT.json')),
                          'classification': None if contract is None else contract.get('classification'),
                          'CLI_match': None if contract is None else contract.get('reason'),
                          'CLI_received_ns': None if contract is None else contract.get('CLI_received_ns'),
                          'model_visible_as_public_CLI_tool_result': bool(contract and contract.get('matched')),
                          'is_error': bool(response.get('result', {}).get('isError') or response.get('error')),
                          'public_error': facts.get('error'),
                          'text_UTF8_bytes': sum(len(x['text'].encode()) for x in body if x['type'] == 'text'),
                          'fact_top_level_keys': list(facts), 'image_blocks': images,
                          'product': product_evidence(folder, owner, request, response)})
    answer_text = None
    if seal['path'] is not None:
        original = Path(seal['original_path']).resolve()
        sealed = Path(seal['path']).resolve()
        raw = sealed.read_bytes()
        require(original.is_relative_to(folder.resolve()) and sealed.is_relative_to(NS.resolve()) and
                original.read_bytes() == raw and digest(raw) == seal['sha256'] and len(raw) == seal['bytes'],
                'original_answer_and_sealed_copy_differ')
        answer_text = raw.decode('utf8')
    return {'slot': label, 'status': seal['status'], 'original_bindings': {k: exact(v) for k, v in paths.items() if v.is_file()},
            'answer_sha256': seal['sha256'], 'attempts': attempted}, answer_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', required=True, type=Path)
    opts = parser.parse_args()
    seal = NS / 'ANSWERS_SEALED.json'
    rows = read(seal)['answers']
    require(tuple(r['slot'] for r in rows) == LABELS, 'both_formal_originals_must_be_sealed_before_tool_review')
    notes = read(opts.observations)
    records = []
    for row in rows:
        record, answer = audit_slot(row)
        editorial = notes[row['slot']]
        require([item['attempt'] for item in editorial['increments']] == [r['attempt'] for r in record['attempts']],
                'manual_increment_classification_does_not_cover_actual_business_attempts')
        require(all(answer and phrase in answer for phrase in editorial['quoted_final_anchors']),
                'adoption_claim_does_not_match_same_slot_original_answer')
        record['incremental_assessment'] = editorial
        records.append(record)
    evidence = {'scope': 'Actual original matched public CLI records and manually reviewed evidence increments only.',
                'actual_provider_input': None, 'answer_seal': exact(seal), 'observations': exact(opts.observations),
                'slots': records}
    with (NS / 'checks/TOOL_EVIDENCE.json').open('x', encoding='utf8', newline='\n') as out:
        json.dump(evidence, out, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True)
        out.write('\n')
    print([(rec['slot'], len(rec['attempts'])) for rec in records])


if __name__ == '__main__':
    main()
