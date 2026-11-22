"""Seal the successful assembly preflight and the one blocked formal recovery."""

from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

NS=Path(__file__).resolve().parent
sys.path[:0]=[str(NS/'harness'),str(NS)]
from common import EXTERNAL, PREVIOUS, read, save
from freeze import verify


SECRET=re.compile(rb'(?i)\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{30,}|ghp_[A-Za-z0-9]{36}|'
                  rb'github_pat_[A-Za-z0-9_]{40,}|Bearer [A-Za-z0-9._~-]{24,})\b')


def pin_bytes(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def pin(path):
    return {'path':str(path),**pin_bytes(path.read_bytes())}


def integrate_failure(root):
    report=read(root/'TRIAL.json')
    assert report['passed'] is False and report['error_type']=='ValueError'
    assert report['error']=='actual_CLI_MCP_owned_child_exit_unconfirmed/actual_CLI_MCP_live_owned_handle_unavailable'
    assert all(report[key]==0 for key in ('Blender_starts','new_rasters','model_starts','extra_API_calls'))
    status={}
    for label in ('QA','QB'):
        arm=root/label
        owner=read(arm/'OWNER_CLOSE.json')
        stock=root/f'stock_{label}'
        close,eof=read(stock/'STOCK_CLOSE.json'),read(stock/'worker/EOF.json')
        frames=read(arm/'BOUND_ORIGINALS.json')
        assert owner['confirmed'] and not owner['errors'] and not owner['transport_errors']
        assert close['confirmed'] and close['exit_code']==0 and not close['forced_kill']
        assert eof['closed'] and all(eof[key]==0 for key in ('observe_dispatches','host_attempts','new_rasters'))
        assert len(frames)==len({row['ref'] for row in frames})==3
        for frame in frames:
            copy=Path(frame['PNG'])
            assert copy.is_relative_to(arm.resolve()) and pin_bytes(copy.read_bytes())['sha256']==frame['PNG_sha256']
            assert copy.read_bytes()==Path(frame['source_path']).read_bytes()
        assert not list((arm/'owner').glob('tool_*')) and not (arm/'direct').exists()
        status[label]={'Owner_closed':owner,'stock_closed':close,'stock_EOF':eof,'registered_original_PNGs':len(frames),
                       'catalogue':pin(arm/'owner/TOOLS_SCHEMA.json'),'business':0}

    qa=root/'QA'
    registry=qa/'cli/actual_cli_registry'
    expected=read(qa/'owner/TOOLS_SCHEMA.json')
    clocks=read(registry/'PROCESS_CLOSE.json')
    assert clocks['exit_code']==0 and clocks['readers_joined'] and clocks['thin_watcher_joined'] and not clocks['killed_after_timeout']
    assert clocks['observed_thin_process']=={'error':'actual_CLI_MCP_live_owned_handle_unavailable'}
    assert '/0.152.1 ' in read(registry/'001/RX.bin')['result']['userAgent']
    registered,=read(registry/'003/RX.bin')['result']['data']
    assert registered['tools']=={tool['name']:tool for tool in expected}
    assert read(registry/'003/RX.bin')['result']['nextCursor'] is None
    thin,=(registry/'mcp_audit').glob('bridge_*')
    assert not (thin/'EXIT.json').exists() and not (root/'QB/cli').exists() and not (root/'stock_P2').exists()
    raw_thin=[]
    for folder in sorted(item for item in thin.iterdir() if item.is_dir()):
        req=read(folder/'TX.bin')
        receipt=read(folder/'RECEIPT.json')
        assert receipt['attempt'] is None and receipt['method']==req['method']
        item={'method':req['method'],'TX':pin(folder/'TX.bin')}
        if (folder/'RX.bin').is_file():
            matching,=(f for f in (qa/'owner').glob('rpc_*') if read(f/'TCP_TX.bin')['args']['message']==req)
            assert read(matching/'TCP_RX.bin')['result']==read(folder/'RX.bin')
            item['RX']=pin(folder/'RX.bin')
            item['owner_wire']={k:pin(matching/f'TCP_{k}.bin') for k in ('TX','RX')}
            item['thin_elapsed_to_stdout_ns']=receipt['flush_completed_ns']-receipt['received_ns']
        raw_thin.append(item)
    assert [row['method'] for row in raw_thin]==['initialize','notifications/initialized','tools/list']
    return {'status':report,'arms':status,'process_close':clocks,'original_QA_CLI_registry':pin(registry/'003/RX.bin'),
            'QA_original_catalogue_exact':True,'QA_CLI_thin':{'start':read(thin/'STARTED.json'),'wire':raw_thin,
            'normal_EOF_receipt':False,'owned_handle_and_exit_code_confirmed':False,
            'failure_observed':'OpenProcess returned null; Win32 error not recorded'},
            'attempted':['QA stock','QB stock','QA Owner','QB Owner','QA CLI registration'],
            'not_run':['QB CLI registration','both formal business paths','direct P2 official replay','closed success attestation']}


def preflight_review(root):
    proof=read(root/'PREFLIGHT.json')
    checker=run_path(str(PREVIOUS/'evidence_check.py'))
    p3=checker['archived_cases']()['P3']
    a,b=(read(root/arm/'direct/CALLS.json') for arm in ('QA','QB'))
    catalogues=[read(root/arm/'direct/TOOLS.json')['result']['tools'] for arm in ('QA','QB')]
    schema=checker['check_catalogue'](*catalogues)
    forms={'discover_full':a['discover_full']['response'],
           **{name:b[name]['response'] for name in ('discover_brief','discover_omitted')}}
    stable=checker['check_products']({'P3':forms},cases={'P3':p3})
    cases={}
    for arm,all_cases in (('QA',a),('QB',b)):
        worker=read(root/f'stock_{arm}/worker/EOF.json')
        rows={}
        for key,row in all_cases.items():
            rows[key]={k:row[k] for k in ('metrics','outer','product_dispatched')}
            if 'stock' in row:
                rows[key]['stock']=row['stock']
            if row['owner'] and 'client_profile' in row['owner']:
                rows[key]['guard']=row['owner']['client_profile']
        cases[arm]={'calls':rows,'worker_encoder_events':worker['encoder_events']}
    return {'passed':proof['passed'],'scope':'actual assembled Owner and product with business thin in preflight; no app-server here',
            'declared_scope_checks':schema,'stable_P3_original':stable,'calls':cases,
            'owner_budget':proof['owner_budget']}


def archive():
    frozen=verify()
    sources={'preflight':EXTERNAL/'preflight','integrated':EXTERNAL/'integrated'}
    intended=integrate_failure(sources['integrated'])
    preflight=preflight_review(sources['preflight'])
    evidence=NS/'evidence'
    save(evidence/'FORMAL_FAILURE_REVIEW.json',{'freeze_sha256':frozen,'passed':False,**intended})
    save(evidence/'PREFLIGHT_WIRE_REVIEW.json',preflight)
    for source,name in ((sources['preflight']/'PREFLIGHT.json','PREFLIGHT.json'),
        (sources['integrated']/'TRIAL.json','TRIAL_FAILURE.json'),
        (sources['integrated']/'QA/cli/actual_cli_registry/PROCESS_CLOSE.json','QA_CLI_PROCESS_CLOSE.json')):
        (evidence/name).write_bytes(source.read_bytes())
    entries={}
    for prefix,root in sources.items():
        for path in sorted(root.rglob('*')):
            relative=path.relative_to(root)
            if not path.is_file() or 'cli_state' in relative.parts:
                continue
            data=path.read_bytes()
            assert not SECRET.search(data) and not {'auth.json','.env','credentials.json'} & set(relative.parts),str(path)
            entries[prefix+'/'+relative.as_posix()]=(path,pin_bytes(data))
    output=NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(output,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for name,(path,receipt) in entries.items():
            data=path.read_bytes()
            assert pin_bytes(data)==receipt,name
            bundle.writestr(name,data)
    with ZipFile(output) as bundle:
        assert set(bundle.namelist())==set(entries)
        assert all(pin_bytes(bundle.read(name))==row for name,(_,row) in entries.items())
    index={'freeze_sha256':frozen,'qualification_attempts':1,'passed':False,'formal_business':0,'replacements':0,
           'archive':{'name':output.name,**pin_bytes(output.read_bytes())},'member_count':len(entries),
           'members':{name:row for name,(_,row) in entries.items()}}
    save(NS/'RAW_INDEX.json',index)
    print('Sealed',index['member_count'],index['archive'],flush=True)


if __name__=='__main__':
    archive()
