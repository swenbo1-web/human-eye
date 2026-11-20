"""Offline control of formal geometric evidence using the original qualification PNGs."""

import argparse
import base64
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import formal


def archived_qualification_bindings(label, slot):
    reply = formal.read(slot / 'client/call_01/RESPONSE.json')
    facts = reply['result']['content']
    formal.require(reply['result']['isError'] is False, 'original_tool_response_failed')
    if label == 'QN':
        formal.require([x['type'] for x in facts] == ['text', 'text', 'image', 'text', 'image'],
                       'native_control_block_order_differs')
        records = [(facts[index - 1]['text'].removesuffix(' (512x512, image/png)'), index, None)
                   for index in (2, 4)]
    else:
        formal.require([x['type'] for x in facts] == ['text', 'image', 'image', 'image'],
                       'product_control_block_order_differs')
        tool = slot / 'owner/tool_01'
        producer = formal.read(tool / 'PRODUCT_RECEIPT.json')['producer_archive']
        full = formal.verified(producer['path'], producer['sha256'], slot)
        records = [(row['image_ref'], index, row['frame_identity'])
                   for index, row in enumerate(json.loads(full)['frames'], 1)]
    delivered = {}
    for ref, index, identity in records:
        content = facts[index]
        formal.require(content['mimeType'] == 'image/png' and ref, 'unbound_original_control_image')
        raw = base64.b64decode(content['data'], validate=True)
        delivered[ref] = [{'MCP_content_block': index, 'PNG_sha256': formal.digest(raw),
                           'PNG_bytes': len(raw), 'frame_identity': identity}]
    return delivered


def main(output):
    binding = formal.read(formal.ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json')
    sys.path.insert(0, binding['dependency_root'])
    expected = formal.truth()
    result = {'passed': False, 'scope': 'Actual qualification geometry/PNG, synthetic transport classification.',
              'new_Blender_starts': 0, 'new_model_starts': 0, 'slots': {}}
    for label in ('QN', 'QP'):
        slot = formal.RECOVERY_RUNTIME / 'slots' / label
        original = formal.read(slot / 'SLOT_RESULT.json')
        terminal, final = formal.terminal(slot, original, expected['asset_sha256'])
        bindings = archived_qualification_bindings(label, slot)
        with patch.object(formal, 'delivered_images', return_value=bindings):
            checked = formal.frame_checks(slot, terminal, expected)
        formal.require(set(checked) == set(bindings) and all('error' not in r for r in checked.values()),
                       'old_actual_frame_could_not_be_scored/' + label)
        for name, view in (('M02', 'SCENE'), ('M09', 'LEFT')):
            formal.require(any(row['view'] == view and row['witnesses'][name]['qualifies'] for row in checked.values()),
                           'old_actual_local_frame_witness_failed/' + label + '/' + name)
        formal.require(not any(row['witnesses']['M06']['qualifies'] for row in checked.values()),
                       'old_covered_region_erroneously_qualified/' + label)
        ref = next(iter(bindings))
        altered = copy.deepcopy(bindings)
        altered[ref][0]['PNG_sha256'] = '0' * 64
        with patch.object(formal, 'delivered_images', return_value=altered):
            rejected = formal.frame_checks(slot, terminal, expected)
        formal.require(rejected[ref]['error'] == 'delivered_reference_does_not_bind_this_frame',
                       'altered_delivery_pin_was_not_rejected/' + label)
        result['slots'][label] = {'current_read_only': final, 'frames': checked, 'altered_PNG_binding_rejected': True}
    result['passed'] = True
    formal.write(output, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output)
