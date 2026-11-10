"""Read-only binding and semantic checks of the no-model preflight artifacts."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'native_plugin_complex_003';DIAG=HERE.parent/'scale_diag_001'
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=read(HERE/'PREFLIGHT.json');assert p['passed'] and p['model_calls']==0 and len(p['cells'])==6
    oracle=next(s for s in read(DIAG/'ORACLE.json')['snapshots'] if s['id']=='D48')['global_nearest_unsigned']
    source=read(HERE/'SOURCE_PREFLIGHT.json');common=None;ordinary=None;rows=[];physical=0
    for cell in p['cells']:
        folder=Path(cell['folder']);public=read(folder/'PUBLIC_TOOLS.json')['result']['tools'];native=public[0]
        if common is None:common=native
        assert native==common and native['name']=='execute_blender_code'
        assert [t['name'] for t in public]==(['execute_blender_code'] if cell['group']=='N' else ['execute_blender_code','human_eye_scene_observe'])
        initial=read(folder/'owner/INITIAL.json');final=read(folder/'owner/FINAL.json');assert initial==final
        closed=read(folder/'owner/CLOSE.json');assert closed['confirmed'] and closed['asset_unchanged']
        tools=read(folder/'owner/TOOLS.json');assert len(tools['tools'])==cell['tool_attempts'] and tools['tools'][0]['is_error'] and not tools['tools'][1]['is_error']
        events=[json.loads(line) for line in (folder/'owner/native/WORKER_EVENTS.jsonl').read_text().splitlines()];physical+=len(events)
        row={'task':cell['task'],'group':cell['group'],'geometry_unchanged':True,'normal_close':True,'failed_attempt_retained':True,
             'worker_events':len(events),'model_calls':0,'source_manifest_sha256':sha(HERE/'SOURCE_PREFLIGHT.json')}
        if cell['group']!='N':
            if ordinary is None:ordinary=public[1]
            assert public[1]==ordinary
            reply=read(folder/'REPLIES.json')[-1];payload=json.loads(reply['result']['content'][0]['text'])
            assert payload['binding']['runtime_source_sha256']==source['versions'][cell['group']]['source_sha256']
            if cell['task']=='assembly':
                assert len(payload['pairs'])==3 and payload['status']=='observed'
                expected=[('separated',.01,2.0446606626675212e-7),('penetrating',0.,0.),('separated',.04,3.0142333402758355e-7)]
                for actual,(relation,distance,error) in zip(payload['pairs'],expected):
                    assert actual['facts']['closed_solid_relation']['value']==relation
                    d=actual['facts']['surface_proximity']['value']['distance_m'];assert abs(d-distance)+error<=1e-6
                row['geometry_answers_qualified']=True
            else:
                assert payload['status']=='complete' and [o['name'] for o in payload['nearest_objects']]==['Peer_000']
                assert payload['coverage']=={'targets_excluding_focal':47,'distance_valid':47,'strictly_excluded':0,'unresolved':0}
                d=payload['distance_m'];assert max(abs(d-oracle['distance_lower_m']),abs(d-oracle['distance_upper_m']))<=1e-6
                row['geometry_answers_qualified']=True
            row['plugin_close']=closed['plugin_close'];assert row['plugin_close']['confirmed']
        rows.append(row)
    assert read(HERE/'WRAPPER_TESTS.json')['passed']
    value={'passed':True,'scope':'no-model preflight only, not consumer acceptance','model_calls':0,'cells':rows,
       'common_native_equal_all_6':True,'ordinary_read_schema_equal_all_plugin_cells':True,'physical_worker_events':physical,
       'wrapper_tests_sha256':sha(HERE/'WRAPPER_TESTS.json'),'source_only_change':'accepted _bounded +4 lines; no product modification by this batch'}
    (HERE/'PREFLIGHT_REVIEW.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'cells':6,'geometry_queries_checked':4,'model_calls':0,'worker_events':physical}))
if __name__=='__main__':main()
