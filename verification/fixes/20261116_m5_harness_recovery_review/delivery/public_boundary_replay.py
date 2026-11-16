"""Pure saved-response replay of public_request, with a local mock transport."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

OUT = Path(__file__).resolve().parent
base = runpy.run_path(str(OUT / 'check_delivery.py'))
check, read, digest = base['check'], base['read'], base['sha']

def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')

def append(path, value):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True) + '\n')

clock = SimpleNamespace(tick=0)
def now():
    clock.tick += 100
    return clock.tick

env = dict(Path=Path, copy=copy, hashlib=hashlib, json=json,
           time=SimpleNamespace(perf_counter_ns=now), save=save, append=append,
           digest=digest, read=read, correlate_archive=base['correlate'])
exec(compile(ast.Module(body=[base['function'](base['newtree'], 'public_request')], type_ignores=[]), str(base['NEW']), 'exec'), env)
summaries = []

for group in ('A', 'B'):
    origin = base['RUN'] / group
    root = OUT / 'pure_replay_R2' / group
    root.mkdir(parents=True)
    (root / 'product_full').mkdir()
    entries, registered = [], []
    owner = SimpleNamespace(runroot=root, _product_calls=0, public_requests=[], np=base['np'])
    owner.check = lambda: None
    owner._save_evidence = lambda: None
    owner._register = lambda **row: registered.append(row)
    original = base['jsonl'](origin / 'PUBLIC_REQUESTS.jsonl')

    def call(message):
        i = owner._product_calls
        source = original[i-1]
        check(message == source['request'], group + '/pure public request unchanged')
        response = copy.deepcopy(source['response'])
        rpc = root / 'mcp' / ('rpc_' + str(i).zfill(2))
        rpc.mkdir(parents=True)
        (rpc / 'TX.bin').write_bytes(Path(source['actual_TX_path']).read_bytes())
        (rpc / 'RX.bin').write_bytes(Path(source['actual_RX_path']).read_bytes())
        if source['producer_archive_index'] is not None:
            index = source['producer_archive_index']
            target = root / 'product_full' / ('call_' + str(index).zfill(3))
            target.mkdir()
            full = read(source['producer_archive']['path'])
            for frame in full.get('frames', []):
                for key in ('image_path', 'arrays_path'):
                    destination = target / Path(frame[key]).name
                    shutil.copyfile(frame[key], destination)
                    frame[key] = str(destination)
            path = target / 'SERVICE_RESULT.json'
            save(path, full)
            entry = dict(source['producer_archive'], path=str(path), sha256=digest(path),
                         started_ns=clock.tick+20, producer_returned_ns=clock.tick+50)
            entries.append(entry)
            (root / 'product_full/INDEX.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in entries), encoding='utf-8')
        owner.client.records.append(dict(index=i, started_ns=clock.tick+10,
                                        stdin_flushed_ns=clock.tick+20,
                                        received_complete_ns=clock.tick+60,
                                        closed_ns=clock.tick+80))
        return response

    owner.client = SimpleNamespace(call=call, records=[])
    outputs = []
    for row in original:
        outputs.append(env['public_request'](owner, row['request']['params']['arguments']))
    check(outputs == [r['response'] for r in original], group+'/pure original response untouched')
    check([r['producer_archive_index'] for r in owner.public_requests] == [1,None,2,3,4], group+'/pure archive sequence')
    check(len(registered) == 2, group+'/pure initial and cached frame registration')
    for frame in registered:
        check(frame['origin'] == 'product', group+'/pure original frame origin')
        check(frame['source_ref'] == 'product-binding:'+frame['extra']['producer']['host_binding_sha256'], group+'/pure current source ref')
        check(len(frame['source_face_offsets']) == len(frame['object_names'])+1, group+'/pure source offsets registered')
        check(set(frame['arrays']) == {'color','depth','owners','triangle_ids'}, group+'/pure all arrays registered')
    check(len(base['jsonl'](root/'PUBLIC_REQUESTS.jsonl')) == 5, group+'/pure all public rows persisted')
    transport_count = []
    def missing_append(message):
        transport_count.append(message)
        rpc = root / 'mcp/rpc_06'
        rpc.mkdir(parents=True)
        (rpc/'TX.bin').write_bytes(json.dumps(message).encode())
        (rpc/'RX.bin').write_bytes(json.dumps(original[2]['response']).encode())
        owner.client.records.append(dict(index=6, started_ns=clock.tick+10,
                                        stdin_flushed_ns=clock.tick+20,
                                        received_complete_ns=clock.tick+60,
                                        closed_ns=clock.tick+80))
        return copy.deepcopy(original[2]['response'])
    owner.client.call = missing_append
    try:
        env['public_request'](owner, original[2]['request']['params']['arguments'])
    except ValueError as error:
        check(str(error)=='same_producer_archive_missing', group+'/pure association failure')
    else:
        check(False, group+'/pure association failure required')
    retained = base['jsonl'](root/'PUBLIC_REQUESTS.jsonl')[-1]
    check(retained['response']==original[2]['response'],group+'/pure failed receipt preserves actual response')
    check('post_reply_binding_error' in retained and retained['producer_archive_index'] is None, group+'/pure failure persisted')
    check(len(transport_count)==1 and len(registered)==2, group+'/pure no retry or false registration')
    summaries.append(dict(group=group, original_responses=5, registered_frames=len(registered), producer_indices=[1,None,2,3,4], missing_append_failure_persisted=True, automatic_retry=0))

result = dict(status='passed', kind='mock_transport_saved_actual_response_replay', groups=summaries,
              new_Blender=0, new_raster=0, new_MCP=0, new_model=0,
              actual_product_calls=0, public_request_AST='fixed migrated runtime')
save(OUT/'PUBLIC_BOUNDARY_RESULT.json', result)
print(json.dumps(result))
