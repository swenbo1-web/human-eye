"""Independent, standard-library-only cost/record audit; never imports author code."""
from __future__ import annotations
import ast
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile
import io

AUTHOR = Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_003')
OUT = Path(r'D:/hefe/verification/fixes/20261113_m4_active_coverage_003_review/cost')
COMMIT = 'f2b9dc01621d5b7adb330c096b6460eb3be9c552'
INPUTS = {}
CHECKS = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    p = Path(path).resolve()
    b = p.read_bytes()
    entry = {'path': str(p), 'bytes': len(b), 'sha256': sha(b)}
    if str(p) in INPUTS and INPUTS[str(p)] != entry:
        raise RuntimeError('input changed during audit: ' + str(p))
    INPUTS[str(p)] = entry
    return b

def js(path):
    return json.loads(read(path).decode('utf-8'))

def check(name, actual, expected=True):
    ok = actual == expected
    CHECKS.append({'name': name, 'passed': ok, 'actual': actual, 'expected': expected})
    return ok

def frac(value):
    v = Fraction(value)
    return {'numerator': v.numerator, 'denominator': v.denominator, 'decimal': float(v)}

def median(xs):
    a = sorted(Fraction(x) for x in xs)
    n = len(a)
    return a[n // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2

def same_path(a, b):
    return Path(a).resolve() == Path(b).resolve()

def interval(name, d, lo, hi):
    check(name + '.integer_bounds', all(type(d[k]) is int for k in ['started_ns','closed_ns','elapsed_ns']))
    check(name + '.difference', d['closed_ns'] - d['started_ns'], d['elapsed_ns'])
    check(name + '.contained', lo <= d['started_ns'] <= d['closed_ns'] <= hi)

def trace(path, pid, lo, hi, arm=None, scenario=None):
    b = read(path)
    rows = [json.loads(line) for line in b.splitlines()]
    label = str(Path(path).relative_to(AUTHOR))
    check(label + '.sequences', [x['sequence'] for x in rows], list(range(1,len(rows)+1)))
    check(label + '.pid', {x['process_id'] for x in rows} == {pid})
    stamps = [x['monotonic_ns'] for x in rows]
    check(label + '.ordered', stamps == sorted(stamps))
    check(label + '.contained', lo <= min(stamps) <= max(stamps) <= hi)
    if arm is not None: check(label+'.arm', all(x['arm']==arm for x in rows))
    if scenario is not None: check(label+'.scenario', all(x['scenario']==scenario for x in rows))
    return rows

def array_payload(blob, label, record):
    check(label + '.magic', blob[:6].hex(), b'\x93NUMPY'.hex())
    major, minor = blob[6:8]
    length_size = 2 if major == 1 else 4
    n = int.from_bytes(blob[8:8+length_size], 'little')
    header = ast.literal_eval(blob[8+length_size:8+length_size+n].decode('latin1'))
    payload = blob[8+length_size+n:]
    itemsize = int(header['descr'][2:])
    check(label + '.shape', list(header['shape']), record['shape'])
    check(label + '.dtype', header['descr'], record['dtype_str'])
    check(label + '.c_order', header['fortran_order'], False)
    check(label + '.size_from_shape', len(payload), math.prod(header['shape']) * itemsize)
    check(label + '.nbytes', len(payload), record['nbytes'])
    check(label + '.raw_sha', sha(payload), record['sha256'])
    return len(payload), sha(payload)

def main():
    prereg = js(AUTHOR/'PREREGISTRATION.json')
    results = js(AUTHOR/'RESULTS.json')
    progress = js(AUTHOR/'PROGRESS.json')
    reservation = js(AUTHOR/'BATCH_STARTED.json')
    read(AUTHOR/'runner.py')  # manual timing-boundary inspection only, never executed/imported
    read(AUTHOR/'PREPARATION.json')
    check('main_denominator', len(prereg['main']), 12)
    check('control_denominator', len(prereg['control']), 2)
    check('main_order', [{k:r[k] for k in ['id','pair','arm','scenario']} for r in results['rows']], prereg['main'])
    check('control_order', [{k:r[k] for k in ['id','pair','arm','scenario']} for r in results['controls']], prereg['control'])
    check('main_statuses', dict(Counter(r['status'] for r in results['rows'])), {'completed':12})
    check('control_statuses', dict(Counter(r['status'] for r in results['controls'])), {'completed':2})
    check('progress_rows', progress['rows'], results['rows'])
    check('progress_controls', progress['controls'], results['controls'])
    check('no_stop', results['stop'], None)
    check('reservation_digest', reservation['freeze_sha256'], results['freeze_sha256'])
    check('run_directory_set', sorted(p.name for p in (AUTHOR/'runs').iterdir() if p.is_dir()), sorted(r['id'] for r in results['rows']+results['controls']))
    bstart, bclose = results['batch_started_ns'], results['batch_closed_before_publication_ns']
    check('whole_batch_difference', bclose-bstart, results['whole_batch_through_analysis_ns'])
    interval('common_setup', results['common_parent_setup'], bstart,bclose)
    last_close = results['common_parent_setup']['closed_ns']
    run_costs = []
    raw_runs = {}
    stages_by_arm = defaultdict(lambda: defaultdict(int))
    for row in results['rows']+results['controls']:
        rid = row['id']; folder = AUTHOR/'runs'/rid
        raw = js(folder/'RESULT.json'); raw_runs[rid] = raw
        publication = js(folder/'RESULT_PUBLICATION.json')
        facts = row['facts']
        pid = row['process_id']
        lo, hi = row['started_ns'], row['closed_ns']
        check(rid+'.strict_sequential', last_close <= lo)
        last_close = hi
        check(rid+'.full_window', hi-lo, row['elapsed_ns'])
        check(rid+'.inside_batch', bstart <= lo <= hi <= bclose)
        check(rid+'.process_pid', raw['process_id'], pid)
        check(rid+'.launch_pid', raw['launch_environment']['process_id'], pid)
        check(rid+'.facts_environment', facts['launch_environment'], raw['launch_environment'])
        check(rid+'.output_directory', same_path(row['output_directory'],folder) and same_path(raw['output_directory'],folder))
        check(rid+'.arm_scenario', [raw['arm'],raw['scenario']], [row['arm'],row['scenario']])
        check(rid+'.completed_no_exceptions', [raw['status'],raw['exceptions'],row['returncode']], ['completed',[],0])
        env = raw['launch_environment']
        check(rid+'.direct_executable', same_path(row['command'][0],env['python_executable']) and same_path(row['command'][0],prereg['direct_launch']['base_executable']))
        check(rid+'.base_exe_digest', env['base_executable_sha256'], prereg['direct_launch']['base_executable_sha256'])
        check(rid+'.base_exe', same_path(env['base_executable'],env['python_executable']))
        check(rid+'.child_source_command', same_path(row['command'][5], AUTHOR/'bootstrap.py') and same_path(row['command'][6],AUTHOR/'runtime.py'))
        for source,digest in raw['inputs_sha256'].items():
            check(rid+'.source.'+Path(source).name,sha(read(source)),digest)
        check(rid+'.scene_source',sha(read(raw['source_scene'])),raw['source_scene_sha256'])
        check(rid+'.camera_source',sha(read(raw['source_camera'])),raw['source_camera_sha256'])
        expected_camera = 'CAMERAS.json' if row['scenario']=='main' else 'CAMERAS_PIXEL_SHORTFALL.json'
        check(rid+'.camera_selection',same_path(raw['source_camera'],AUTHOR/'inputs'/expected_camera))
        check(rid+'.no_old_evidence',raw['audit']['forbidden_old_evidence_reads'],0)
        check(rid+'.no_old_writes',raw['audit']['forbidden_old_writes'],0)
        check(rid+'.no_external_new_calls',raw['metrics']['new_model_provider_Blender_API_runs'],0)
        check(rid+'.runtime_window',lo<=raw['started_ns']<=raw['work_closed_ns']<=row['process_exited_ns']<=row['cleanup_exited_ns']<=hi)
        check(rid+'.runtime_elapsed',raw['work_closed_ns']-raw['started_ns'],raw['elapsed_before_result_publication_ns'])
        cleanup=row['cleanup']; interval(rid+'.cleanup',cleanup,row['process_exited_ns'],row['cleanup_exited_ns'])
        check(rid+'.cleanup_pid',cleanup['pid'],pid)
        check(rid+'.cleanup_complete',[cleanup['confirmed'],cleanup['reaped'],cleanup['process_handle_closed'],all(cleanup['pipes_closed'].values()),cleanup['errors'],cleanup['kill_requested']],[True,True,True,True,[],False])
        interval(rid+'.result_publication',publication,raw['work_closed_ns'],row['process_exited_ns'])
        rb=read(folder/'RESULT.json')
        check(rid+'.published_result_bytes',publication['RESULT_bytes'],len(rb))
        check(rid+'.published_result_digest',publication['RESULT_sha256'],sha(rb))
        events=trace(folder/'TRACE.jsonl',pid,raw['started_ns'],row['process_exited_ns'],row['arm'],row['scenario'])
        evcounts=Counter(x['event'] for x in events)
        check(rid+'.work_completion_count',evcounts['work_complete'],1)
        check(rid+'.process_completion_count',evcounts['process_complete'],1)
        check(rid+'.trace_result_digest',events[-1]['RESULT_sha256'],sha(rb))
        check(rid+'.trace_last_event',events[-1]['event'],'process_complete')
        raw_trace=read(folder/'TRACE.jsonl')
        check(rid+'.prepublication_trace_prefix',len(raw_trace.splitlines(keepends=True)[-1])+raw['trace_bytes_before_result_publication'],len(raw_trace))
        sc={x['stage']:x for x in events if x['event']=='stage_complete'}
        check(rid+'.trace_stage_names',sorted(sc),sorted(set(raw['stages'])-{'stdlib_import'}))
        timeline=[]
        for name,s in raw['stages'].items():
            interval(rid+'.stage.'+name,s,raw['started_ns'],raw['work_closed_ns'])
            if name != 'stdlib_import':check(rid+'.stage_trace.'+name,{k:sc[name][k] for k in ['started_ns','closed_ns','elapsed_ns']},s)
            timeline.append((s['started_ns'],s['closed_ns'],name))
            if row['scenario']=='main':stages_by_arm[row['arm']][name.split('.',1)[-1]]+=s['elapsed_ns']
        timeline.sort()
        check(rid+'.nonoverlapping_child_stages',all(a[1]<=b[0] for a,b in zip(timeline,timeline[1:])))
        check(rid+'.facts_stages',facts['stage_timings'],raw['stages'])
        attempts=[e for e in events if e['event']=='render_attempt']
        completed=[e for e in events if e['event']=='render_complete']
        frame_completed=[e for e in events if e['event']=='frame_complete']
        check(rid+'.attempt_ids',[e['attempt_id'] for e in attempts],list(range(1,len(attempts)+1)))
        n=len(attempts)
        check(rid+'.render_record_counts',[len(completed),len(frame_completed),len(raw['frames']),len(raw['render_attempts']),row['render_attempts'],raw['metrics']['raster_attempts'],raw['metrics']['raster_completed'],facts['render_attempts'],facts['render_completed']],[n]*9)
        views=[f['view_name'] for f in raw['frames']]
        expectedviews=['SCENE','TOP','LEFT','RIGHT','FRONT','BACK'] if row['arm']=='A' else (['SCENE','BACK'] if row['scenario']=='main' else ['SCENE','BACK','LEFT','TOP'])
        check(rid+'.views',views,expectedviews)
        check(rid+'.facts_views',facts['views'],views)
        png_bytes=npz_bytes=payload_bytes=metadata_bytes=0
        pixel_rows=0
        raw_hashes={}
        for i,f in enumerate(raw['frames'],1):
            label=rid+'.frame'+str(i)
            for key in ['PNG','owner_depth_RGB_arrays','metadata_path']:
                check(label+'.local_'+key,Path(f[key]).resolve().is_relative_to(folder.resolve()))
            png=read(f['PNG']); npz=read(f['owner_depth_RGB_arrays']); meta=read(f['metadata_path'])
            png_bytes+=len(png);npz_bytes+=len(npz);metadata_bytes+=len(meta)
            check(label+'.png_bytes',len(png),f['PNG_bytes']);check(label+'.png_sha',sha(png),f['PNG_sha256'])
            check(label+'.png_magic',png[:8].hex(),b'\x89PNG\r\n\x1a\n'.hex())
            check(label+'.png_dimensions',list(struct.unpack('>II',png[16:24])),f['pose']['size_px'])
            check(label+'.npz_bytes',len(npz),f['compressed_array_file_bytes']);check(label+'.npz_sha',sha(npz),f['arrays_sha256'])
            check(label+'.metadata_bytes',len(meta),f['metadata_bytes']);check(label+'.metadata_sha',sha(meta),f['metadata_sha256'])
            m=json.loads(meta)
            for key in m:
                if key in ['metadata_stage_scope','stages']:continue
                check(label+'.metadata_record.'+key,m[key],f[key])
            frame_payload=0
            raw_hashes[f['view_name']]={}
            with zipfile.ZipFile(io.BytesIO(npz)) as z:
                check(label+'.array_members',sorted(z.namelist()),['color.npy','depth.npy','owners.npy'])
                for name,record in f['arrays'].items():
                    size,digest=array_payload(z.read(name+'.npy'),label+'.'+name,record)
                    frame_payload+=size;raw_hashes[f['view_name']][name]=digest
            check(label+'.payload_bytes',frame_payload,f['array_payload_bytes']);payload_bytes+=frame_payload
            check(label+'.six_returned_pixel_rows',len(f['pixel_rows']),6);pixel_rows+=len(f['pixel_rows'])
            check(label+'.pixel_count_completed', [f['pixel_evaluation_attempted_roi_count'],f['pixel_evaluation_completed']],[6,True])
            a=raw['render_attempts'][i-1]
            check(label+'.attempt_binding',[a['attempt_id'],a['view_name'],a['intent_ns'],a['intent_trace_sequence']],[i,f['view_name'],attempts[i-1]['monotonic_ns'],attempts[i-1]['sequence']])
            check(label+'.attempt_timeline',lo<=a['intent_ns']<=a['render_started_ns']<=a['render_closed_ns']<=a['completed_ns']<=hi)
            check(label+'.render_trace_times',[a['render_started_ns'],a['render_closed_ns']],[completed[i-1]['started_ns'],completed[i-1]['closed_ns']])
            check(label+'.complete_hashes',[frame_completed[i-1]['PNG_sha256'],frame_completed[i-1]['arrays_sha256']],[sha(png),sha(npz)])
        cost={'id':rid,'arm':row['arm'],'pair':row['pair'],'scenario':row['scenario'],'process_id':pid,
              'elapsed_ns':hi-lo,'render_attempts':n,'pixel_rows_returned':pixel_rows,
              'PNG_bytes':png_bytes,'NPZ_bytes':npz_bytes,'array_payload_bytes':payload_bytes,
              'metadata_bytes':metadata_bytes,'result_bytes':len(rb),'trace_bytes':len(raw_trace),
              'publication_bytes':len(read(folder/'RESULT_PUBLICATION.json')),
              'child_stage_sum_ns':sum(s['elapsed_ns'] for s in raw['stages'].values()),
              'startup_to_first_child_clock_ns':raw['started_ns']-lo,
              'parent_post_exit_ns':hi-row['process_exited_ns'],
              'child_work_ns':raw['work_closed_ns']-raw['started_ns']}
        for stream in ['stdout','stderr']:
            data=read(folder/(stream.upper()+'.bin'));cost[stream+'_bytes']=len(data)
            check(rid+'.'+stream+'_bytes',len(data),row[stream+'_bytes']);check(rid+'.'+stream+'_sha',sha(data),row[stream+'_sha256'])
        cost['text_artifact_bytes']=sum(cost[k] for k in ['metadata_bytes','result_bytes','trace_bytes','publication_bytes'])
        cost['stored_payload_bytes']=sum(cost[k] for k in ['text_artifact_bytes','PNG_bytes','NPZ_bytes','stdout_bytes','stderr_bytes'])
        check(rid+'.directory_total_bytes',sum(x.stat().st_size for x in folder.rglob('*') if x.is_file()),cost['stored_payload_bytes'])
        for key in ['PNG_bytes','NPZ_bytes','array_payload_bytes','metadata_bytes','result_bytes','trace_bytes','publication_bytes']:
            check(rid+'.facts_'+key,cost[key],facts[key])
        for key in ['PNG_bytes','NPZ_bytes','array_payload_bytes']:check(rid+'.metrics_'+key,cost[key],raw['metrics'][key])
        check(rid+'.metrics_metadata',metadata_bytes,raw['metrics']['frame_metadata_bytes'])
        check(rid+'.pixel_count',pixel_rows,raw['metrics']['pixel_tests'])
        check(rid+'.parent_validation_counts',[facts['validator_PNG_decodes'],facts['validator_pixel_tests']],[n,pixel_rows])
        check(rid+'.repeat_zero',raw['repeat_query']['new_render_attempts'],0)
        check(rid+'.repeat_unchanged',raw['repeat_query']['state_before'],raw['repeat_query']['state_after'])
        check(rid+'.six_discovered',len(raw['index']['roi_ids']),6)
        check(rid+'.five_covered',len(raw['final_state']['covered_roi_ids']),5)
        check(rid+'.one_unresolved',len(raw['final_state']['unresolved_roi_ids']),1)
        check(rid+'.unresolved_pool',raw['final_state']['unresolved_roi_ids'],raw['final_state']['candidate_pool_uncovered_roi_ids'])
        check(rid+'.no_final_pixel_shortfall',raw['final_pixel_shortfall_roi_ids'],[])
        run_costs.append(cost)
    # Compare both arms' final claims from their raw results, without author validator.
    for a,b in [(f'main_p{i:02}_A',f'main_p{i:02}_B') for i in range(1,7)]+[('control_A','control_B')]:
        for key in ['covered_roi_ids','unresolved_roi_ids','candidate_pool_uncovered_roi_ids']:
            check(a+'__'+b+'.'+key,raw_runs[a]['final_state'][key],raw_runs[b]['final_state'][key])
        check(a+'__'+b+'.source_scene',raw_runs[a]['source_scene_sha256'],raw_runs[b]['source_scene_sha256'])
        check(a+'__'+b+'.source_camera',raw_runs[a]['source_camera_sha256'],raw_runs[b]['source_camera_sha256'])
        check(a+'__'+b+'.candidate',raw_runs[a]['index']['candidate_identity'],raw_runs[b]['index']['candidate_identity'])
    control=raw_runs['control_B'];back=control['frames'][1]
    check('control_B.new_roi_counts',[len(s['new_roi_ids']) for s in control['steps']],[2,0,2,1])
    check('control_B.BACK_64',back['pose']['size_px'],[64,64])
    check('control_B.BACK_geometry_complete',len(control['steps'][1]['geometry_complete_roi_ids']),3)
    check('control_B.BACK_actual_readable',sum(x['readable'] for x in back['pixel_rows']),0)
    check('control_B.BACK_zero_surfaces_boundaries',all(x['visible_surface_pixels']==0 and x['contrasting_boundary_pixels']==0 for x in back['pixel_rows']))
    check('control_B.shortfall_history',len(control['pixel_shortfall_history_roi_ids']),3)
    # Reconstruct cost and order statistics using exact rational arithmetic.
    pairs=[]
    for i in range(1,7):
        arms={r['arm']:r['elapsed_ns'] for r in run_costs if r['scenario']=='main' and r['pair']==i}
        pairs.append({'pair':i,'A_ns':arms['A'],'B_ns':arms['B'],'B_over_A':frac(Fraction(arms['B'],arms['A']))})
    pairmedian=median(Fraction(x['B_ns'],x['A_ns']) for x in pairs)
    armmedian={a:median(x['elapsed_ns'] for x in run_costs if x['scenario']=='main' and x['arm']==a) for a in ['A','B']}
    rom=armmedian['B']/armmedian['A']
    for key,value in [('median_pair_ratio',pairmedian),('ratio_of_medians',rom),('A_median_ns',armmedian['A']),('B_median_ns',armmedian['B'])]:
        claim=results['summary'][key]
        check('summary.'+key,Fraction(claim['numerator'],claim['denominator'])==value)
    check('all_six_pairs_faster',sum(x['B_ns']<x['A_ns'] for x in pairs),6)
    group={}
    sumkeys=['elapsed_ns','render_attempts','pixel_rows_returned','PNG_bytes','NPZ_bytes','array_payload_bytes','metadata_bytes','result_bytes','trace_bytes','publication_bytes','stdout_bytes','stderr_bytes','text_artifact_bytes','stored_payload_bytes','child_stage_sum_ns','startup_to_first_child_clock_ns','parent_post_exit_ns','child_work_ns']
    for label,subset in [('main_A',[r for r in run_costs if r['scenario']=='main' and r['arm']=='A']),('main_B',[r for r in run_costs if r['scenario']=='main' and r['arm']=='B']),('controls',[r for r in run_costs if r['scenario']!='main']),('all_003',run_costs)]:
        group[label]={'runs':len(subset),**{k:sum(r[k] for r in subset) for k in sumkeys}}
    mainrenders=group['main_A']['render_attempts']+group['main_B']['render_attempts']
    check('main_render_budget_exact',mainrenders,48)
    check('control_render_count',group['controls']['render_attempts'],10)
    check('new_render_total',group['all_003']['render_attempts'],58)
    check('new_render_cap',group['all_003']['render_attempts']<=prereg['limits']['all_render_attempts_including_preparation_and_failures'])
    # Qualification: independent record/clock checks of four pre-existing no-image probes.
    qualification=js(AUTHOR/'qualification/RESULTS.json')
    qfinal=js(AUTHOR/'qualification/FINAL_TIMING.json')
    check('qualification_digest_in_batch',sha(read(AUTHOR/'qualification/RESULTS.json')),results['qualification_result_sha256'])
    check('qualification_source_freeze',qualification['source_freeze_sha256'],results['freeze_sha256'])
    check('qualification_cases',[c['scenario'] for c in qualification['cases']],['normal','nonzero','timeout','receipt_failure'])
    check('qualification_count',qualification['actual_child_processes'],4)
    check('qualification_new_raster',qualification['new_raster_calls'],0)
    check('qualification_new_external_calls',qualification['new_model_provider_Blender_API_runs'],0)
    check('qualification_summary_pass',qualification['all_passed'])
    qt=qualification['timing'];qlo=qt['started_ns'];qwork=qt['work_closed_before_result_publication_ns']
    interval('qualification_final_timing',qfinal,qlo,bstart)
    check('qualification_result_then_final',qwork<=qfinal['closed_ns']<=bstart)
    qrows=[];q_last=qlo
    for case in qualification['cases']:
        label='qualification.'+case['scenario'];folder=AUTHOR/'qualification'/case['scenario']
        saved=js(folder/'CASE.json');qtime=js(folder/'FINAL_TIMING.json');penv=js(folder/'ENVIRONMENT.json');ps=js(folder/'PARENT_START.json')
        check(label+'.embedded_case',saved,case)
        check(label+'.same_pid',[case['Popen_pid'],case['actual_pid'],penv['process_id'],case['handshake']['process_id'],ps['Popen_pid']],[case['Popen_pid']]*5)
        check(label+'.actual_launch_environment',case['launch_environment'],penv)
        check(label+'.source_runtime',penv['base_executable_sha256'],prereg['direct_launch']['base_executable_sha256'])
        check(label+'.direct_command',same_path(case['command'][0],penv['python_executable']) and same_path(case['command'][5],AUTHOR/'bootstrap.py') and same_path(case['command'][6],AUTHOR/'probe.py'))
        check(label+'.started_once',case['process_started'])
        check(label+'.passed',case['passed'])
        check(label+'.no_errors',case['errors'],[])
        check(label+'.no_images',case['new_raster_calls'],0)
        check(label+'.no_external_calls',case['new_model_provider_Blender_API_runs'],0)
        check(label+'.sequential',q_last<=case['started_ns']);q_last=qtime['closed_ns']
        interval(label+'.full_case',qtime,qlo,qwork)
        check(label+'.case_start',qtime['started_ns'],case['started_ns'])
        stamps=[case['started_ns'],case['before_Popen_ns'],case['Popen_returned_ns'],case['handshake_confirmed_ns'],case['wait_boundary_ns'],case['cleanup']['started_ns'],case['cleanup']['closed_ns'],case['streams_closed_ns'],case['readback_closed_ns'],qtime['closed_ns']]
        check(label+'.timeline',stamps==sorted(stamps))
        cl=case['cleanup'];interval(label+'.cleanup',cl,case['wait_boundary_ns'],case['streams_closed_ns'])
        check(label+'.cleaned',[cl['confirmed'],cl['reaped'],cl['process_handle_closed'],all(cl['pipes_closed'].values()),case['parent_files_closed'],cl['errors']],[True,True,True,True,True,[]])
        qevents=trace(folder/'TRACE.jsonl',case['actual_pid'],case['before_Popen_ns'],case['wait_boundary_ns'],scenario=case['scenario'])
        check(label+'.no_raster_events',not any('render' in e['event'] or 'raster' in e['event'] for e in qevents))
        for rel,digest in case['files_sha256'].items():check(label+'.file.'+rel,sha(read(folder/rel)),digest)
        if case['scenario']=='normal':check(label+'.normal_receipt',[case['exit_code'],case['receipt_validation']['passed'],case['action_count']],[0,True,0])
        if case['scenario']=='nonzero':check(label+'.nonzero',[case['exit_code'],case['receipt_validation']['passed'],case['action_count']],[1,False,0])
        if case['scenario']=='timeout':
            check(label+'.deadline_250ms',case['registered_wait_deadline_ns']-case['handshake_confirmed_ns'],250000000)
            check(label+'.real_timeout',case['timeout_after_handshake'] and cl['kill_requested'] and case['wait_boundary_ns']>=case['registered_wait_deadline_ns'])
        if case['scenario']=='receipt_failure':
            check(label+'.marker_once',[case['action_count'],case['child_state']['marker_actions'],case['exit_code'],case['receipt_validation']['passed']],[1,1,0,False])
            check(label+'.missing_receipt',not (folder/'RECEIPT.json').exists())
        qrows.append({'scenario':case['scenario'],'pid':case['actual_pid'],'elapsed_ns':qtime['elapsed_ns'],'raster_attempts':0,'action_count':case['action_count'],'exit_code':case['exit_code']})
    # Keep the failed 002 denominator and charged images separate.
    old=js(AUTHOR.parent/'m4_active_coverage_002/RESULTS.json')
    oldmain=Counter(r['status'] for r in old['rows']);oldcontrols=Counter(r['status'] for r in old['controls'])
    check('old_002_main_status_preserved',dict(oldmain),{'failed':1,'not_run':11})
    check('old_002_control_status_preserved',dict(oldcontrols),{'not_run':2})
    oldrenders=sum(r.get('render_attempts',0) for r in old['rows']+old['controls'])
    check('old_002_charged_renders',oldrenders,6)
    cross=oldrenders+group['all_003']['render_attempts']
    check('cross_charged_renders',cross,64);check('cross_cap',cross<=prereg['limits']['cross_002_003_render_attempts'])
    oldtime=old['batch_closed_before_publication_ns']-old['batch_started_ns']
    check('old_002_window',oldtime,old['whole_batch_through_analysis_ns'])
    # All post-primary gaps are retained in the whole batch, never silently dropped.
    timing={
      'main_primary_sum_ns':group['main_A']['elapsed_ns']+group['main_B']['elapsed_ns'],
      'control_primary_sum_ns':group['controls']['elapsed_ns'],
      'all_primary_sum_ns':group['all_003']['elapsed_ns'],
      'formal_whole_batch_through_analysis_ns':bclose-bstart,
      'formal_common_setup_ns':results['common_parent_setup']['elapsed_ns'],
      'formal_outside_primary_total_ns':bclose-bstart-group['all_003']['elapsed_ns'],
      'formal_outside_primary_except_common_setup_ns':bclose-bstart-group['all_003']['elapsed_ns']-results['common_parent_setup']['elapsed_ns'],
      'qualification_before_RESULTS_publication_ns':qwork-qlo,
      'qualification_including_RESULTS_writeclose_ns':qfinal['closed_ns']-qlo,
      'qualification_case_windows_sum_ns':sum(c['elapsed_ns'] for c in qrows),
      'qualification_overhead_outside_cases_ns':qfinal['closed_ns']-qlo-sum(c['elapsed_ns'] for c in qrows),
      'qualification_plus_formal_recorded_windows_ns':qfinal['closed_ns']-qlo+bclose-bstart,
      'gap_qualification_end_to_formal_start_ns':bstart-qfinal['closed_ns'],
      'span_from_qualification_start_to_formal_analysis_end_ns':bclose-qlo,
      'old_002_whole_window_ns':oldtime,
      'cross_002_003_recorded_windows_ns':oldtime+qfinal['closed_ns']-qlo+bclose-bstart,
    }
    check('known_timing_claims',[timing['main_primary_sum_ns'],timing['control_primary_sum_ns'],timing['formal_whole_batch_through_analysis_ns'],timing['qualification_including_RESULTS_writeclose_ns']],[12968602900,2329854600,16502010700,3155142200])
    for p,rec in list(INPUTS.items()):check('input_unchanged.'+str(Path(p)),sha(Path(p).read_bytes()),rec['sha256'])
    report={
       'schema':'independent-cost-audit-v1','author_commit':COMMIT,'scope':'Offline record/byte/timing arithmetic; no author code import, no engine, no image generation, no performance rerun.',
       'own_agent_handle':'08e9bc2425e346dc97e95f0df32d3fbe','full_source_manifest_audit':'Delegated to root, not duplicated here.',
       'checks_total':len(CHECKS),'checks_passed':sum(x['passed'] for x in CHECKS),'failures':[x for x in CHECKS if not x['passed']],
       'denominators':{'main_planned':12,'main_completed':12,'main_failed':0,'main_not_run':0,'pairs':6,'controls_planned':2,'controls_completed':2},
       'pairs':pairs,'A_median_ns':frac(armmedian['A']),'B_median_ns':frac(armmedian['B']),
       'median_pair_B_over_A':frac(pairmedian),'median_pair_reduction':frac(1-pairmedian),'ratio_arm_medians':frac(rom),'ratio_arm_median_reduction':frac(1-rom),
       'run_costs':run_costs,'groups':group,'main_child_stage_sums_by_arm_ns':dict(stages_by_arm),
       'qualification':qrows,'timing':timing,'cross_renders':{'old_002':oldrenders,'new_003':group['all_003']['render_attempts'],'total':cross,'registered_limit':prereg['limits']['cross_002_003_render_attempts']},
       'historical_002':{'main_statuses':dict(oldmain),'control_statuses':dict(oldcontrols),'failed_slot_elapsed_ns':old['rows'][0]['elapsed_ns'],'whole_batch_ns':oldtime,'renders':oldrenders,'pid_ancestry':'unknown; this audit does not retroactively repair 002'},
       'unmeasured':['Controller process startup, initial standard-library imports and FROZEN read','Formal final RESULTS self-publication and outer controller receipt publication','Development/preparation/review duration; qualification-to-formal gap is wall-clock only, not attributed compute','Python/Fraction/index heap and peak RSS','Model task correctness, actual model input/output tokens, model call rounds, service elapsed time and charges','OS cold-cache behavior; only application image caches were empty','Generic scenes/material/texture/model semantic visual recognition; fixed six-camera finite pool only'],
       'inspection_notes':['One initial exploratory read guessed PREREG.json; actual file is PREREGISTRATION.json. FileNotFoundError was a schema discovery error, not an experiment failure. No experiment was run or repeated.','PNG file bytes/hash/header and NPZ raw payload bytes/hash rechecked; no image rerender, no geometric scorer, no pixel-rule recomputation. Parent validation-count fields are reconciled to returned rows, not claimed as independent parent-code execution.'],
       'cost_interpretation':'26.30% reduction is median of six registered full child-process paired ratios including parent readback. 19.6571529 seconds is the sum of two measured preparation/formal windows, not total development or model end-to-end cost. Text artifact bytes are disk bytes, not model tokens.',
    }
    OUT.mkdir(parents=True,exist_ok=True)
    for name,value in [('INPUTS.json',{'inputs':list(INPUTS.values())}),('CHECKS.json',CHECKS),('RESULTS.json',report)]:
        with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:report[k] for k in ['checks_total','checks_passed','failures','median_pair_B_over_A','groups','timing']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
