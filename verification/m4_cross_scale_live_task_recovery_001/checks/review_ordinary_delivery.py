"""Replay the original native reply as typed MCP content, without rerunning the slot."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parents[1]
SLOT = Path('D:/he_m4_cross_scale_live_task_recovery_001/slots/QN')


def main():
    spec = importlib.util.spec_from_file_location('_frozen_recovery_qualification_checks', NS / 'qualify.py')
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    sys.path.insert(0, common.read(common.BINDING)['dependency_root'])
    original = SLOT / 'SLOT_RESULT.json'
    frozen = common.read(original)
    publication = common.read(SLOT / 'SLOT_PUBLICATION.json')
    assert publication['status'] == frozen['status'] == 'failed' and publication['result_sha256'] == common.sha(original)
    assert len(frozen['errors']) == 1 and frozen['errors'][0]['type'] == 'JSONDecodeError'
    assert frozen['closure_verification']['passed'] and frozen['independent_before_after']['passed']
    assert frozen['diagnostic_close']['confirmed'] and frozen['owner_close']['confirmed']
    args, = common.read(NS / 'inputs/DIAGNOSTIC_N.json')['calls']
    receipt = frozen['diagnostic_calls'][0]
    live = SLOT / 'client/call_01/RESPONSE.json'
    req = live.with_name('REQUEST.json')
    response, request = common.read(live), common.read(req)
    assert receipt['response_sha256'] == common.sha(live) and receipt['request_sha256'] == common.sha(req)
    assert response['id'] == request['id'] and request['params'] == args
    assert response == common.read(SLOT / 'owner/tool_01/RESPONSE.json')
    assert request == common.read(SLOT / 'owner/tool_01/REQUEST.json')
    matched = []
    for path in (SLOT / 'client/attachments').glob('bridge_*/*/TX.bin'):
        if common.read(path) == request:
            rx = path.with_name('RX.bin')
            wire = common.read(path.with_name('RECEIPT.json'))
            assert wire['origin'] == 'owner' and common.read(rx) == response
            assert (path.stat().st_size, rx.stat().st_size) == (wire['request_bytes'], wire['response_bytes'])
            matched.append({'TX_sha256': common.sha(path), 'RX_sha256': common.sha(rx), 'receipt': wire})
    assert len(matched) == 1
    result = response['result']
    contents = result['content']
    assert not result['isError'] and [x['type'] for x in contents] == ['text', 'text', 'image', 'text', 'image']
    expected = {x['object_name']: x for x in common.read(NS / 'fixture/CURRENT_TRUTH.json')['eligible']}
    native = common.native(SLOT, expected, result)
    facts = common.readbacks(SLOT, frozen)
    assert native['CLI']['passed']
    views = [record for record in native['regions'].values() if record['status'] == 'covered']
    for index, object_row in enumerate(views):
        label = contents[2 * index + 1]['text']
        assert label == object_row['ref'] + ' (512x512, image/png)'
        data = base64.b64decode(contents[2 * index + 2]['data'], validate=True)
        object_row['original_PNG_sha256'] = hashlib.sha256(data).hexdigest()
        object_row['native_content_index'] = 2 * index + 2
    for text in (contents[1]['text'], contents[3]['text']):
        try:
            json.loads(text)
        except json.JSONDecodeError:
            continue
        raise AssertionError('plain caption/JSON failure control changed')
    note = {'actual_native_geometry_images_and_CLI_replay_passed': True, 'scope': 'Post-run verification of the same QN bytes.',
            'original_slot_status': publication['status'], 'frozen_qualification_status': False,
            'admission_changed': False, 'new_business_or_model_calls': 0,
            'original_slot_sha256': common.sha(original), 'original_response_sha256': common.sha(live),
            'before_after': facts, 'native_evidence': native, 'matched_wire': matched,
            'qualification_archive_decode_reason': 'Expected one JSON text block, encountered ordinary caption text.'}
    with (NS / 'checks/ORDINARY_DELIVERY_REPLAY.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(note, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(note['actual_native_geometry_images_and_CLI_replay_passed'])


if __name__ == '__main__':
    main()
