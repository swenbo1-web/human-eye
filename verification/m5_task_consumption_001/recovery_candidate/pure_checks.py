"""Saved A1 correlation replay and synthetic rejection/recovery checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
NAMESPACE=HERE.parent
RUNTIME=Path('D:/he_m5_task_consume_001')


def pin(path):
    path=Path(path).resolve()
    raw=path.read_bytes()
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(value,sort_keys=True)+'\n').encode())


def encoded(records):
    return b''.join((json.dumps(row,sort_keys=True)+'\n').encode() for row in records)


def main():
    out=HERE/'PURE_01'
    out.mkdir(exist_ok=False)
    execution_events=[]
    def prohibit_actual(event,args):
        if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect','socket.bind'):
            execution_events.append(event)
            raise RuntimeError('pure_test_forbids_actual_execution:'+event)
    sys.addaudithook(prohibit_actual)
    spec=importlib.util.spec_from_file_location('_m5_archive_recovery_candidate',HERE/'owned_runtime.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks=[]
    pins=[pin(HERE/'owned_runtime.py'),pin(Path(__file__)),pin(NAMESPACE/'harness/owned_runtime.py')]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:
            raise ValueError(name)
    a1=RUNTIME/'formal/A1'
    public=[json.loads(line) for line in (a1/'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    archive_raw=(a1/'product_full/INDEX.jsonl').read_bytes()
    archive_lines=archive_raw.splitlines(keepends=True)
    archive=[json.loads(line) for line in archive_lines]
    mapped=[]
    replay=[]
    for request in public:
        before_count=sum(row['producer_returned_ns']<=request['started_ns'] for row in archive)
        after_count=sum(row['producer_returned_ns']<=request['closed_ns'] for row in archive)
        before=b''.join(archive_lines[:before_count])
        after=b''.join(archive_lines[:after_count])
        result=module.correlate_archive(before,after,request['started_ns'],request['closed_ns'],
            request['response']['result']['isError'] is True,a1/'product_full')
        mapped.append(None if result is None else result['index'])
        replay.append(dict(public_request_id=request['id'],actual_MCP_isError=request['response']['result']['isError'],
            matched_producer_index=mapped[-1],before_prefix_bytes=len(before),after_prefix_bytes=len(after),
            scope='Derived snapshots are exact prefixes of original final INDEX bytes selected by the actual recorded request windows. Original runtime is untouched.'))
    check('actual A1 maps rejection then valid replies to independent producer indices',mapped==[1,None,2,3])
    check('actual A1 two valid later replies retain successful MCP status',
          [request['response']['result']['isError'] for request in public[2:]]==[False,False])
    pins.extend([pin(a1/'PUBLIC_REQUESTS.jsonl'),pin(a1/'product_full/INDEX.jsonl')])
    pins.extend(pin(row['path']) for row in archive)
    root=out/'synthetic_product_full'
    root.mkdir()
    def record(index,begin=120,end=160,where=None):
        path=(root if where is None else where)/('call_'+str(index).zfill(3))/'SERVICE_RESULT.json'
        if not path.exists():
            dump(path,dict(result_kind='task_query',status='observed',facts={}))
        return dict(index=index,started_ns=begin,producer_returned_ns=end,path=str(path),sha256=pin(path)['sha256'])
    one=record(1)
    two=record(2)
    def reject(name,reason,before,after,is_error=False):
        try:
            module.correlate_archive(before,after,100,200,is_error,root)
        except ValueError as error:
            check(name,str(error)==reason)
        else:
            raise ValueError('accepted invalid archive:'+name)
    reject('successful reply without archive rejected','same_producer_archive_missing',b'',b'')
    check('pre-service error without archive preserved',module.correlate_archive(b'',b'',100,200,True,root) is None)
    reject('duplicate producer index rejected','same_producer_archive_duplicate_or_unordered_index',
        encoded([one]),encoded([one,one]))
    reject('multiple new producer entries rejected','same_producer_archive_multiple_new_entries',b'',encoded([one,two]))
    reject('producer from earlier request rejected','same_producer_archive_cross_request_window',b'',encoded([dict(one,started_ns=99)]))
    reject('producer completing after this reply rejected','same_producer_archive_cross_request_window',b'',encoded([dict(one,producer_returned_ns=201)]))
    other=record(1,where=out/'other_slot')
    reject('cross-slot producer path rejected','same_producer_archive_cross_slot_path',b'',encoded([other]))
    reject('changed producer hash rejected','same_producer_archive_content_changed',b'',encoded([dict(one,sha256='0'*64)]))
    reject('modified original index prefix rejected','same_producer_archive_prefix_changed',encoded([one]),encoded([dict(one,started_ns=121)]))
    reject('partial index record rejected','same_producer_archive_incomplete_index',b'',encoded([one]).rstrip(b'\n'))
    skipped=record(3)
    check('service index gaps remain independent from public request count',
          module.correlate_archive(encoded([one]),encoded([one,skipped]),100,200,False,root)['index']==3)

    class Client:
        def __init__(self,path):
            self.path=path
            self.records=[]
            self.replies=[]
            self.service_count=0
        def call(self,message):
            number=len(self.records)+1
            directory=self.path/'mcp'/('rpc_'+str(number).zfill(2))
            directory.mkdir(parents=True)
            started=time.perf_counter_ns()
            if number==1:
                value=dict(status='error',error='original validation rejection')
                result=dict(isError=True,content=[dict(type='text',text=json.dumps(value))])
            else:
                self.service_count+=1
                producer=self.path/'product_full'/('call_'+str(self.service_count).zfill(3))/'SERVICE_RESULT.json'
                value=dict(status='partial' if number==3 else 'observed',result_kind='task_query',
                    binding=dict(objects=[dict(name='M4_Far_00',object_id='mock')]),facts={})
                dump(producer,value)
                returned=time.perf_counter_ns()
                row=dict(index=self.service_count,started_ns=started,producer_returned_ns=returned,
                         path=str(producer),sha256=pin(producer)['sha256'])
                with (self.path/'product_full/INDEX.jsonl').open('ab') as stream:
                    stream.write(encoded([row]))
                result=dict(isError=False,content=[dict(type='text',text=json.dumps(value))])
            response=dict(jsonrpc='2.0',id=message['id'],result=result)
            tx=(json.dumps(message)+'\n').encode()
            rx=(json.dumps(response)+'\r\n').encode()
            (directory/'TX.bin').write_bytes(tx)
            (directory/'RX.bin').write_bytes(rx)
            closed=time.perf_counter_ns()
            self.records.append(dict(index=number,started_ns=started,stdin_flushed_ns=started,
                received_complete_ns=closed,closed_ns=closed,TX_bytes=len(tx),RX_bytes=len(rx)))
            self.replies.append(response)
            return response
    runtime=module.RootRuntime()
    runtime.consumer_deadline_ns=time.perf_counter_ns()+60_000_000_000
    runtime.poisoned=False
    runtime.native=None
    runtime.runroot=out/'runtime_mock'
    (runtime.runroot/'product_full').mkdir(parents=True)
    runtime.group='A'
    runtime.label='candidate_mock'
    runtime.binding={'source_sha256':module.PRODUCT_SHA256['A']}
    runtime._product_calls=0
    runtime.public_requests=[]
    runtime.source_reads=[]
    runtime.by_ref={}
    runtime.client=Client(runtime.runroot)
    responses=[runtime.public_request(dict(query=dict(mode='task'),include_image=False)) for _ in range(3)]
    check('full public runtime returns original rejected then observed then partial replies',
          all(result is original for result,original in zip(responses,runtime.client.replies))
          and [row['result']['isError'] for row in responses]==[True,False,False])
    check('full runtime logs actual independent producer indices',
          [row['producer_archive_index'] for row in runtime.public_requests]==[None,1,2])
    saved=[json.loads(line) for line in (runtime.runroot/'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    check('published public journal retains corrected bindings and original responses',
          [row['producer_archive_index'] for row in saved]==[None,1,2]
          and [row['response'] for row in saved]==responses
          and all('post_reply_binding_error' not in row for row in saved))
    baseline=json.loads((HERE/'BASELINE.json').read_bytes())
    check('frozen harness source unchanged',pin(baseline['source'])['sha256']==baseline['sha256'])
    run=json.loads((RUNTIME/'RUN_RESULT.json').read_bytes())
    stopped=next(row for row in run['records'] if row['slot_id']=='B3')
    stop=json.loads((RUNTIME/'ROOT_OPERATOR_STOP.json').read_bytes())
    claims=[json.loads(path.read_bytes()) for path in (RUNTIME/'budget/claims').glob('*.json')]
    b3_claims=[row for row in claims if row['label']=='B3']
    check('B3 actual zero startups/consumers distinguished from recorded dispatch failure',
          stopped['status']=='failed' and stopped['result_path'] is None and stopped['publication_path'] is None
          and not b3_claims and not (RUNTIME/'formal/B3/native/SPAWN.json').exists()
          and not (RUNTIME/'formal/B3/CONSUMER_START.json').exists() and stop['stopped_before_slot']=='B3')
    pins.extend([pin(RUNTIME/'RUN_RESULT.json'),pin(RUNTIME/'ROOT_OPERATOR_STOP.json'),
                 pin(RUNTIME/'formal/B3/ROOT_OPERATOR_STOP.json')])
    pins.extend(pin(path) for path in sorted((RUNTIME/'budget/claims').glob('*.json')))
    check('source-only execution guard observed zero actual starts',execution_events==[])
    report=dict(schema='m5-archive-recovery-candidate-pure-v1',passed=True,checks=checks,input_pins=pins,
        actual_new_Blender_MCP_model_raster_starts=0,A1_saved_replay=replay,
        stopped_B3=dict(original_dispatch_record=stopped,root_operator_stop=stop,actual_budget_claims=b3_claims,
            actual_owned_starts=0,actual_model_consumers=0,
            explanation='Root retained exclusive-directory sentinel. Formal driver recorded dispatchfailed on FileExistsError before Session, claims or consumers. Inflight slots closed normally.'),
        author_association='Author of frozen harness and recovery candidate. Root alone executed the original five formal consumers. This candidate is pure/saved-only and remains uninstalled/unexecuted in actual tasks.',
        scope='Current batch remains unchanged. No replacement sample, changed original response, reconstructed answer or claimed performance gain.')
    dump(out/'RESULT.json',report)
    print(json.dumps(dict(passed=True,checks=len(checks),report=pin(out/'RESULT.json'))))


if __name__=='__main__':
    main()
