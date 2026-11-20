"""Replay the installed MCP formatter on sealed originals without observing again."""

import argparse
import base64
import copy
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import zipfile
from contextlib import ExitStack


NS = Path(__file__).resolve().parents[1]
V = NS.parent
BRIEF = V / 'm4_cross_scale_brief_entry_001'
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
FIXED_POLICY = V / 'm1_source_region_facts_first_001/checks'
PRODUCT_BINDING = V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
TARGET = 'human_eye_plugin/live_spatial_mcp.py'
TOOL = 'human_eye_scene_observe'
FIELDS = ('area_m2', 'unit_normal_world')
ROSTER = {'M02', 'M06', 'M09'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class Evidence:
    def __init__(self):
        self.pins = {}

    def raw(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        row = {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
        require(expected is None or row['sha256'] == expected, 'source_digest_changed/' + str(path))
        require(self.pins.get(path, row) == row, 'input_changed_during_replay/' + str(path))
        self.pins[path] = row
        return raw


class Original:
    def __init__(self, evidence, ns, runtime, index_sha, stack):
        self.evidence, self.root = evidence, Path(runtime).resolve()
        self.slot = self.root / 'slots/P1'
        index = json.loads(evidence.raw(ns / 'RUNTIME_INDEX.json', index_sha))
        archive_path = self.root / 'ORIGINAL_RUNTIME.zip'
        require(len(evidence.raw(archive_path, index['archive']['sha256'])) == index['archive']['bytes'],
                'original_zip_size_changed')
        self.archive = stack.enter_context(zipfile.ZipFile(archive_path))
        self.index = {row['path']: row for row in index['files']}
        members = self.archive.namelist()
        require(len(self.index) == index['count'] == len(members) and set(members) == self.index.keys(),
                'original_zip_index_membership_changed')
        self.invocations = self.load(self.slot / 'consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
        raw_events = self.raw(self.slot / 'consumer/stdout.raw.bin').splitlines()
        self.events = {event['item']['id']: event['item'] for line in raw_events if
                       (event := json.loads(line)).get('type') == 'item.completed'
                       and event.get('item', {}).get('type') == 'mcp_tool_call'}
        self.product_log = [json.loads(line) for line in self.raw(self.slot / 'PUBLIC_REQUESTS.jsonl').splitlines()]

    def raw(self, path):
        path = Path(path).resolve()
        relative = path.relative_to(self.root).as_posix()
        row = self.index[relative]
        raw = self.evidence.raw(path, row['sha256'])
        require(raw == self.archive.read(relative) and len(raw) == row['bytes'],
                'original_archive_member_changed/' + relative)
        return raw

    def load(self, path):
        return json.loads(self.raw(path))

    def call(self, ordinal, detail, image_count, raster_count):
        owner = self.slot / 'owner' / f'tool_{ordinal:02d}'
        names = ('REQUEST.json', 'RESPONSE.json', 'PRODUCT_REQUEST.json',
                 'PRODUCT_RESPONSE.json', 'PRODUCT_RECEIPT.json')
        request, response, product_request, product_response, receipt = [self.load(owner / name) for name in names]
        arguments = request['params']['arguments']
        require(request['params']['name'] == product_request['params']['name'] == TOOL
                and product_request['params']['arguments'] == arguments and arguments['response_detail'] == detail
                and arguments['include_image'] is bool(image_count) and response['id'] == request['id'],
                'original_tool_argument_or_id_changed')
        installed, = [row for row in self.product_log if row['request']['id'] == product_request['id']]
        producer = receipt['producer_archive']
        require(installed['request'] == product_request and installed['response'] == product_response
                and installed['receipt'] == receipt['receipt'] and installed['producer_archive'] == producer
                and product_response['id'] == product_request['id'] and producer['new_observations_for_archive'] == 0,
                'original_product_receipt_link_changed')
        archive_source = self.raw(producer['path'])
        require(sha(archive_source) == producer['sha256'], 'original_producer_digest_changed')
        value = json.loads(archive_source)
        self.raw(producer['read_context'])

        invocation, = [row for row in self.invocations if row['attempt'] == ordinal]
        caller_txs = [self.root / name for name, pin in self.index.items()
                      if name.endswith('/TX.bin') and pin['sha256'] == invocation['TX_sha256']]
        tx, = caller_txs
        rx = tx.with_name('RX.bin')
        wire_result = self.raw(rx)
        event = self.events[invocation['caller_identity']['CLI_event_item_id']]
        result = response['result']
        require(json.loads(self.raw(tx)) == request and json.loads(wire_result) == response
                and sha(wire_result) == invocation['RX_sha256']
                and self.load(tx.with_name('RECEIPT.json')) == invocation['receipt']
                and result == product_response['result'] and result['isError'] is False
                and invocation['matched'] is True and invocation['tool'] == event['tool'] == TOOL
                and event['arguments'] == arguments and event['status'] == 'completed' and event['error'] is None
                and event['result']['content'] == result['content'],
                'original_request_installed_result_stdio_or_CLI_not_bound')
        header, *images = result['content']
        require(header['type'] == 'text'
                and len(header['text'].encode()) == invocation['CLI_text_UTF8_bytes']
                and len(images) == invocation['CLI_images'] == len(value['frames']) == image_count
                and value['work']['raster_attempts'] == raster_count, 'original_text_or_work_denominator_changed')
        for frame, content in zip(value['frames'], images, strict=True):
            png = self.raw(frame['image_path'])
            require(content == {'type': 'image', 'mimeType': 'image/png',
                                'data': base64.b64encode(png).decode('ascii')}
                    and sha(png) == frame['image_sha256'] and len(png) == frame['PNG_bytes'],
                    'original_producer_image_not_bound_to_CLI')
        return {'source': producer['path'], 'source_sha256': producer['sha256'],
                'wire_sha256': sha(wire_result), 'arguments': arguments, 'ordinal': ordinal,
                'response': result, 'work': value['work']}


def run_formatter(install, dependency, cases):
    worker = """
import hashlib
import json
from pathlib import Path
import sys
install, dependency = map(Path, sys.argv[1:])
sys.path[:0] = [str(install), str(dependency)]
from human_eye_plugin import live_spatial_mcp
path = Path(live_spatial_mcp.__file__).resolve()
if path != install / 'human_eye_plugin/live_spatial_mcp.py':
    raise ValueError('formatter_import_not_from_expected_isolated_install')
results = []
for case in json.load(sys.stdin):
    value = json.loads(Path(case['source']).read_bytes())
    original = json.dumps(value, ensure_ascii=True, allow_nan=False)
    audit = {}
    result = live_spatial_mcp._tool_result(value, is_error=False,
        response_detail=case['arguments']['response_detail'], active_delivery_audit=audit)
    if json.dumps(value, ensure_ascii=True, allow_nan=False) != original:
        raise ValueError('public_formatter_mutated_original_producer_value')
    results.append({'result': result, 'audit': audit, 'work': value['work']})
print(json.dumps({'formatter': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'tool_catalogues': [live_spatial_mcp.LIVE_MCP_TOOLS_SCHEMA,
                                      live_spatial_mcp.SPATIAL_TASK_TOOLS_SCHEMA],
                  'results': results}, ensure_ascii=True, allow_nan=False))
"""
    args = [{key: case[key] for key in ('source', 'arguments')} for case in cases]
    result = subprocess.run([sys.executable, '-I', '-B', '-c', worker, str(install), str(dependency)],
        check=True, input=json.dumps(args).encode(), capture_output=True, timeout=60)
    return json.loads(result.stdout)


def verify_images(body, wire):
    table = body['images']
    images = [dict(zip(table['columns'], row, strict=True)) for row in table['rows']]
    require(len(images) == len(wire['content']) - 1, 'brief_image_table_count_mismatch')
    for index, image in enumerate(images, start=1):
        raw = base64.b64decode(wire['content'][index]['data'], validate=True)
        require(image['native_content_block_index'] == index and image['image_sha256'] == sha(raw),
                'brief_image_table_index_or_digest_changed')
    by_ref = {row['image_ref']: row for row in images}
    for row in body['region_task']['rows']:
        if row['complete_witness'] is not None:
            witness = row['complete_witness']
            evidence = by_ref[witness['image_ref']]
            require(all(witness[key] == evidence[key] for key in
                        ('scope_id', 'frame_identity', 'view_name', 'native_content_block_index')),
                    'brief_local_witness_reference_changed')
    return images


def verify_rows(old, new):
    require(new['schema'] == old['schema'] == 'active-observation-region-task-brief-v1',
            'brief_region_task_schema_changed')
    remaining = copy.deepcopy(new)
    regions = {}
    for row in remaining['region_task']['rows']:
        name = row['object_name']
        require(name not in regions, 'duplicate_candidate_region')
        area, normal = [row.pop(key) for key in FIELDS]
        require(type(area) in (float, int) and math.isfinite(area) and area > 0
                and type(normal) is list and len(normal) == 3
                and all(type(value) in (float, int) and math.isfinite(value) for value in normal)
                and abs(math.hypot(*normal) - 1) <= 2e-15, 'candidate_region_numeric_facts_invalid/' + name)
        with localcontext() as context:
            context.prec = 90
            root = Decimal(10).sqrt()
            exact = ((root / 256, 0, -1 / root, 3 / root) if name == 'M09' else
                     (Decimal(1) / 64, 0, 0, 1))
            actual = [area, *normal]
            errors = [abs(Decimal.from_float(float(value)) - target)
                      for value, target in zip(actual, exact, strict=True)]
            require(all(error <= 2 * Decimal.from_float(math.ulp(float(target)))
                        for error, target in zip(errors, exact, strict=True)),
                    'candidate_wire_geometry_differs_from_independent_decimal/' + name)
        regions[name] = {**dict(zip(FIELDS, (area, normal), strict=True)),
                         'independent_decimal_area_normal': [str(target) for target in exact],
                         'absolute_errors_area_normal': [str(error) for error in errors]}
    require(remaining == old and regions.keys() == ROSTER, 'brief_contract_changed_outside_numeric_fields')
    return regions


def verify_cli(helper, policy, wire):
    body = wire['content'][0]['text']
    required = {key: compact(json.loads(body)[key]) for key in
                ('binding', 'region_task', 'images', 'witness_pixels')}
    outcomes = []
    for seconds in ('0.0000', '10.0000', '100.0000'):
        emitted = helper['model_items'](wire, seconds)
        mcp = helper['truncate_items'](emitted, policy['MCP_bytes'])
        final = helper['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
        retained = ''.join(item['text'] for item in final[1:] if item['type'] == 'input_text')
        require(final == emitted and retained == body and all(serialized in retained for serialized in required.values()),
                'candidate_CLI_fallback_text_or_images_clipped/' + seconds)
        outcomes.append({'wall_time_header_sample': seconds,
                         'body_utf8_bytes': len(retained.encode()),
                         'header_utf8_bytes': len(final[0]['text'].encode()),
                         'all_content_unchanged': True})
    return outcomes


def compare(cases, baseline, candidate, helper, policy, precheck_base):
    outcomes = []
    for case, old, new in zip(cases, baseline['results'], candidate['results'], strict=True):
        original = case['response']
        old_wire, new_wire = old['result'], new['result']
        original_text, old_text, new_text = [wire['content'][0]['text'] for wire in (original, old_wire, new_wire)]
        original_body, old_body, new_body = map(json.loads, (original_text, old_text, new_text))
        require(old['work'] == new['work'] == case['work']
                and original_body == old_body and len(old_text.encode()) == len(original_text.encode())
                and original['content'][1:] == old_wire['content'][1:] == new_wire['content'][1:]
                and original['isError'] is old_wire['isError'] is new_wire['isError'] is False,
                'old_formatter_or_original_png_work_semantics_changed')
        record = {key: case[key] for key in ('arguments', 'ordinal', 'source_sha256', 'wire_sha256', 'work')}
        record.update(original_text_utf8_bytes=len(original_text.encode()),
                      candidate_text_utf8_bytes=len(new_text.encode()),
                      text_byte_delta=len(new_text.encode()) - len(original_text.encode()),
                      original_producer_path=case['source'], ordered_original_PNGs_unchanged=True,
                      original_PNGs=len(original['content']) - 1)
        if case['arguments']['response_detail'] == 'brief':
            record['regions'] = {} if precheck_base else verify_rows(old_body, new_body)
            record['image_table'] = verify_images(new_body, new_wire)
            record['offline_CLI_budget'] = verify_cli(helper, policy, new_wire)
        else:
            require(old_wire == new_wire, 'full_formatter_bytes_changed_on_same_archived_input')
            record['full_wire_byte_identical_on_same_archived_input'] = True
        outcomes.append(record)
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path)
    parser.add_argument('--precheck-base', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_python_I_B')
    require(bool(args.install_root) is not args.precheck_base, 'use_one_of_install_root_or_precheck_base')
    evidence = Evidence()
    binding = json.loads(evidence.raw(PRODUCT_BINDING,
        'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'))
    baseline_root = Path(binding['install_root']).resolve()
    install = baseline_root if args.precheck_base else args.install_root.resolve()
    dependency = Path(binding['dependency_root']).resolve()
    source, = [row for row in binding['source_manifest'] if row['path'] == TARGET]
    evidence.raw(baseline_root / TARGET, source['sha256'])
    if not args.precheck_base:
        require(install != baseline_root and sha(evidence.raw(install / TARGET)) != source['sha256'],
                'one_candidate_install_must_differ_from_historical_formatter')
    historical_freeze = json.loads(evidence.raw(FORMAL / 'FROZEN.json',
        '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c'))
    frozen = {Path(row['path']).resolve(): row['sha256'] for row in historical_freeze['direct_inputs']}
    helper_path, policy_path = [FIXED_POLICY / name for name in
                                ('client_budget_replay.py', 'CLIENT_BUDGET_REVIEW.json')]
    evidence.raw(helper_path, frozen[helper_path.resolve()])
    helper = runpy.run_path(str(helper_path))
    policy = json.loads(evidence.raw(policy_path, frozen[policy_path.resolve()]))['policy']
    with ExitStack() as stack:
        fresh = Original(evidence, BRIEF, 'D:/he_m4_cross_scale_brief_entry_001',
            '7625392863637b311c5c6a1921a4eaac386845e5acbcd30c452a2c1d2e385fbb', stack)
        formal = Original(evidence, FORMAL, 'D:/he_m4_cross_scale_live_task_formal_001',
            'aa0e6e76930b58e4928683e6318428b72cedf30a3af1008cb12595b1bfba27d3', stack)
        cases = (fresh.call(1, 'brief', 3, 4), fresh.call(2, 'full', 0, 0),
                 formal.call(1, 'full', 3, 4), formal.call(11, 'brief', 3, 0))
    baseline = run_formatter(baseline_root, dependency, cases)
    candidate = baseline if args.precheck_base else run_formatter(install, dependency, cases)
    require(baseline['sha256'] == source['sha256']
            and candidate['sha256'] == sha(evidence.raw(candidate['formatter'])),
            'formatter_changed_during_candidate_replay')
    require(baseline['tool_catalogues'] == candidate['tool_catalogues'], 'candidate_tool_catalogue_changed')
    outcomes = compare(cases, baseline, candidate, helper, policy, args.precheck_base)
    if not args.precheck_base:
        output = NS / 'checks/PROJECTION_REPLAY.json'
        record = {'schema': 'm4-cross-scale-geometry-facts-projection-replay-v1', 'passed': True,
                  'scope': 'Same sealed producer data and PNGs fed to both installed formatters. '
                           'Archived producer object keys were sorted, so actual old public JSON is compared by value '
                           'and UTF-8 length. Old versus candidate full replay is also byte identical.',
                  'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
                  'baseline_formatter_sha256': baseline['sha256'], 'candidate_formatter_sha256': candidate['sha256'],
                  'installed_tool_catalogues_equal': True,
                  'installed_tool_catalogues_sha256': sha(compact(candidate['tool_catalogues']).encode()),
                  'original_producer_values_not_mutated': True,
                  'CLI_budget_policy': policy, 'actual_provider_model_input': None, 'cases': outcomes,
                  'source_pins': list(sorted(evidence.pins.values(), key=lambda row: row['path']))}
        with output.open('x', encoding='utf8', newline='\n') as stream:
            json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
            stream.write('\n')
    print('Projection replay', 'baseline validated' if args.precheck_base else 'candidate validated',
          [(row['candidate_text_utf8_bytes'], row['text_byte_delta']) for row in outcomes])


if __name__ == '__main__':
    main()
