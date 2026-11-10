"""Recorded source/geometry/lifecycle and raw metrics; no new test execution."""
import hashlib,json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def summary(values):
    values=[v for v in values if v is not None]
    return {'n':len(values),'median':statistics.median(values) if values else None,
            'min':min(values) if values else None,'max':max(values) if values else None,'sum':sum(values)}
def main():
    plan=read(HERE/'PLAN.json');expected=read(HERE/'private/author_mesh_snapshots.json')['initial'];rows=[];inputs={}
    for slot in plan['sequence']:
        folder=HERE/'cells'/slot['cell'];consumer=read(folder/'CONSUMER.json') if (folder/'CONSUMER.json').exists() else {}
        row=dict(slot,completed=consumer.get('valid_completion',False),geometry_verified=False)
        if consumer:
            owner=read(folder/'owner/CLOSE.json');initial=read(folder/'owner/INITIAL.json');final=read(folder/'owner/FINAL.json')
            fields=('name','vertices_local','matrix_world','faces')
            assert [{k:o[k] for k in fields} for o in initial['objects']]==[{k:o[k] for k in fields} for o in expected['objects']]
            assert initial==final and owner['confirmed'] and owner['native_close']['exit_code']==0
            assert owner['worker_closed']['initial_geometry_fingerprint']==owner['worker_closed']['final_geometry_fingerprint']
            tools=read(folder/'owner/TOOLS.json');identity=read(folder/'owner/IDENTITY.json')
            scripts=[];tool_text=0
            for f in sorted((folder/'owner').glob('tool_*/REQUEST.json')):
                request=read(f);response=read(f.with_name('RESPONSE.json'))
                tool_text+=sum(len(c.get('text','').encode()) for c in response['result'].get('content',[]) if c.get('type')=='text')
                if request['params']['name']=='execute_blender_code':scripts.append(request['params']['arguments']['code'])
            # Original code remains in the evidence; this list is an audit aid,
            # not a claim to statically sandbox arbitrary Python.
            suspicious=[{'script':i,'pattern':s} for i,code in enumerate(scripts) for s in
                ('open(','read_text(','read_bytes(','load_mainfile','save_as_mainfile','bpy.ops.','os.','subprocess','human_eye','TRUTH','private/') if s in code]
            actual_wire=0;catalog=0
            for f in (folder/'attachments').glob('bridge_*/*/RX.bin'):
                raw=f.read_bytes();actual_wire+=len(raw)
                tx=read(f.with_name('TX.bin'))
                if tx['method']=='tools/list':catalog+=len(raw)
            worker_events=[json.loads(s) for s in (folder/'owner/native/WORKER_EVENTS.jsonl').read_text().splitlines()]
            assert all(e.get('terminal_geometry_and_file_checks_passed') for e in worker_events)
            public_events=[json.loads(s)['event'] for s in (folder/'events.jsonl').read_text().splitlines()]
            usage=[e['usage'] for e in public_events if e.get('type')=='turn.completed']
            row.update(geometry_verified=True,lifecycle_confirmed=True,usage_complete=usage[-1] if usage else None,
                prompt_to_final_ns=consumer.get('prompt_to_final_ns'),cli_wall_ns=consumer['wall_ns'],
                total_task_wall_ns=consumer['total_task_wall_ns'],setup_ns=consumer['pre_consumer_setup_ns'],
                owner_finish_ns=consumer['owner_finish']['finish_elapsed_ns'],
                actor_setup_ns=identity['startup_ns'],close_ns=owner['ended_ns']-owner['started_ns'],
                native_calls=sum(t['name']=='execute_blender_code' for t in tools['tools']),
                plugin_calls=sum(t['name']=='human_eye_spatial_relations' for t in tools['tools']),
                tool_calls=tools['calls'],tool_error_count=sum(t['is_error'] for t in tools['tools']),
                tool_time_ns=sum(t['elapsed_ns'] for t in tools['tools']),
                physical_execute_rpcs=len(worker_events),administrative_snapshots=2,close_rpc=1,
                public_tool_text_bytes=tool_text,public_tool_wire_bytes=tools['wire_tool_bytes'],
                catalog_wire_bytes=catalog,all_stdio_wire_bytes=actual_wire,public_image_bytes=0,
                input_prompt_bytes=consumer['input_text_bytes'],final_text_bytes=consumer['output_text_bytes'],
                source_identity=identity['runtime_identity'],script_audit_flags=suspicious,
                final=consumer['final'],provider_retry_observations=consumer['provider_retry_observations'])
        rows.append(row)
        for f in folder.rglob('*'):
            if f.is_file():inputs[str(f.relative_to(HERE))]=sha(f)
    groups={}
    for group in ('N','A','B'):
        selected=[r for r in rows if r['group']==group]
        groups[group]={key:summary([r.get(key) for r in selected]) for key in ('prompt_to_final_ns','total_task_wall_ns',
            'cli_wall_ns','setup_ns','owner_finish_ns','tool_calls','native_calls','plugin_calls','tool_time_ns',
            'physical_execute_rpcs','public_tool_text_bytes','catalog_wire_bytes','all_stdio_wire_bytes')}
        keys=set().union(*(set((r.get('usage_complete') or {})) for r in selected))
        groups[group]['usage']={k:sum(r['usage_complete'][k] for r in selected if r.get('usage_complete') and k in r['usage_complete']) for k in keys}
    ratios=[]
    for round_id in (1,2,3):
        selected={r['group']:r for r in rows if r['round']==round_id};n=selected['N']
        ratios.append({'round':round_id,**{g+'_over_N':selected[g]['total_task_wall_ns']/n['total_task_wall_ns'] for g in ('A','B')}})
    result={'cycle_id':plan['cycle_id'],'denominator':9,'completed':sum(r['completed'] for r in rows),
        'geometry_verified':sum(r['geometry_verified'] for r in rows),'rows':rows,'groups':groups,'round_ratios':ratios,
        'quality_status':'independent de-labelled semantic review separate; no quality inferred from exit0',
        'provider_request_count':None,'dollar_cost':None,'resolved_effort':None,
        'script_sha256':sha(Path(__file__)),'inputs_sha256':inputs,
        'new_model_calls':0,'new_Blender_runs':0,'new_product_calls':0}
    (HERE/'METRICS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'completed':result['completed'],'geometry_verified':result['geometry_verified'],'groups':groups,'round_ratios':ratios}))
if __name__=='__main__':main()
