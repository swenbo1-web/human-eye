"""Archive the single failed integrated start and the independent successful preflights."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
sys.path[:0]=[str(NS/'harness'),str(NS)]
from common import EXTERNAL, ORIGINAL_RUN, read, save
from freeze import verify
from bridge import REGION_TASK_RULE
from evidence_check import check_catalogue


SECRETS = re.compile(rb'(?i)\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{30,}|ghp_[A-Za-z0-9]{36}|'
                     rb'github_pat_[A-Za-z0-9_]{40,}|Bearer [A-Za-z0-9._~-]{24,})\b')


def meta(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def archive(registry):
    frozen=verify()
    integrated=EXTERNAL/'integrated'
    trial=read(integrated/'TRIAL.json')
    qa=integrated/'stock_QA'
    product=read(qa/'worker/EOF.json')
    closed=read(qa/'STOCK_CLOSE.json')
    assert trial['passed'] is False and trial['error_type']=='ImportError' and "'SOURCE_REGION'" in trial['error']
    assert product['closed'] and product['observe_dispatches']==product['host_attempts']==product['new_rasters']==0
    assert closed['confirmed'] and closed['exit_code']==0 and not closed['forced_kill']
    assert set(x.name for x in integrated.iterdir())=={'stock_QA','QA','TRIAL.json'}
    assert list((integrated/'QA').iterdir())==[]
    sequence=[read(path)['method'] for path in sorted((qa/'wire').rglob('RECEIPT.json'))]
    assert sequence==['initialize','notifications/initialized','tools/list']
    cli=read(registry/'CLI_PROOF.json')
    assert cli['passed'] and cli['tool_count']==6 and cli['exact_all_tool_definitions']
    assert cli['threads_started']==cli['business_calls']==cli['provider_model_launches']==0
    assert cli['registry_response']['sha256']==meta((registry/'003/RX.bin').read_bytes())['sha256']
    catalogue=read(ORIGINAL_RUN/'slots/P2/owner/TOOLS_SCHEMA.json')
    registered,=read(registry/'003/RX.bin')['result']['data']
    fields=('name','description','inputSchema')
    actual=[{field:registered['tools'][row['name']][field] for field in fields} for row in catalogue]
    check=check_catalogue(catalogue, actual)
    compact=lambda value:len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
    evidence=NS/'evidence'
    save(evidence/'STARTUP_AND_REGISTRY_REVIEW.json',{
       'passed_integrated_qualification':False,'freeze_sha256':frozen,
       'integrated':{'attempts':1,'stock_A_started':1,'stock_A_tools_list':True,'stock_A_normal_exit':True,
                     'A_owner_started':False,'B_owner_started':False,'B_stock_started':0,'business_calls':0,
                     'error':trial['error'],'trace_dependency':{
                         'caller':'m4_dense_panel_sweep_formal_001/frame_device.py:9',
                         'required_imports':['SOURCE_REGION','load'],'source':'harness/bridge.py',
                         'observed_first_missing':'SOURCE_REGION','additional_unexported_static_name':'load'}},
       'registry_only':{'proved':True,'prototype_backend':'independent local replay behind the actual thin consumer',
             'uses_retained_Owner':False,'cli':cli['CLI'],'tools':cli['tool_count'],'condition_preserved_exactly':check,
             'additional_schema_UTF8_bytes':compact(actual)-compact(catalogue),'rule_UTF8_bytes':compact(REGION_TASK_RULE),
             'exact_registry_response':meta((registry/'003/RX.bin').read_bytes()),'app_server_RPC':cli['app_server_RPC'],
             'process_closure':read(registry/'PROCESS_CLOSE.json')},
       'empty_unvalidated_arms':['A explicit full through retained Owner','B rejection and next-request recovery through retained Owner',
          'same-name scope read_images through profiled Owner','profile outer attempt limit','integrated per-dispatch overhead'],
       'new_Blender_starts':0,'new_rasters':0,'new_model_starts':0,'extra_API_calls':0,'trial_replacements':0})
    for original,name in ((integrated/'TRIAL.json','TRIAL_FAILURE.json'),(qa/'STOCK_CLOSE.json','INTEGRATED_STOCK_CLOSE.json'),
                          (qa/'worker/EOF.json','INTEGRATED_STOCK_EOF.json'),(registry/'CLI_PROOF.json','CLI_REGISTRY_PROOF.json')):
        (evidence/name).write_bytes(original.read_bytes())

    folders={'integrated':integrated,'independent_cli_registry':registry,
             'direct_P2':EXTERNAL/'product_smoke_01','direct_P3':EXTERNAL/'product_smoke_P3',
             'direct_product_deadline':EXTERNAL/'product_expired_budget'}
    entries={}
    for prefix, root in folders.items():
        for path in sorted(root.rglob('*')):
            relative=path.relative_to(root)
            if not path.is_file() or 'cli_state' in relative.parts:
                continue
            data=path.read_bytes()
            assert not SECRETS.search(data) and not {'auth.json','.env','credentials.json'} & set(relative.parts), str(path)
            name=prefix+'/'+relative.as_posix()
            entries[name]=(path,meta(data))
    output=NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(output,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for name,(path,receipt) in entries.items():
            data=path.read_bytes()
            assert meta(data)==receipt,name
            bundle.writestr(name,data)
    with ZipFile(output) as bundle:
        assert set(bundle.namelist())==set(entries)
        assert all(meta(bundle.read(name))==row for name,(_,row) in entries.items())
    index={'freeze_sha256':frozen,'passed_integrated_qualification':False,'archive':{'name':output.name,**meta(output.read_bytes())},
           'member_count':len(entries),'members':{name:row for name,(_,row) in entries.items()}}
    save(NS/'RAW_INDEX.json',index)
    print('Archived source files',index['member_count'],index['archive'])


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('registry',type=Path)
    archive(parser.parse_args().registry.resolve(strict=True))
