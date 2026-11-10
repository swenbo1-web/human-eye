"""Synthetic transcript checks for the 005 cost adapter; no trial reads."""
from pathlib import Path
from collections import Counter
import importlib.util
import json
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('complex005_cost_adapter', HERE/'analyze.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False)+'\n', encoding='utf8', newline='\n')


def reply(request, payload, error=False):
    return {'jsonrpc':'2.0','id':request['id'],
        'result':{'content':[{'type':'text','text':json.dumps(payload)}],'isError':error}}


def schemas(group):
    return [{'name':'human_eye_scene_observe','inputSchema':{'type':'object','properties':{
        'query':{'type':'object','properties':{'mode':{'enum':
            ['overview','exact_pairs','top1'] if group=='H' else ['task','surface_nearest']}}}}}},
        {'name':'human_eye_connection_status','inputSchema':{'type':'object','additionalProperties':False}}]


def public_catalogue(root, group):
    folder=root/group; bridge=folder/'attachments/bridge_fake'
    save(bridge/'STARTED.json', {'pid':42})
    request={'jsonrpc':'2.0','id':1,'method':'tools/list'}
    tools=[{'name':'execute_blender_code'}]+([] if group=='N' else schemas(group))
    response={'jsonrpc':'2.0','id':1,'result':{'tools':tools}}
    call=bridge/'001';call.mkdir()
    tx=m.public_wire(request);rx=m.public_wire(response)
    (call/'TX.bin').write_bytes(tx);(call/'RX.bin').write_bytes(rx)
    save(bridge/'EXIT.json', {'normal_exit':True,'complete_tx_bytes':len(tx),'complete_rx_bytes':len(rx)})
    return folder


def catalogues(root):
    evidence=m.Evidence(root)
    for group in ('N','H','C'):
        folder=public_catalogue(root,group);issues=[]
        reads=[] if group=='N' else schemas(group)
        result,_,_=m.bridge_metrics(evidence,folder,group,reads,issues)
        assert not issues and result['catalogues'][0]['valid']
    issues=[]
    result,_,_=m.bridge_metrics(evidence,root/'H','H',schemas('C'),issues)
    assert not result['catalogues'][0]['valid']
    assert any(x['code']=='public_release_read_schema_changed' for x in issues)
    issues=[]
    result,_,_=m.bridge_metrics(evidence,root/'H','H',schemas('H')[:1],issues)
    assert not result['catalogues'][0]['valid']
    assert any(x['code']=='unexpected_public_catalogue' for x in issues)
    # A missing EXIT receipt remains a limitation, not fabricated normal EOF.
    (root/'H/attachments/bridge_fake/EXIT.json').unlink()
    issues=[]
    result,_,_=m.bridge_metrics(evidence,root/'H','H',schemas('H'),issues)
    assert result['missing_graceful_exit_receipts']==1 and not result['graceful_client_exit_attested']
    assert result['counts'].get('missing_response_frames',0)==0
    assert [x['code'] for x in issues]==['missing_bridge_exit']


def status_ledger(root):
    owner=root/'owner';attempts=[];total=0
    names=['human_eye_scene_observe','human_eye_connection_status','execute_blender_code']
    for i,name in enumerate(names,1):
        arguments={'code':'print(1)'} if name=='execute_blender_code' else ({'include_image':False} if i==1 else {})
        request={'jsonrpc':'2.0','id':'reused-id','method':'tools/call','params':{'name':name,'arguments':arguments}}
        response=reply(request, {'status':'unknown' if i==1 else 'ready','host_connectivity_checked':False}, i==1)
        raw=m.public_wire(response);total+=len(raw)
        attempt=dict(attempt=i,name=name,started_ns=100*i,elapsed_ns=i,response_bytes=len(raw),
            produced_response_bytes=len(raw),exception=None,is_error=i==1)
        folder=owner/('tool_%02d'%i)
        save(folder/'REQUEST.json',request);save(folder/'ATTEMPT.json',attempt);save(folder/'RESPONSE.json',response)
        attempts.append(attempt)
    save(owner/'TOOLS.json',dict(attempts=3,calls=3,wire_tool_bytes=total,tools=attempts))
    issues=[];metric,requests,responses=m.owner_tools(m.Evidence(root),owner,issues)
    assert not issues and metric['ledger_complete'] and metric['response_wire_bytes_verified']
    assert metric['attempts']==3 and metric['native_attempts']==1 and metric['plugin_attempts']==1
    assert metric['scene_observe_attempts']==1 and metric['connection_status_attempts']==1
    assert metric['all_plugin_read_attempts']==2 and metric['tool_time_ns']==6
    assert metric['sum_recorded_response_bytes']==total and sum(requests.values())==sum(responses.values())==3
    # Status between a failed observation and Native is not labelled as a
    # direct geometric fallback or a successful engine calculation.
    assert metric['native_after_plugin_error_count']==0


def peer_status(root, group):
    owner=root/group;peer=owner/'plugin';peer.mkdir(parents=True)
    status={'jsonrpc':'2.0','id':'private-status','method':'tools/call',
        'params':{'name':'human_eye_connection_status','arguments':{}}}
    for i,start in [(1,100),(2,120)]:
        folder=owner/('tool_%02d'%i)
        save(folder/'REQUEST.json',status)
        save(folder/'ATTEMPT.json',{'attempt':i,'name':'human_eye_connection_status','started_ns':start,'elapsed_ns':10})
    catalogue=schemas(group)+[{'name':'human_eye_transform'},{'name':'human_eye_clearance_segment'}]
    if group=='C':catalogue.append({'name':'human_eye_arm_twist_diagnose'})
    init={'jsonrpc':'2.0','id':'private-init','method':'initialize'}
    initialized={'jsonrpc':'2.0','id':'private-init','result':{'_meta':{'human_eye':{'source_file_count':125 if group=='H' else 137}}}}
    listed={'jsonrpc':'2.0','id':'private-list','method':'tools/list'}
    list_answer={'jsonrpc':'2.0','id':'private-list','result':{'tools':catalogue}}
    notify={'jsonrpc':'2.0','method':'notifications/initialized'}
    frames=[(init,initialized,1),(notify,None,2),(listed,list_answer,3),
        (status,reply(status,{'status':'ready','host_connectivity_checked':False}),4),
        (status,reply(status,{'status':'ready','host_connectivity_checked':False}),103),
        (status,reply(status,{'status':'ready','host_connectivity_checked':False}),123)]
    records=[];tx_total=rx_total=0
    for i,(request,response,start) in enumerate(frames,1):
        folder=peer/str(i).zfill(3);folder.mkdir()
        tx=m.public_wire(request);(folder/'TX.bin').write_bytes(tx);tx_total+=len(tx)
        rx=b'' if response is None else m.public_wire(response)
        if response is not None:(folder/'RX.bin').write_bytes(rx)
        rx_total+=len(rx)
        receipt=dict(request_id=request.get('id'),method=request['method'],started_ns=start,elapsed_ns=1,
            sent_bytes=len(tx),attempted_send_bytes=len(tx),send_confirmed=True,received_bytes=len(rx),error=None)
        save(folder/'RECEIPT.json',receipt);records.append(receipt)
    save(peer/'START.json',{'started_ns':0,'launcher_pid':1,'command':['fake-only']})
    save(peer/'RPC.json',{'requests':records,'tx_bytes':tx_total,'rx_bytes':rx_total,'poisoned':False})
    save(owner/'PLUGIN_INITIALIZE.json',initialized);save(owner/'PLUGIN_TOOLS.json',list_answer)
    issues=[];metrics=m.peer_metrics(m.Evidence(root),owner,issues)
    assert not issues,issues
    assert metrics['counts']['private_admin_requests']==4 and metrics['counts']['forwarded_status_requests']==2
    assert metrics['counts'].get('forwarded_query_requests',0)==0
    assert [x['owner_attempt'] for x in metrics['forwarded_read_correlations']]==[1,2]
    assert metrics['actual_ordinary_tools']==catalogue and len(catalogue)==(4 if group=='H' else 5)
    assert metrics['saved_catalogue_equals_wire'] and metrics['saved_initialize_equals_wire']
    assert metrics['tx_bytes']==tx_total and metrics['rx_bytes']==rx_total
    # Identical request/ID at an unrelated time cannot be used as evidence of
    # an owner-forwarded call, including when it says private-status.
    receipt=json.loads((peer/'006/RECEIPT.json').read_bytes());receipt['started_ns']=200
    save(peer/'006/RECEIPT.json',receipt);records[-1]=receipt
    save(peer/'RPC.json',{'requests':records,'tx_bytes':tx_total,'rx_bytes':rx_total,'poisoned':False})
    issues=[];m.peer_metrics(m.Evidence(root),owner,issues)
    assert any(x['code']=='internal_product_read_not_bound_to_owner_attempt' for x in issues)


def source_counts(root):
    versions={}
    for group,count in [('H',125),('C',137)]:
        site=root/group;site.mkdir(parents=True);members=[]
        for number in range(count):
            path=site/('source_%03d.py'%number);path.write_bytes(('# synthetic %s %d\n'%(group,number)).encode())
            members.append({'path':path.name,'sha256':m.digest(path.read_bytes())})
        identity={'base_version':'9.7.2','implementation_revision':'synthetic_'+group,'source_files':members,
            'source_kind':'installed_distribution','mode':'live','capabilities':{'old_scope':group=='H'}}
        body={'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':members}
        sha=m.digest(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        identity.update(source_sha256=sha,build_id='sha256:'+sha)
        versions[group]={'identity':identity,'runtime_sources':members,'installed_root':str(site),
            'source_sha256':sha,'entry':'synthetic_entry_'+group,'source_count':count}
    source={'versions':versions};issues=[];e=m.Evidence(root)
    replays=m.replay_source_manifests(e,source,issues);assert not issues
    for group,count in [('H',125),('C',137)]:
        want=versions[group];actual={k:v for k,v in want['identity'].items() if k!='source_files'}
        actual.update(source_file_count=count,production_mode=True,identity_check={
            'compatible':True,'pins_requested':True,'reasons':[],'expected':{'source_sha256':want['source_sha256']}})
        config={'source_sha256':want['source_sha256'],'entry':want['entry'],'install_root':want['installed_root']}
        assert m.source_binding({'runtime_identity':actual},config,group,source,replays[group])
        actual['source_file_count']=137 if group=='H' else 125
        assert m.source_binding({'runtime_identity':actual},config,group,source,replays[group]) is False
    (root/'H/source_000.py').write_bytes(b'changed synthetic source\n')
    issues=[];replays=m.replay_source_manifests(e,source,issues)
    assert replays['H']['passed'] is False and replays['C']['passed'] is True


def main():
    base=m.self_test()
    with tempfile.TemporaryDirectory(prefix='complex005-cost-fake-') as temporary:
        root=Path(temporary)
        catalogues(root/'catalogues');status_ledger(root/'ledger')
        peer_status(root/'peers','H');peer_status(root/'peers','C');source_counts(root/'sources')
    print(json.dumps({'passed':True,'scope':'synthetic inputs only, no formal or preflight trial reads',
        'adapter_sha256':m.digest((HERE/'analyze.py').read_bytes()),
        'test_script_sha256':m.digest(Path(__file__).read_bytes()),'reused_v2_fake_suite':base,
        'checks':['N1_H3_C3_catalogues','original_group_schemas_not_interchanged','missing_EXIT_remains_unattested',
            'status_attempt_bytes_and_time_counted','status_not_geometric_solve_or_direct_fallback',
            'private_status_vs_two_identical_public_requests','duplicate_ID_multiset_and_owner_interval_binding',
            'H4_C5_internal_catalogues_retained','H125_C137_identity_bindings','wrong_count_and_changed_source_rejected'],
        'model_calls':0,'service_starts':0,'Blender_runs':0,'formal_records_read':0}))


if __name__=='__main__':main()
