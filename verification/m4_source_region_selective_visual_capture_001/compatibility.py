"""Check the installed stdio default and old reference admission without geometry reads."""
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from experiment import ROOT, BASE_BINDING, B_BINDING, PYTHON, stable, load, save, reference_inputs, need


def request(seq,method,params):
    return {'jsonrpc':'2.0','id':seq,'method':method,'params':params}


def probe(binding_path, slot, reference):
    slot.mkdir(parents=True,exist_ok=False)
    binding=load(binding_path)
    config=slot/'PRODUCT_CONFIG.json'
    save(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'expected_identity':{'source_sha256':binding['source_sha256']},
        'project_root':binding['install_root'],'state_file':str(slot/'product_state.json'),
        'audit_file':str(slot/'product_audit.jsonl'),'request_budget_s':5,
        'blender':{'host':'127.0.0.1','port':1,'timeout_s':1}})
    wrong={'query':{**reference['M21']['query'],'mode':'source_region_visual'},'include_image':True}
    wire=b''.join(stable(x) for x in (request(1,'initialize',{}),request(2,'tools/list',{}),
                   request(3,'tools/call',{'name':'human_eye_scene_observe','arguments':wrong})))
    (slot/'STDIO_TX.bin').write_bytes(wire)
    result=subprocess.run([str(PYTHON),'-IB','-X','utf8',str(HERE/'stdio_entry.py'),
           'A',str(binding_path),str(config),str(slot)],input=wire,capture_output=True,timeout=30)
    (slot/'STDIO_RX.bin').write_bytes(result.stdout)
    (slot/'STDIO_STDERR.bin').write_bytes(result.stderr)
    result.check_returncode()
    hello,directory,rejection=map(json.loads,result.stdout.splitlines())
    need(hello['id']==1 and hello['result']['_meta']['human_eye']['source_sha256']==binding['source_sha256'],
         'compatibility_wrong_runtime')
    need(directory['id']==2 and rejection['id']==3 and rejection['result']['isError'] is True,'default_scoped_mode_not_rejected')
    need(json.loads(rejection['result']['content'][0]['text'])['error']=='source_region_visual_disabled'
         if binding_path==B_BINDING else 'error' in json.loads(rejection['result']['content'][0]['text']),
         'unexpected_default_rejection')
    ended=load(slot/'STDIO_WORKER_EOF.json')
    need(not ended['producer_calls'] and not ended['render_attempts'],'compatibility_unexpected_geometry')
    legacy={'query':{'mode':'source_region','region_ref':reference['M21']['producer']['region_ref'],
                      'reference':reference['M21']['query']['reference'],'requested_facts':['surface_proximity']},
            'include_image':True,'response_detail':'full'}
    code='import json,sys;sys.path[:0]=sys.argv[1:3];from human_eye_plugin.live_spatial_mcp import _validate_arguments;'
    code+="print(json.dumps(_validate_arguments('human_eye_scene_observe',json.loads(sys.argv[3]))))"
    ref=subprocess.run([str(PYTHON),'-IB','-X','utf8','-c',code,binding['install_root'],binding['dependency_root'],
                        json.dumps(legacy)],capture_output=True,timeout=20)
    (slot/'LEGACY_REF_ADMISSION_STDOUT.bin').write_bytes(ref.stdout)
    (slot/'LEGACY_REF_ADMISSION_STDERR.bin').write_bytes(ref.stderr)
    ref.check_returncode()
    need(json.loads(ref.stdout) is None,'old_reference_shape_changed')
    return directory['result']['tools']


def main():
    start=perf_counter_ns()
    reference=reference_inputs()
    root=ROOT/'preflight_compatibility'
    a=probe(BASE_BINDING,root/'A',reference)
    b=probe(B_BINDING,root/'B-standard',reference)
    need(a==b,'candidate_standard_tools_list_changed')
    save(root/'RESULT.json',{'passed':True,'default_directories_equal':True,
         'legacy_ref_request_admitted_in_both':True,'formal_blender':0,'images':0,
         'note':'shape of sealed legacy ref validated independently; no cross-process dereference attempted',
         'elapsed_ns':perf_counter_ns()-start,'tool_count':len(a)})


if __name__=='__main__':
    main()
