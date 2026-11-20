"""Read typed MCP diagnostics without changing the original response."""

import hashlib
import json
from pathlib import Path
import re
import runpy
import time


ROOT = Path(__file__).resolve().parents[3]
IMAGE_CHECK = ROOT / 'verification/m4_cross_scale_live_qualification_001/checks/delivery.py'
DECODE = runpy.run_path(str(IMAGE_CHECK))['decode_image']
CAPTION = re.compile(r'((?:native-image|active-host-image):[0-9a-f]{64}) \(512x512, image/png\)')
TABLE = {'image_ref', 'image_sha256', 'native_content_block_index', 'scope_id', 'frame_identity', 'camera_identity'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_content(response, *, contract='ordinary', expected_png=None, expected_refs=None, fact_index=None):
    """Parse the designated fact body, then verify images against their original references."""
    result = response.get('result', {})
    content = result.get('content')
    require(result.get('isError') is False and isinstance(content, list), 'successful_typed_diagnostic_result_required')
    require(contract in ('ordinary', 'active_region_task'), 'diagnostic_contract_unsupported')
    require(all(isinstance(b, dict) and (b.get('type') == 'image' or
                 b.get('type') == 'text' and isinstance(b.get('text'), str)) for b in content), 'unknown_content_block')
    if contract == 'active_region_task':
        require(fact_index in (None, 0), 'product_fact_index_fixed')
        fact_index = 0
    fact = None
    if fact_index is not None:
        require(type(fact_index) is int and 0 <= fact_index < len(content) and
                content[fact_index]['type'] == 'text', 'designated_fact_text_absent')
        try:
            fact = json.loads(content[fact_index]['text'])
        except (TypeError, ValueError) as error:
            raise ValueError('designated_fact_text_invalid_JSON') from error
        require(type(fact) is dict, 'designated_JSON_fact_object_required')

    product_rows = {}
    if contract == 'active_region_task':
        require(fact.get('schema') == 'active-observation-region-task-brief-v1' and
                all(b['type'] == 'image' for b in content[1:]), 'single_product_fact_and_image_blocks_required')
        table = fact.get('images') or {}
        columns, rows = table.get('columns'), table.get('rows')
        require(type(columns) is list and len(columns) == len(set(columns)) and TABLE <= set(columns) and
                type(rows) is list and len(rows) == len(content) - 1, 'product_image_index_table_changed')
        for index, row in enumerate(rows, 1):
            require(type(row) is list and len(row) == len(columns), 'product_image_table_row_changed')
            metadata = dict(zip(columns, row, strict=True))
            require(type(metadata['native_content_block_index']) is int and
                    metadata['native_content_block_index'] == index, 'product_native_content_order_changed')
            product_rows[index] = metadata

    images, texts = [], []
    for index, block in enumerate(content):
        if block['type'] == 'text':
            item = block['text']
            texts.append({'content_index': index, 'type': 'fact' if index == fact_index else 'text', 'text': item,
                          'UTF8_bytes': len(item.encode()), 'UTF8_sha256': digest(item.encode())})
            if CAPTION.fullmatch(item) and index != fact_index:
                require(contract == 'ordinary' and index + 1 < len(content) and
                        content[index + 1]['type'] == 'image', 'orphan_image_caption')
            continue
        row = {'index': len(images) + 1, 'content_index': index, 'size_px': [512, 512]}
        if contract == 'ordinary':
            match = CAPTION.fullmatch(content[index - 1].get('text', '')) if index > 0 and index - 1 != fact_index else None
            require(match is not None, 'ordinary_image_ref_caption_required')
            row.update(ref=match.group(1), caption_index=index - 1)
            texts[-1]['type'] = 'image_caption'
        else:
            metadata = product_rows[index]
            row.update(ref=metadata['image_ref'], scope_id=metadata['scope_id'],
                       frame_identity=metadata['frame_identity'], camera_identity=metadata['camera_identity'])
        raw = DECODE(block)
        png_sha = digest(raw)
        if contract == 'active_region_task':
            require(png_sha == product_rows[index]['image_sha256'], 'product_image_sha256_or_order_changed')
        if expected_png is not None:
            require(expected_png.get(row['ref']) == raw, 'image_bytes_do_not_match_bound_ref')
        row.update(PNG_sha256=png_sha, PNG_bytes=len(raw), base64_characters=len(block['data']),
                   consumer_read_confirmed=True)
        images.append((row, raw))

    refs = [row['ref'] for row, _ in images]
    if expected_refs is not None:
        require(refs == list(expected_refs), 'original_image_reference_order_changed')
    if expected_png is not None:
        require(set(refs) == set(expected_png), 'bound_ref_coverage_changed')
    return fact, texts, images


def inspect_images(response, output_directory, *, contract='ordinary', expected_png=None, expected_refs=None, fact_index=None):
    started = time.perf_counter_ns()
    fact, texts, observed = verify_content(response, contract=contract, expected_png=expected_png,
                                          expected_refs=expected_refs, fact_index=fact_index)
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for row, raw in observed:
        path = output / f"image_{row['index']:02d}.png"
        path.write_bytes(raw)
        rows.append({**row, 'path': str(path)})
    closed = time.perf_counter_ns()
    value = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started,
             'text': fact, 'text_blocks': texts, 'images': rows, 'image_blocks_read': len(rows),
             'PNG_bytes': sum(row['PNG_bytes'] for row in rows),
             'base64_characters': sum(row['base64_characters'] for row in rows),
             'model_image_consumption': 'not_tested', 'model_calls': 0}
    with (output / 'READBACK.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    return value
