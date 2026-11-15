"""Saved-only qualification baseline. No product import or runtime startup."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m5_observe_measure_001/qualification/A_qual')
INSTALL = Path('D:/he_m4_target_002/B/product')


def load(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def run():
    result = load(RUN / 'RESULT.json')
    publication = load(RUN / 'PUBLICATION.json')
    wire = load(RUN / 'SAVED_WIRE.json')
    events = [json.loads(line) for line in (RUN / 'native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
    audit = [json.loads(line) for line in (RUN / 'audit.jsonl').read_bytes().splitlines()]
    contexts = [load(RUN / f'producer/call_{i:03d}/READ_CONTEXT.json') for i in (1, 2)]
    traces = {row['trace']['annotations']['mcp_request_id']: row['trace']
              for row in audit if row['event'] == 'request_trace'}
    checks = []

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)

    check('closed qualification transport scope', publication['passed_transport_scope'] and result['errors'] == [])
    check('publication binds exact RESULT bytes', pin(RUN / 'RESULT.json')['sha256'] == publication['result_sha256'])
    check('two registered adjacent requests', [row['id'] for row in result['requests']] == ['observe', 'measure'])
    check('two native geometry commands', [row.get('command', {}).get('command') for row in wire['steps'][:2]]
          == ['capture_active_observation', 'capture_task'])
    check('two complete native command events', [row['status'] for row in events[:2]] == ['completed', 'completed'])
    work = []
    for event in events[:2]:
        before = event['m2_work']['before']
        after = event['m2_work']['after']
        check('one resident module in command ' + str(event['sequence']), len(after) == 1 and len(before) <= 1)
        old = before[0]['work'] if before else {}
        work.append({key: value - old.get(key, 0) for key, value in after[0]['work'].items()
                     if type(value) is int})
    zero = ('to_mesh', 'triangulations', 'resource_builds', 'resource_faces_read',
            'resource_vertices_read', 'world_transforms', 'world_vertices_transformed')
    check('second command has zero counted rebuild/read/transform work', all(work[1][key] == 0 for key in zero))
    check('same resident resource revisions retained', events[1]['m2_work']['before'][0]['resources']
          == events[1]['m2_work']['after'][0]['resources'])
    check('no second resource forward', wire['steps'][1]['resources_forwarded'] == 0
          and wire['steps'][1]['resource_faces_forwarded'] == 0
          and wire['steps'][1]['resource_vertices_forwarded'] == 0)
    check('no second materialized resource arrays', all(value == 0 for value in events[1]['m2_work']['new_resource_arrays'].values()))
    states = [row['capture_state'] for row in wire['captures']]
    check('same actual generation different selection',
          all(states[0][key] == states[1][key] for key in ('instance_id', 'epoch', 'revision'))
          and states[0]['selection_key'] != states[1]['selection_key'])
    check('same retained object IDs selected for task', set(wire['captures'][1]['object_ids']).issubset(wire['captures'][0]['object_ids']))
    active = contexts[0]['after']['selections'][0]
    selected = contexts[1]['after']['selections'][-1]
    check('active no retained ReadContext normalized tuple', active['normalized'] is False and active['mesh_arrays'] == [])
    check('task newly retains normalized tuple', selected['normalized'] is True and len(selected['mesh_arrays']) == 2)
    check('context before task equals after active', contexts[1]['before'] == contexts[0]['after'])
    check('same actual source loaded payloads', all(pin(INSTALL / row['path'])['sha256'] == row['sha256'] for row in wire['loaded_source_payloads']))
    rows = []
    for request in result['requests']:
        receipt, server = request['receipt'], request['server']
        check('raw clocks ' + request['id'],
              request['complete_client_call_ns'] == request['completed_ns'] - request['started_ns']
              and request['client_flush_to_received_ns'] == receipt['received_complete_ns'] - receipt['stdin_flushed_ns']
              and server['request_to_reply_ns'] == server['reply_completed_ns'] - server['request_received_ns'])
        spans = [{key: span[key] for key in ('name', 'start_offset_ns', 'duration_ns', 'parent_span_id', 'span_id')}
                 for span in traces[request['id']]['spans']]
        rows.append(dict(id=request['id'], complete_client_call_ns=request['complete_client_call_ns'],
                         client_flush_to_received_ns=request['client_flush_to_received_ns'],
                         client_internal_pre_receipt_ns=request['client_internal_pre_receipt_ns'],
                         server_request_to_reply_ns=server['request_to_reply_ns'],
                         trace_inclusive_duration_ns=traces[request['id']]['duration_ns'],
                         spans=spans, stdio_raw_RX_bytes=receipt['RX_bytes'],
                         stdio_LF_text_bytes=server['RX_text_UTF8_LF_bytes'],
                         stdio_TX_bytes=receipt['TX_bytes']))
    check('full session recomputed', publication['complete_session_ns']
          == publication['result_published_ns'] - result['started_ns'])
    source_files = ['human_eye_plugin/blender_host.py', 'human_eye_plugin/blender_mcp_host.py',
                    'human_eye_plugin/read_context.py', 'human_eye_plugin/live_service.py']
    pins = [pin(path) for path in [Path(__file__), HERE / 'A_RUN_BINDING.json', HERE / 'REQUESTS.json']]
    pins += [pin(INSTALL / name) for name in source_files]
    pins += [pin(path) for path in sorted(RUN.rglob('*'))
             if path.is_file() and (path.suffix in {'.json', '.jsonl'}
                or path.name in {'REQUEST.bin', 'RESPONSE.bin', 'SCRIPT.py', 'RX.bin', 'TX.bin'})]
    producer = load(RUN / 'producer/call_001/SERVICE_RESULT.json')
    task_event = [row for row in audit if row['event'] == 'observe'][-1]
    report = dict(schema='m5-a-resource-baseline-v1', passed_checked_scope=True,
        author_association='Review author also wrote M5 harness and archive instrumentation. Saved records independently recomputed here; no independent authorship claim.',
        qualification_only=True, sample_count=1, actual_new_owned=0, actual_new_rasters=0,
        source_sha256=result['source_sha256'], checks=checks, input_pins=pins,
        business=dict(result['business_windows'][0], client_intercall_gap_ns=result['requests'][1]['started_ns']-result['requests'][0]['completed_ns']),
        timing=dict(requests=rows, setup_ns=result['setup_closed_ns']-result['started_ns'],
                    owned_lifecycle_ns=result['owned_lifecycle_ns'], complete_session_ns=publication['complete_session_ns'],
                    clock_scope=result['clock_scope']),
        wire=wire['steps'], host_resource_counter_deltas=work,
        new_resource_arrays=[row['m2_work']['new_resource_arrays'] for row in events[:2]],
        read_context=dict(active_normalized=False, task_normalized=True,
            same_generation=True, distinct_selection=True, retained_task_mesh_arrays=selected['mesh_arrays'],
            retained_task_array_payload_bytes=sum(row['vertices_nbytes']+row['faces_nbytes'] for row in selected['mesh_arrays']),
            measured_allocation_count=None, measured_copy_count=None, measured_temporary_or_RSS_bytes=None),
        active_generation_work=producer['work'], active_stages=producer['stages'],
        measurement_task_work=task_event['task_work'], wrapper_work=result['wrapper_work'],
        cleanup=dict(MCP_retained=result['cleanup']['MCP_retained'], native=result['cleanup']['native'],
                     worker_close_event_status=events[-1]['status'],
                     worker_close_interpretation='unknown worker event retained separately from explicit closed response, matching final fingerprint and actual owned Popen exit0/wait-reap'),
        limitations=[
            'Single A qualification. No B comparison, formal gate or performance conclusion.',
            'Zero resource counters and forwards prove the listed work was avoided. capture_cache_hits stays zero because the selected scene packet is newly assembled.',
            'ReadContext array metadata records retained task tuple identity and payload size. Active conversion arrays are outside this metadata and copy/allocation counts remain unmeasured.',
            'Native fixture full-scene fingerprints and file guards have source-derived scope. Actual whole-scene loop visits are unmeasured, their elapsed time is included.',
            'Trace, producer and host stages are inclusive with nesting. They must not be summed as disjoint costs. Server completion and client transport are separately bounded.',
            'Windows raw stdio CRLF adds one byte per response compared with pre-stdout LF text. Host marked stdout excludes the printed newline; native stdout byte count includes it.'
        ],
        next_direction=[
            'Reuse actual active capture objects for measurement, replacing the second host RPC and duplicate selected-scene binding/validation only under the frozen current-generation/source-face contract.',
            'Retain exactly one independent surface-proximity solve. Its observed 100.0657ms remains required work; do not claim it disappears through observation reuse.',
            'Evaluate any elimination of active and task geometry conversion with actual final B counters/identity and complete timings; this A metadata alone does not establish copy savings.'
        ])
    target = HERE / 'A_RESOURCE_BASELINE.json'
    target.write_bytes((json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf8'))
    markdown = '''# A 资源基线复核

本次只读取已关闭的 A 资格，样本数 1。复核作者也参与编写本批 harness 和被动归档层。

- 第二次 task 的 to_mesh、三角化、资源构建、资源顶点/面读取和世界变换增量均为 0。资源转发 0，新增资源数组 0。同一 resident 资源及修订号保留。
- 第二次仍有真实 capture_task，TCP 请求 1505 字节、响应 2634 字节，host.capture 54.948 毫秒。capture_cache_hits 为 0，选中场景包重新组装。
- Active 的 ReadContext 未保留 normalized tuple。Task 此时新增 2 个 mesh、296 点、515 面的 normalized tuple，数组元数据合计 13284 字节。复制和分配次数未测量。
- Task facts 为 100.0657 毫秒，scene.validate 为 2.5829 毫秒，其内嵌 hash 为 0.5853 毫秒。各级跨度有嵌套关系。
- 连续业务为 974.2059 毫秒，完整会话含结果 fsync 为 3401.953 毫秒。两个完整 client.call 为 784.5417 和 189.6567 毫秒，server 回写时界为 782.8491 和 172.6425 毫秒。
- 两响应原始 stdio 分别为 12451、1671 字节。LF 编码文本分别为 12450、1670 字节，差值来自实际 Windows CRLF。
- MCP 持有句柄 exit0 且已关闭，Blender owned Popen exit0 且已 wait/reap，全场初末指纹一致。Worker close 的通用事件仍为 unknown，独立保存，关闭回包和 Popen 证据已核。

优化依据是复用当前 observation 来源，省去第二次 host RPC 和所选场景重复绑定。独立 surface-proximity 求解仍须执行一次。后续 B 和正式样本决定完整收益。

所有原件和安装源的字节数、SHA256 见 JSON input_pins。只读脚本未启动产品、Blender 或 raster。
'''
    (HERE / 'A_RESOURCE_BASELINE.md').write_text(markdown, encoding='utf8')
    print(json.dumps(dict(passed=True, checks=len(checks), report=pin(target)), ensure_ascii=False))


if __name__ == '__main__':
    run()
