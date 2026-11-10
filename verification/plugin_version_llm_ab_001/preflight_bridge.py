"""Two explicitly auxiliary no-model MCP checks, one installed process each."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent


def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')


def main():
    folder=HERE/sys.argv[1];folder.mkdir(parents=True,exist_ok=False)
    source={'A':'e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0',
            'B':'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'}
    row=json.loads((HERE/'TASKS.json').read_text(encoding='utf8'))['cases'][0]
    for label in ('A','B'):
        out=folder/label;out.mkdir();fixture=out/'fixture.json';save(fixture,{'cases':[row]})
        venv=ROOT/'.plugin_ab_runtime'/label/'venv';cell=out/'cell.json'
        save(cell,{'audit_dir':str((out/'bridge').resolve()),'fixture_input':str(fixture.resolve()),
            'blend_file':str(ROOT/'verification/arch_expert_entry_opt_001/actual_run_01/new_owned_setup/fixture.blend'),
            'expected_install_root':str(venv/'Lib/site-packages'),'expected_source_sha256':source[label]})
        commands=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{}}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'describe_task','arguments':{}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'run_arm_goal','arguments':{'event_id':row['event_id']}}},
            {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'run_arm_goal','arguments':{'event_id':row['event_id']}}}]
        encoded=''.join(json.dumps(c)+'\n' for c in commands).encode()
        mark=time.perf_counter_ns()
        process=subprocess.Popen([str(venv/'Scripts/python.exe'),'-I','-B','-X','utf8',str(HERE/'bridge.py'),'--cell',str(cell)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stdout,stderr=process.communicate(encoded,timeout=90)
        (out/'STDOUT.jsonl').write_bytes(stdout);(out/'STDERR.log').write_bytes(stderr)
        responses=[json.loads(line) for line in stdout.splitlines()]
        result={'scope':'auxiliary_no_model_protocol_preflight','model_calls':0,'returncode':process.returncode,
            'elapsed_ns':time.perf_counter_ns()-mark,'responses':responses,'passed':False}
        try:
            assert process.returncode==0 and len(responses)==5
            assert all('error' not in r for r in responses),responses
            first=json.loads(responses[3]['result']['content'][0]['text'])
            replay=json.loads(responses[4]['result']['content'][0]['text'])
            assert first['status']=='satisfied' and first['setter_returns']==2,first
            assert replay['replayed'] and replay['new_setter_count']==0,replay
            bridge=json.loads((out/'bridge/BRIDGE_RESULT.json').read_text(encoding='utf8'))
            child=json.loads((out/'bridge/CHILD_INSTALL_IDENTITY.json').read_text(encoding='utf8'))
            assert child['runtime_identity']['source_kind']=='installed_distribution'
            assert child['runtime_identity']['source_sha256']==source[label]
            assert bridge['process_exit']['closed'] and bridge['process_exit']['returncode']==0
            assert bridge['cost_counts']['arm_ledger_validation']==(2 if label=='A' else 1)
            assert len([c for c in bridge['rpc'] if c['command']=='correct_arm_axial'])==1
            assert (out/'bridge/FINAL_NATIVE.json').exists() and (out/'bridge/CHILD_CLEANUP.json').exists()
            result['passed']=True
        except BaseException as exc:result['failure']=repr(exc)
        save(out/'RESULT.json',result)
        print(json.dumps({'label':label,'passed':result['passed'],'result':str(out/'RESULT.json')}))
        if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
