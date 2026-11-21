"""Check the fixed two-stage CLI policy on archived full and prototype first packets."""

import argparse
import base64
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path
import struct
import sys


V = Path(__file__).resolve().parents[2]
POLICY = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
EXPECTED = {'no_image': (39717, 0), 'image': (62318, 3156)}
ORIGINAL_BODY_SHA256 = {
    'no_image': '048791d3b052c74d1f30e915f465c3e38155ea0f3d4ad3b0eaf81b62ad6fc559',
    'image': 'db06caf63baeb77534d1d94c13ea9c65f6f781b7aa47d2541ea456c78f5e77ff',
}
ORIGINAL_WIRE_SHA256 = {
    'no_image': '81541965317f29dc12e94872766fd3be36efc8b248b1053cf9a14283e56e1b0f',
    'image': 'c35cca65251f8b65f81e76776b23c0dd48c75fc033c18203c097157e309a9dce',
}
BODY_LIMIT = 10800
HEADERS = (('0.0000', 33), ('10.0000', 34), ('100.0000', 35))
TRUNCATION = re.compile(r'…\d+ (?:chars|tokens) truncated…')
FULL_FIELDS = (
    ('binding', 'binding_sha256'),
    ('binding', 'source_binding_sha256'),
    ('region_ref',),
    ('facts', 'visibility', 'reason'),
    ('facts', 'visibility', 'complete_witness'),
    ('frames',),
    ('generation_work', 'pixel_owner_work'),
    ('task_result', 'reference'),
    ('task_result', 'measurement_scope'),
    ('task_result', 'facts', 'surface_proximity', 'value', 'distance_m'),
    ('task_result', 'facts', 'surface_proximity', 'value', 'nearest_witness'),
    ('task_result', 'source_mapping', 'nearest_witness'),
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


@lru_cache(maxsize=1)
def policy():
    helpers, limits = run_path(str(POLICY))['budget_helpers']()
    require((limits['MCP_bytes'], limits['history_approximate_tokens']) == (12000, 3000),
            'pinned_CLI_budget_changed')
    return helpers, limits


def packet(raw_or_result):
    helpers, _ = policy()
    if isinstance(raw_or_result, (str, Path)):
        raw_or_result = Path(raw_or_result).read_bytes()
    if isinstance(raw_or_result, bytes):
        original_wire = raw_or_result
        value = helpers['parsed'](raw_or_result)
    else:
        original_wire = None
        value = raw_or_result
    response = value.get('result', value)
    require(response.get('isError') is False and 'structuredContent' not in response
            and 'structured_content' not in response and not response.get('_meta'),
            'expected_plain_successful_MCP_result')
    text, *images = response['content']
    require(text['type'] == 'text' and not text.get('_meta')
            and all(item['type'] == 'image' and item['mimeType'] == 'image/png'
                    and not item.get('_meta') for item in images), 'unexpected_MCP_native_content_order')
    image_bytes = [base64.b64decode(item['data'], validate=True) for item in images]
    for raw in image_bytes:
        require(raw[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                and struct.unpack('>II', raw[16:24]) == (512, 512), 'expected_original_512px_PNG')
    return response, text['text'], helpers['parsed'](text['text']), image_bytes, original_wire


def verify_binding(first, full, original_text, images):
    ref = first['diagnostic_artifact']
    require(type(ref) is dict and set(ref) == {'local_path', 'sha256', 'bytes'}
            and type(ref['bytes']) is int and ref['bytes'] == len(original_text)
            and ref['sha256'] == digest(original_text), 'diagnostic_locator_wrong_original_body')
    path = Path(ref['local_path'])
    require(path.is_absolute() and ref['local_path'] == path.as_posix()
            and not ref['local_path'].startswith('//'), 'diagnostic_locator_not_native_local_path')
    require(first['result_kind'] == full['result_kind'] == 'source_region'
            and first['region_ref'] == full['region_ref']
            and all(first[key] == full[key] for key in ('status', 'observation_status', 'read_only',
                                                        'execution_authority'))
            and all(first['binding'][key] == full['binding'][key] for key in
                    ('source_binding_sha256', 'binding_sha256')),
            'brief_does_not_reference_same_captured_full_result')
    require(all(first['task_result'][key] == full['task_result'][key] for key in
                ('facts', 'status', 'reference', 'measurement_scope'))
            and first['task_result']['source_mapping']['nearest_witness']
            == full['task_result']['source_mapping']['nearest_witness'],
            'brief_changes_region_measurement_or_witness')
    before, after = full['facts']['visibility'], first['visibility']
    require(all(before.get(key) == after.get(key) for key in
                ('status', 'view_name', 'reason', 'selected_surface_pixels', 'complete_witness',
                 'image_ref', 'frame_identity')), 'brief_changes_visible_or_unknown_evidence')
    if images:
        image, = first['images']
        frame, = full['frames']
        png, = images
        require(image['image_block_index'] == 1
                and all(image[key] == frame[key] == after['complete_witness'][key] for key in
                        ('view_name', 'frame_identity', 'image_ref'))
                and image['image_sha256'] == frame['image_sha256'] == digest(png)
                and image['local_image_path'] == Path(frame['image_path']).as_posix(),
                'brief_locator_or_image_is_not_the_original_complete_witness')
    else:
        require(first['images'] == full['frames'] == [] and after['complete_witness'] is None,
                'unexpected_image_or_witness_in_no_image_case')
    return ref


def retained_image_identity(items):
    rows = []
    for item in items:
        if item['type'] != 'input_image':
            continue
        prefix, data = item['image_url'].split(',', 1)
        require(prefix == 'data:image/png;base64' and item['detail'] == 'high',
                'CLI_native_PNG_encoding_changed')
        raw = base64.b64decode(data, validate=True)
        rows.append({'bytes': len(raw), 'sha256': digest(raw)})
    return rows


def full_cut(text, retained, helpers):
    """Locate the original UTF-8 span omitted by the known middle-truncation branches."""
    marker, = TRUNCATION.finditer(retained)
    prefix, suffix = retained[:marker.start()], retained[marker.end():]
    require(text.startswith(prefix) and text.endswith(suffix),
            'retained_full_is_not_exact_middle_truncation')
    length = len(text.encode())
    left, right = len(prefix.encode()), length - len(suffix.encode())
    require(left < right, 'invalid_archive_middle_cut')
    fields = {}
    body = helpers['parsed'](text)
    for path in FULL_FIELDS:
        node = body
        for key in path:
            if type(node) is not dict or key not in node:
                break
            node = node[key]
        else:
            span = helpers['path_byte_span'](text, path)
            fields['.'.join(path)] = {'whole_field_retained': span['end'] <= left or span['start'] >= right,
                                      'original_byte_span': [span['start'], span['end']]}
    return {'original_cut_span_UTF8': [left, right], 'original_bytes_cut': right - left,
            'replacement_marker': marker.group(), 'watched_fields': fields}


def stages(kind, response, text, image_identities, output):
    helpers, limits = policy()
    rows = []
    for seconds, header in HEADERS:
        source = helpers['model_items'](response, seconds)
        require(len(source[0]['text'].encode()) == header, 'pinned_CLI_header_bytes_changed')
        first = helpers['truncate_items'](source, limits['MCP_bytes'])
        second = helpers['truncate_items'](first, limits['history_approximate_tokens'], token_mode=True)
        for stage, retained in (('MCP', first), ('history', second)):
            heading, body = [item['text'] for item in retained if item['type'] == 'input_text']
            require(heading == source[0]['text'], 'separate_tool_title_changed')
            images = retained_image_identity(retained)
            exact = retained == source
            raw = encoded(retained)
            row = {'header_bytes': header, 'stage': stage, 'body_UTF8_bytes': len(body.encode()),
                   'body_sha256': digest(body.encode()), 'items_sha256': digest(raw), 'all_items_exact': exact,
                   'native_PNG_exact': images == image_identities, 'retained_images': images}
            if kind == 'first':
                row['locator_exact'] = exact
            elif not exact:
                row['middle_cut'] = full_cut(text, body, helpers)
            if output is not None:
                path = output / f'{kind}_{header}_{stage}.json'
                with path.open('xb') as stream:
                    stream.write(raw)
                row['raw_stage'] = {'name': path.name, 'bytes': len(raw), 'sha256': digest(raw)}
            rows.append(row)
    return rows


def audit(label, first_packet, full_packet, *, raw_output=None):
    """Read both packets, validate scope and bytes, and exercise all six CLI combinations."""
    first_result, first_text, first_body, first_png, first_wire = packet(first_packet)
    full_result, full_text, full_body, full_png, full_wire = packet(full_packet)
    first_size, full_raw = len(first_text.encode()), full_text.encode()
    require((len(full_raw), sum(map(len, full_png))) == EXPECTED[label]
            and digest(full_raw) == ORIGINAL_BODY_SHA256[label]
            and (full_wire is None or digest(full_wire) == ORIGINAL_WIRE_SHA256[label])
            and len(full_png) == (label == 'image') and full_png == first_png,
            'prototype_changed_registered_original_packet_or_PNG')
    locator = verify_binding(first_body, full_body, full_raw, first_png)
    image_identities = [{'bytes': len(raw), 'sha256': digest(raw)} for raw in full_png]
    output = None if raw_output is None else Path(raw_output)
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    first_stages = stages('first', first_result, first_text, image_identities, output)
    full_stages = stages('original_full', full_result, full_text, image_identities, output)
    passed_stages = sum(row['all_items_exact'] and row['native_PNG_exact'] and row['locator_exact']
                        for row in first_stages)
    diagnostic_full = all(not row['all_items_exact'] and row['native_PNG_exact'] for row in full_stages)
    return {'case': label, 'passed': first_size <= BODY_LIMIT and passed_stages == 6 and diagnostic_full,
            'first_body_limit_UTF8_bytes': BODY_LIMIT, 'first_body_UTF8_bytes': first_size,
            'first_body_sha256': digest(first_text.encode()), 'original_full_body_UTF8_bytes': len(full_raw),
            'original_full_body_sha256': digest(full_raw), 'native_PNG': image_identities,
            'first_wire_bytes': len(first_wire) if first_wire is not None else None,
            'first_wire_sha256': digest(first_wire) if first_wire is not None else None,
            'original_full_wire_bytes': len(full_wire) if full_wire is not None else None,
            'original_full_wire_sha256': digest(full_wire) if full_wire is not None else None,
            'artifact_locator': locator, 'first_passed_stages': passed_stages, 'first_required_stages': 6,
            'first_stages': first_stages, 'original_full_truncated_in_all_stages': diagnostic_full,
            'original_full_diagnostic_stages': full_stages, 'policy': policy()[1],
            'scope': 'Fixed local CLI replay only. This checks text and PNG retention, not host file open or model use.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label', choices=EXPECTED)
    parser.add_argument('first', type=Path)
    parser.add_argument('full', type=Path)
    parser.add_argument('--raw-output', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_with_I_B')
    result = audit(args.label, args.first, args.full, raw_output=args.raw_output)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    raise SystemExit(0 if result['passed'] else 1)
