"""Independent offline audit; no candidate imports or product execution."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import traceback
from PIL import Image

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
DELIVERY = REPO / 'verification/m4_active_observation_brief_delivery_001'
OUT = Path(__file__).parent / 'transport_results.json'
checks, evidence = [], {}

def check(label, condition, detail=None):
    checks.append({'check': label, 'passed': bool(condition), **({'detail': detail} if detail is not None else {})})

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def load(path):
    return json.loads(path.read_bytes())

def main():
    archive = load(DELIVERY / 'EXTERNAL_ARCHIVE.json')
    paths = {row['original_relative_path']: REPO / row['archive_path'] for row in archive['files']}
    def raw(rel):
        return paths[rel].read_bytes()
    def obj(rel):
        return json.loads(raw(rel))
    inputs = obj('payload/inputs/INPUTS.json')
    prior_path = REPO / 'verification/m4_active_observation_host_bridge_001/EXTERNAL_ARCHIVE.json'
    prior = load(prior_path)
    prior_map = {row['archive_path']: row for row in prior['files']}
    check('prior_manifest_hash', sha(prior_path.read_bytes()) == inputs['source_archive_manifest_sha256'])
    for row in archive['files']:
        data = (REPO / row['archive_path']).read_bytes()
        check('archive:' + row['original_relative_path'], len(data) == row['bytes'] and sha(data) == row['sha256'])
    expected_cases = ['ordinary', 'same_source_repeat', 'recovery_rename_baseline', 'renamed_source', 'nonplanar_source']
    check('five_case_order', [c['case'] for c in inputs['cases']] == expected_cases)
    historical = {}
    input_pngs = 0
    input_text_bytes = 0
    for case in inputs['cases']:
        name = case['case']
        data = raw('payload/inputs/' + case['raw_response'])
        original = (REPO / case['original_archive_RX_path']).read_bytes()
        row = prior_map[case['original_archive_RX_path']]
        check(name + ':original_RX', data == original and sha(original) == row['sha256'] == case['raw_response_sha256'])
        check(name + ':original_RX_origin', case['historical_original_RX_path'] == row['original_path'])
        response = json.loads(data)
        content = response['result']['content']
        value = json.loads(content[0]['text'])
        historical[name] = (case, response, value)
        check(name + ':historical_RPC', response['id'] == name and response['result']['isError'] is False)
        check(name + ':input_block_count', len(case['images']) == len(value['frames']) == len(content) - 1)
        text_len = len(content[0]['text'].encode('utf8'))
        check(name + ':historical_text_bytes', text_len == case['original_public_text_UTF8_bytes'])
        input_text_bytes += text_len
        for i, image in enumerate(case['images'], 1):
            data = raw('payload/inputs/' + image['file'])
            original = (REPO / image['original_archive_path']).read_bytes()
            old = prior_map[image['original_archive_path']]
            check(f'{name}:PNG{i}:original', data == original and sha(data) == image['sha256'] == old['sha256'])
            check(f'{name}:PNG{i}:historical_block', data == base64.b64decode(content[i]['data'], validate=True))
            frame = value['frames'][i-1]
            check(f'{name}:PNG{i}:source_ref', image['source_image_path'] == frame['image_path'] == old['original_path'] and image['image_ref'] == frame['image_ref'])
            check(f'{name}:PNG{i}:hash_size', image['sha256'] == frame['image_sha256'] and image['bytes'] == len(data) == frame['PNG_bytes'])
            input_pngs += 1
        mapping = obj('run/replay_01/server/injected/' + name + '/PATH_MAPPING.json')
        mapped = obj('run/replay_01/server/injected/' + name + '/MAPPED_VALUE.json')
        reverse = copy.deepcopy(mapped)
        changes = mapping['path_changes']
        expected_pointers = {f'/frames/{i}/image_path' for i in range(len(case['images']))} | {f'/facts/observations/{i}/image_path' for i in range(len(case['images']))}
        check(name + ':mapping_pointer_set', {r['pointer'] for r in changes} == expected_pointers)
        check(name + ':mapping_count', len(changes) == len(expected_pointers))
        pairs = {image['source_image_path']: str((Path('D:/he_brief_001/payload/inputs') / image['file']).resolve()) for image in case['images']}
        for change in changes:
            segments = change['pointer'].split('/')[1:]
            node = reverse
            for seg in segments[:-1]:
                node = node[int(seg)] if isinstance(node, list) else node[seg]
            check(name + ':mapping:' + change['pointer'], segments[-1] == 'image_path' and node[segments[-1]] == change['mapped'] == pairs[change['original']])
            node[segments[-1]] = change['original']
        check(name + ':mapped_value_only_image_path', reverse == value)
    check('input_text_sum', input_text_bytes == 101824)
    check('input_png_count', input_pngs == 8)
    records, responses, png_records = [], {}, []
    tx_total = rx_total = text_total = png_total = base64_total = 0
    raw_stdout = b''
    for index in range(1,18):
        prefix = f'run/replay_01/stdio/rpc_{index:02d}/'
        tx, rx = raw(prefix + 'TX.bin'), raw(prefix + 'RX.bin')
        request, response = json.loads(tx), json.loads(rx)
        receipt = obj(prefix + 'RECEIPT.json')
        tx_total += len(tx)
        rx_total += len(rx)
        raw_stdout += rx
        check(f'RPC{index}:saved_response_equals_wire', response == obj(prefix + 'RESPONSE.json'))
        check(f'RPC{index}:id_pair', request['id'] == response['id'])
        check(f'RPC{index}:JSONRPC', request['jsonrpc'] == response['jsonrpc'] == '2.0')
        check(f'RPC{index}:single_record', len(tx.splitlines()) == len(rx.splitlines()) == 1)
        if index == 1:
            check('initialize', request['method'] == 'initialize' and response['result']['serverInfo']['name'] == 'human-eye-live-spatial')
            continue
        if index == 2:
            check('tools_list', request['method'] == 'tools/list' and any(t['name'] == 'human_eye_scene_observe' for t in response['result']['tools']))
            continue
        case_name = expected_cases[(index-3)//3]
        detail = ('default','brief','full')[(index-3)%3]
        case, original_response, original = historical[case_name]
        request_id = case_name + '__' + detail
        responses[request_id] = response
        arguments = request['params']['arguments']
        check(request_id + ':request', request['id'] == request_id and request['method'] == 'tools/call' and request['params']['name'] == 'human_eye_scene_observe')
        check(request_id + ':detail', ('response_detail' not in arguments if detail == 'default' else arguments['response_detail'] == detail))
        check(request_id + ':query', arguments['query'] == {'mode':'active_observation'} and arguments['include_image'] is True and arguments['session_id'] == original['session_id'])
        check(request_id + ':success', response['result']['isError'] is False and 'error' not in response)
        content = response['result']['content']
        check(request_id + ':native_blocks_equal_in_order', content[1:] == original_response['result']['content'][1:])
        public = json.loads(content[0]['text'])
        readback = obj('run/replay_01/consumer/' + request_id + '/READBACK.json')
        check(request_id + ':consumer_text', readback['text'] == public)
        check(request_id + ':consumer_block_count', readback['image_blocks_read'] == len(content) - 1 == len(case['images']))
        check(request_id + ':consumer_unconfirmed', public['image_delivery']['consumer_read_status'] == 'unconfirmed' and readback['model_calls'] == 0)
        text_len = len(content[0]['text'].encode('utf8'))
        text_total += text_len
        if detail == 'full':
            reverse = copy.deepcopy(public)
            mapping = obj('run/replay_01/server/injected/' + case_name + '/PATH_MAPPING.json')
            for change in mapping['path_changes']:
                segments = change['pointer'].split('/')[1:]
                node = reverse
                for seg in segments[:-1]:
                    node = node[int(seg)] if isinstance(node, list) else node[seg]
                check(request_id + ':full_mapped:' + change['pointer'], node[segments[-1]] == change['mapped'])
                node[segments[-1]] = change['original']
            check(request_id + ':full_all_fields_exact', reverse == original)
            images = public['frames']
        else:
            check(request_id + ':brief_schema', public['schema'] == 'active-observation-brief-v1')
            table = public.get('images', {'columns': [],'rows': []})
            images = [dict(zip(table['columns'],r)) for r in table['rows']]
            check(request_id + ':brief_image_table_count', len(images) == len(content)-1)
        for j, (block, desc) in enumerate(zip(content[1:], images),1):
            decoded = base64.b64decode(block['data'], validate=True)
            frame = original['frames'][j-1]
            saved = raw('run/replay_01/consumer/' + request_id + f'/image_{j:02d}.png')
            check(request_id + f':image{j}:block_format', set(block) == {'type','mimeType','data'} and block['type'] == 'image' and block['mimeType'] == 'image/png')
            check(request_id + f':image{j}:saved', decoded == saved)
            check(request_id + f':image{j}:ref', desc['image_ref'] == frame['image_ref'] and desc['view_name'] == frame['view_name'])
            check(request_id + f':image{j}:hash', sha(decoded) == frame['image_sha256'] == desc['image_sha256'])
            if detail != 'full':
                check(request_id + f':image{j}:block_index', type(desc['native_content_block_index']) is int and desc['native_content_block_index'] == j)
            with Image.open(io.BytesIO(decoded)) as img:
                img.load()
                rgb = img.convert('RGB').tobytes()
                check(request_id + f':image{j}:decode_dimensions', img.size == (512,512) and img.format == 'PNG')
                check(request_id + f':image{j}:readback_RGB', sha(rgb) == readback['images'][j-1]['RGB_sha256'])
            png_total += len(decoded)
            base64_total += len(block['data'])
            png_records.append({'request':request_id, 'block':j, 'PNG_bytes':len(decoded), 'sha256':sha(decoded)})
        records.append({'case':case_name, 'detail':detail, 'text_UTF8_bytes':text_len, 'image_count':len(images)})
    check('stdout_complete', raw_stdout == raw('run/replay_01/stdio/stdout.raw.bin'))
    check('stderr_empty', raw('run/replay_01/stdio/stderr.raw.bin') == b'')
    for case_name in expected_cases:
        check(case_name + ':default_equals_brief', responses[case_name+'__default']['result'] == responses[case_name+'__brief']['result'])
    calls = [json.loads(line) for line in raw('run/replay_01/server/SERVICE_CALLS.jsonl').splitlines()]
    check('15_service_calls', len(calls) == 15)
    check('service_call_order', [(c['case'],c['response_detail']) for c in calls] == [(r['case'],r['detail']) for r in records])
    check('stub_zero_new_execution', all(c['actual_new_capture_calls'] == c['actual_new_prepare_calls'] == c['actual_new_raster_attempts'] == c['actual_new_local_image_constructions'] == 0 for c in calls))
    binding = obj('payload/RUN_BINDING.json')
    start = obj('run/replay_01/server/START.json')
    launch = obj('run/replay_01/stdio/START.json')
    finish = obj('run/replay_01/server/FINISH.json')
    check('installed_source_path', start['original_content_source'] == str(Path(binding['install_root'])/'human_eye_plugin/live_spatial_mcp.py'))
    check('installed_source_hash', start['original_content_source_sha256'] == sha(Path(start['original_content_source']).read_bytes()) == sha((REPO/'human_eye_plugin/live_spatial_mcp.py').read_bytes()))
    check('binding_hash', start['binding_sha256'] == sha(raw('payload/RUN_BINDING.json')))
    check('inputs_hash', start['inputs_sha256'] == sha(raw('payload/inputs/INPUTS.json')))
    check('nonrepo_cwd', Path(launch['cwd']).resolve() != REPO.resolve() and str(Path(launch['cwd']).resolve()).startswith('D:\\he_brief_001\\'))
    check('source_bound_finish', finish['source_error'] is None and finish['failure'] is None and finish['pid'] == start['pid'] and finish['service_calls'] == 15)
    check('24_images', len(png_records) == 24)
    check('sum_wire_bytes', (tx_total,rx_total) == (3832,311634))
    check('sum_text_png_base64', (text_total,png_total,base64_total) == (155154,83400,111216))
    evidence.update(historical_RX_count=5, copied_input_PNG_count=input_pngs, actual_protocol_requests=17,
                    actual_tool_responses=len(records), short_responses=10, full_responses=5,
                    native_image_blocks=len(png_records), PNG_bytes=png_total, base64_characters=base64_total,
                    TX_bytes=tx_total,RX_bytes=rx_total,public_text_UTF8_bytes=text_total,
                    cases=records,images=png_records,
                    independent_execution={'product_calls':0,'Blender_calls':0,'raster_calls':0,'model_calls':0,'RPC_replays':0},
                    source_read_findings=['Only live_spatial_mcp.py product source changed; HistoricalService, source bootstrap, instrumentation and path mapping confined to verification.',
                    'Installed actual dispatcher, PNG validation/base64, active content callable and wire serializer preserved; wrappers call originals once.',
                    'Historical generation digest/work remain historical; these are transport-replay evidence, not current Host acquisition or model quality evidence.'])

try:
    main()
except BaseException as exc:
    evidence['review_error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
result = {'schema':'independent-brief-transport-review-v1','passed':not evidence.get('review_error') and all(c['passed'] for c in checks),
          'checks':len(checks),'failed_checks':[c for c in checks if not c['passed']], 'records':checks,'evidence':evidence}
with OUT.open('x',encoding='utf8') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:result[k] for k in ('passed','checks','failed_checks')},ensure_ascii=False))
if evidence.get('review_error'):
    print(json.dumps(evidence['review_error'],ensure_ascii=False))
