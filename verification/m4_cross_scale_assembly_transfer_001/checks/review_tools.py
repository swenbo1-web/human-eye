"""Bind formal tool increments and image adoption to the original per-slot wire."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys


NS = Path(__file__).resolve().parents[1]
FORMAL = NS.parent / 'm4_cross_scale_live_task_formal_001'
BRIEF = NS.parent / 'm4_cross_scale_brief_entry_001'
LABELS = ('N1', 'P1')
IMAGE_REF = re.compile(r'(?:active-host-image|native-image):[0-9a-f]{64}')
CAPTION = re.compile(r'((?:active-host-image|native-image):[0-9a-f]{64}) \(512x512, image/png\)')
ANNOTATIONS = {'primary_observation', 'independent_current_geometry', 'additional_obstruction_evidence',
               'additional_witness', 'repeated_observation', 'error_recovery', 'failure', 'unresolved'}


def exact(path):
    with path.open('rb') as raw:
        digest = hashlib.file_digest(raw, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def read(path):
    return json.loads(path.read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def product_binder(retained):
    original = retained['product_evidence']

    def bind(slot, owner, request, response):
        arguments, receipt = (owner / name for name in ('PRODUCT_REQUEST.json', 'PRODUCT_RECEIPT.json'))
        if not arguments.is_file() or not receipt.is_file() or 'producer_archive' in read(receipt):
            return original(slot, owner, request, response)
        # Product dispatch may really fail before producing any archive.
        req, record = read(arguments), read(receipt)
        matched = [row for row in retained['read_jsonl'](slot / 'PUBLIC_REQUESTS.jsonl')
                   if row['request']['id'] == req['id']]
        require(len(matched) == 1 and matched[0]['request'] == req and
                req['params'] == {k: v for k, v in request['params'].items() if k != '_meta'} and
                matched[0].get('receipt') == record.get('receipt'), 'failed_product_original_receipt_mismatch')
        public = owner / 'PRODUCT_RESPONSE.json'
        if public.is_file():
            require(read(public) == matched[0]['response'] and
                    ('result' not in matched[0]['response'] or response.get('result') == matched[0]['response']['result']),
                    'failed_installed_product_reply_mismatch')
        require(response.get('error') or response.get('result', {}).get('isError'),
                'successful_product_cannot_omit_producer_archive')
        return {'request': exact(arguments), 'receipt': exact(receipt),
                'response': exact(public) if public.is_file() else None, 'arguments': req['params']['arguments'],
                'installed_original_id': req['id'], 'producer_delivery': None}

    return bind


def shown_refs(body, facts, images):
    """Resolve a ref only when a caption or metadata names the actual image bytes."""
    table = facts.get('images')
    indexed = {}
    if (isinstance(table, dict) and isinstance(table.get('columns'), list) and isinstance(table.get('rows'), list)
            and {'native_content_block_index', 'image_sha256', 'image_ref'} <= set(table['columns'])):
        for row in table['rows']:
            info = dict(zip(table['columns'], row, strict=True))
            indexed[info['native_content_block_index']] = info
    frames = facts.get('frames') or []
    chosen = {}
    for image in images:
        idx = image['content_index']
        by_index = indexed.get(idx)
        if by_index is not None and by_index['image_sha256'] == image['sha256']:
            chosen[idx] = {'ref': by_index['image_ref'], 'binding': 'indexed_product_image_table'}
        elif idx and body[idx - 1].get('type') == 'text' and (match := CAPTION.fullmatch(body[idx - 1]['text'])):
            chosen[idx] = {'ref': match[1], 'binding': 'preceding_original_ordinary_caption'}
        else:
            same = {f.get('image_ref') for f in frames if isinstance(f, dict) and
                    f.get('image_sha256') == image['sha256'] and f.get('image_ref')}
            if len(same) == 1:
                chosen[idx] = {'ref': same.pop(), 'binding': 'unique_product_frame_by_PNG_sha256'}
    return chosen


def enrich(row, answer, annotations, retained):
    refs = set(IMAGE_REF.findall(answer or ''))
    used_pngs = {}
    chosen = {}
    attempts = row['attempts']
    if annotations is not None:
        require([note['attempt'] for note in annotations] == [call['attempt'] for call in attempts],
                'manual_annotations_must_cover_the_actual_business_denominator')
    for i, attempt in enumerate(attempts):
        body = read(Path(attempt['RX']['path'])).get('result', {}).get('content', [])
        binding = shown_refs(body, retained['facts_from_first'](body), attempt['image_blocks'])
        for image in attempt['image_blocks']:
            image_id = image['sha256']
            earlier = used_pngs.get(image_id)
            image['repeats_PNG_from_previous_attempt'] = earlier if earlier != attempt['attempt'] else None
            used_pngs.setdefault(image_id, attempt['attempt'])
            metadata = binding.get(image['content_index'])
            image['delivered_reference'] = metadata
            if metadata and metadata['ref'] in refs and attempt['model_visible_as_public_CLI_tool_result']:
                chosen.setdefault(metadata['ref'], []).append({'attempt': attempt['attempt'], 'PNG_sha256': image_id,
                                                                'content_index': image['content_index']})
        attempt['requested_detail'] = read(Path(attempt['TX']['path']))['params']['arguments'].get('response_detail')
        if annotations is not None:
            note = annotations[i]
            require(note['label'] in ANNOTATIONS and
                    all(any(block['type'] == 'text' and quote in block['text'] for block in body)
                        for quote in note.get('response_anchors', [])) and
                    all(answer and quote in answer for quote in note.get('answer_anchors', [])),
                    'increment_claim_not_bound_to_original_evidence/' + str(attempt['attempt']))
            attempt['reviewed_increment'] = note
    row['explicit_original_answer_image_references'] = sorted(refs)
    row['adopted_reference_deliveries'] = chosen
    row['explicit_refs_without_unique_proven_delivery'] = sorted(refs - set(chosen))
    row['first_business_tool'] = attempts[0]['tool'] if attempts else None
    row['first_installed_execution_attempt'] = next((call['attempt'] for call in attempts if call['product']), None)
    return row


def main(runtime, output, annotations):
    sys.path.insert(0, str(NS / 'harness'))
    import common

    require(common.EXTERNAL.resolve() == runtime, 'registered_runtime_required')
    original = runpy.run_path(str(FORMAL / 'checks/review_actual_tools.py'))
    audit = original['audit_slot']
    audit.__globals__.update(NS=NS, RUNTIME=runtime, product_evidence=product_binder(original))
    costs = runpy.run_path(str(FORMAL / 'costs.py'))['slot_summary']
    costs.__globals__.update(NS=NS, EXTERNAL=runtime)
    summarize = runpy.run_path(str(BRIEF / 'checks/review_brief_entry.py'))['costs']
    sealed = NS / 'ANSWERS_SEALED.json'
    notes = read(annotations) if annotations else None
    seals = read(sealed)['answers']
    require([row['slot'] for row in seals] == list(LABELS), 'both_original_formal_slots_required_in_seal')
    records = []
    for seal in seals:
        label = seal['slot']
        cost = costs(label)
        if seal['status'] == 'unrun':
            records.append({'slot': label, 'status': 'unrun', 'attempts': [], 'model_consumers': 0})
            continue
        try:
            ledger, answer = audit(seal)
        except (ValueError, OSError, KeyError) as error:
            if seal['status'] == 'completed':
                raise
            records.append({'slot': label, 'status': seal['status'], 'harness_cost': cost,
                            'partial_tool_archive_issue': {'type': type(error).__name__, 'reason': str(error)}})
            continue
        require([entry['attempt'] for entry in ledger['attempts']] == list(range(1, len(ledger['attempts']) + 1)),
                'formal_business_wire_has_an_ordinal_gap')
        ledger = enrich(ledger, answer, notes[label] if notes is not None else None, original)
        ledger.update(harness_cost=cost, compared_clocks=summarize(ledger, cost),
                      model_consumers=cost['model_consumers'])
        records.append(ledger)
    report = {'scope': 'Public CLI event and exact original raw-wire evidence. '
                       'Quoted image references establish use of these public refs in the original answer. '
                       'Evidence quality scoring is independent. Actual provider identity, inputs and fees are unobserved.',
              'answer_seal': exact(sealed), 'annotations': exact(annotations) if annotations else None, 'slots': records}
    with output.open('x', encoding='utf8', newline='\n') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=NS / 'checks/TOOL_EVIDENCE.json')
    parser.add_argument('--annotations', type=Path)
    flags = parser.parse_args()
    main(flags.runtime.resolve(), flags.output, flags.annotations)
