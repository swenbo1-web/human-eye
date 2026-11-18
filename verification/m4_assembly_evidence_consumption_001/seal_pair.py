"""Seal the original pair of final answers and first installed product responses."""

import hashlib
import json
from pathlib import Path
import time


NS = Path(__file__).resolve().parent
RUN = Path('D:/he_m4_assembly_evidence_consumption_001')
LABELS = ('A1', 'B1')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(content)


def json_save(path, payload):
    save(path, (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode())


def first_packet(folder, label, status, result_sha):
    original = folder / 'product_calls/call_001/RESPONSE.json'
    row = {'slot': label, 'status': status, 'slot_result_sha256': result_sha,
           'path': None, 'sha256': None, 'bytes': None}
    if not original.is_file():
        return {**row, 'reason': 'first_installed_RPC_produced_no_response'}
    raw_product = original.read_bytes()
    product = json.loads(raw_product)
    first = read(original.with_name('REQUEST.json'))
    matches = [path.parent for path in (folder / 'owner').glob('tool_*/PRODUCT_REQUEST.json')
               if read(path) == first]
    if len(matches) != 1 or product.get('id') != first['id']:
        raise ValueError(label + ' first installed RPC did not match a unique forwarded request')
    owner_path = matches[0] / 'RESPONSE.json'
    owner = read(owner_path)
    detail = read(matches[0] / 'PRODUCT_DETAIL.json')
    receipt = read(matches[0] / 'PRODUCT_RECEIPT.json')
    request = read(matches[0] / 'REQUEST.json')
    if owner['id'] != request['id'] or first['params']['arguments'] != request['params']['arguments']:
        raise ValueError(label + ' first installed RPC arguments changed')
    row.update(original_product_response_path=str(original), original_product_response_sha256=sha(raw_product),
               owner_tool=matches[0].name, owner_response_sha256=sha(owner_path.read_bytes()),
               original_request_path=str(original.with_name('REQUEST.json')),
               original_request_sha256=sha(original.with_name('REQUEST.json').read_bytes()),
               original_rpc_receipt=receipt, observed_detail=detail)
    blocks = product.get('result', {}).get('content', [])
    if product.get('result') != owner.get('result') or [b['type'] for b in blocks] != ['text']:
        return {**row, 'reason': 'first_installed_RPC_did_not_deliver_one_original_text_block'}
    raw = blocks[0]['text'].encode('utf8')
    copy = NS / 'first_packets' / (label + '.json')
    save(copy, raw)
    return {**row, 'path': str(copy), 'sha256': sha(raw), 'bytes': len(raw), 'is_error': product['result']['isError']}


def main():
    started = time.perf_counter_ns()
    answers, packets = [], []
    for label in LABELS:
        folder = RUN / 'slots' / label
        result_raw = (folder / 'SLOT_RESULT.json').read_bytes()
        result, result_sha = json.loads(result_raw), sha(result_raw)
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if label != result['slot'] or pub['result_sha256'] != result_sha:
            raise ValueError('published slot identity differs for ' + label)
        row = {'slot': label, 'status': result['status'], 'slot_result_sha256': result_sha,
               'published_ns': pub['published_ns'], 'path': None, 'sha256': None, 'bytes': None}
        if result.get('answer') is None:
            row['reason'] = 'original_slot_published_without_final_answer'
        else:
            original = folder / 'consumer/PUBLIC_FINAL.txt'
            raw = original.read_bytes()
            if sha(raw) != result['answer']['sha256'] or len(raw) != result['answer']['bytes']:
                raise ValueError('original final identity differs for ' + label)
            copy = NS / 'answers' / (label + '.txt')
            save(copy, raw)
            row.update(path=str(copy), original_path=str(original), sha256=sha(raw), bytes=len(raw))
        answers.append(row)
        packets.append(first_packet(folder, label, result['status'], result_sha))
    stopped = time.perf_counter_ns()
    meta = {'started_ns': started, 'sealed_ns': stopped, 'replacement_consumers': 0}
    json_save(NS / 'ANSWERS_SEALED.json', {**meta, 'answers': answers})
    json_save(NS / 'FIRST_PACKETS_SEALED.json', {**meta, 'first_packets': packets})
    print([(a['slot'], a['status'], a['bytes'], b['bytes']) for a, b in zip(answers, packets, strict=True)])


if __name__ == '__main__':
    main()
