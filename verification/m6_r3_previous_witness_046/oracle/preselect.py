"""046 fixed-order C-only eligibility and independent archived truth binding.

No D source/path/import is accessed. Two previously documented families are
screened in their original query order, with no geometry generation or tuning.
"""
from __future__ import annotations
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path('D:/HumanEye/runs/M6-046-R3-PREVIOUS-WITNESS/oracle')
C_SITE=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region/site-packages')
C_SHA='b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e'
F44=Path('D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/oracle')
F43=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/quality/prepared_004')

def pin(path):
    p=Path(path).resolve(strict=True);b=p.read_bytes()
    return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as out:json.dump(value,out,indent=2,allow_nan=False);out.write('\n')
    return pin(path)
def exact(value):
    if isinstance(value,Q):return str(value)
    if isinstance(value,dict):return {k:exact(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [exact(v) for v in value]
    return value
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rank(key):n,d,e=key;return Q(n,d)*Q(2)**e

def restore_cases():
    f44=read(F44/'INPUTS.json');assert pin(f44['geometry']['path'])==f44['geometry']
    doc=read(f44['geometry']['path']);objects=doc['objects']
    primary={'id':'closed_solid_original_96_12','asset':f44['originals']['scene.blend'],
        'source_input':pin(F44/'INPUTS.json'),'source_geometry':f44['geometry'],'independent_truth':pin(F44/'TRUTH.json'),
        'pair':['Object_01','Object_02'],'request':f44['original_request'],
        'facts':['closed_solid_relation','surface_proximity'],
        'left':{'name':'Object_01','vertices_world':objects['Object_01']['vertices_world_m'],'faces':objects['Object_01']['triangles']},
        'right':{'name':'Object_02','vertices_world':objects['Object_02']['vertices_world_m'],'faces':objects['Object_02']['triangles']}}
    binding=read(F43/'ARCHIVE_BINDING.json');assert pin(binding['snapshot']['path'])==binding['snapshot']
    snapshot=read(binding['snapshot']['path']);objects={x['name']:x for x in snapshot['objects']}
    secondary={'id':'original_unrotated_assembly_128_28','asset':binding['blend'],
        'source_input':pin(F43/'ARCHIVE_BINDING.json'),'source_geometry':binding['snapshot'],
        'independent_truth':pin(F43/'ARCHIVE_ORACLE.json'),'pair':binding['pair'],
        'request':{'include_image':False,'query':binding['query']},'facts':['surface_proximity']}
    for label,name in zip(('left','right'),binding['pair']):
        secondary[label]={'name':name,'vertices_world':objects[name]['vertices_world'],'faces':objects[name]['triangles']}
    return [primary,secondary]

class Observer:
    def __init__(self,kernel):
        self.kernel=kernel;self.calls=[];self.positive=[];self.nonparallel=[]
    def profile(self,frame,event,arg):
        if event!='return' or frame.f_code is not self.kernel._nearest_pair.__code__ or arg is None:return
        local=frame.f_locals;before=local['best'];after=arg;budget=local['budget']
        caller=frame.f_back;pair=caller.f_locals.get('pair')
        if pair is None:pair=(local.get('left_idx'),local.get('right_idx'))
        count=budget.counts['narrow_phase_pairs'];q=Q(after[0],after[1])
        reason='same_or_nonimproving'
        if before is None:reason='first_completed_bound'
        elif q<Q(before[0],before[1]):reason='strict_improvement'
        elif after is not before and q==Q(before[0],before[1]):reason='equal_distance_representative_change'
        item={'completed_exact_ordinal':count,'pair':list(pair),'before_squared_integer_frame':None if before is None else str(Q(before[0],before[1])),
            'after_squared_integer_frame':str(q),'change':reason,'work_units_at_completion':budget.counts['work_units']}
        if reason in ('first_completed_bound','strict_improvement') and q>0:
            points=self.kernel._witness(after[2]);direction=tuple(Q(b)-Q(a) for a,b in zip(*points))
            item['direction_exact_integer_frame']=[str(x) for x in direction]
            item['witness_points_integer_frame']=[[str(x) for x in p] for p in points]
            if self.positive:
                previous=self.positive[-1];old=tuple(map(Q,previous['direction_exact_integer_frame']))
                nonparallel=any(cross(old,direction))
                if nonparallel:self.nonparallel.append({'previous':dict(previous),'current':dict(item),'exact_cross':[str(x) for x in cross(old,direction)]})
            self.positive.append(dict(item))
        self.calls.append(item)

def eligibility(case,kernel,helpers):
    factory,task_query,cacheclass=helpers
    meshes=factory([(case[label]['vertices_world'],case[label]['faces'],('046',case['id'],label),case[label]['name']) for label in ('left','right')])
    observer=Observer(kernel);diagnostics={};deadline=time.monotonic()+30.
    def checkpoint(stage):
        if time.monotonic()>=deadline:raise TimeoutError(stage)
    began=time.perf_counter_ns();cpu=time.process_time_ns();previous=sys.getprofile()
    sys.setprofile(observer.profile)
    try:
        facts,surface=task_query._closed_surface_facts(*meshes,set(case['facts']),cacheclass(),checkpoint,
            {'source':'046_fixed_archived_source','geometry_sha256':case['source_geometry']['sha256']},diagnostics,rank=True)
    finally:sys.setprofile(previous)
    truth=read(case['independent_truth']['path'])
    q=Q(truth.get('exact_distance_squared_world_m2',truth.get('distance_squared')))
    assert surface['measurement_valid'] and rank(surface['_exact_distance_sq'])==q
    total=surface['work']['narrow_phase_pairs']
    opportunities=[x for x in observer.nonparallel if x['current']['completed_exact_ordinal']<total]
    projection=surface['work'].get('witness_projection_tests',0)
    return {'case':case['id'],'status':'known_exact','runtime_source_sha256':C_SHA,'surface':surface,'facts':facts,
        'diagnostics':diagnostics,'completed_exact_calls':observer.calls,'positive_real_bounds':observer.positive,
        'nonparallel_previous_events':observer.nonparallel,'nonparallel_with_later_exact_need':opportunities,
        'geometry_eligible':bool(opportunities),'ordinary_projection_tests':projection,
        'ordinary_projection_opportunity_eligible':bool(opportunities) and projection>0,
        'scope':'offline passive C-only production task fact path, restored original archived arrays; no D and no host',
        'cost_wall_ns':time.perf_counter_ns()-began,'cost_cpu_ns':time.process_time_ns()-cpu}

def main():
    began=time.perf_counter_ns();cpu=time.process_time_ns();RAW.mkdir(parents=True,exist_ok=False)
    binding_path=C_SITE.parent/'admin/RUNTIME_BINDING.json';binding=read(binding_path)
    assert binding['identity']['source_sha256']==C_SHA and len(binding['source_files'])==143
    for row in binding['source_files']:assert pin(C_SITE/row['path'])['sha256']==row['sha256']
    cases=restore_cases()
    for case in cases:
        for name in ('asset','source_input','source_geometry','independent_truth'):assert pin(case[name]['path'])==case[name]
    specs=save(RAW/'CANDIDATES.json',cases)
    plan=save(RAW/'PLAN.json',{'schema':'m6-046-independent-holdout-prereg-v1','source':pin(__file__),
        'contract':'7beb04ad3e5a546911396b3043d8e49b19a3bcfc','C_binding':pin(binding_path),'C_identity':binding['identity'],
        'candidate_order':[x['id'] for x in cases],'candidates':specs,
        'selection_rule':'first fixed-order known C case with real nonparallel positive prior bound, later exact calls, and existing ordinary projection tests; '
            'otherwise first geometry-eligible case with explicit no ordinary projection/actual trigger gap; otherwise no real eligible case',
        'C_only_passive_observer':'_nearest_pair return events; original return value untouched; initial finite bound and strict improvements separated from equal-distance tie changes',
        'no_D_read_or_import':True,'no_new_geometry':True,'Blender':0,'MCP':0})
    sys.path.insert(0,str(C_SITE))
    from human_eye_plugin import surface_proximity as kernel,task_query
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity(mode='live');assert identity['source_sha256']==C_SHA
    rows=[];refs=[]
    for case in cases:
        row=eligibility(case,kernel,(_meshes_from_objects,task_query,SpatialSceneCache));rows.append(row)
        refs.append(save(RAW/(case['id']+'_C_ONLY.json'),exact(row)))
    eligible=[i for i,x in enumerate(rows) if x['ordinary_projection_opportunity_eligible']]
    if not eligible:eligible=[i for i,x in enumerate(rows) if x['geometry_eligible']]
    selected=eligible[0] if eligible else None
    choice=None
    if selected is not None:
        case=cases[selected];geometry=save(RAW/'GEOMETRY.json',{'case':case['id'],'unit':'m','source_kind':'existing_archived_native_asset',
            'left':case['left'],'right':case['right']})
        truth=save(RAW/'TRUTH.json',{'schema':'m6-046-independent-frozen-holdout-truth-v1','geometry':geometry,
            'independent_reference':case['independent_truth'],'truth':read(case['independent_truth']['path'])})
        choice={'case':case['id'],'asset':case['asset'],'geometry':geometry,'independent_truth':truth,
            'original_request':case['request'],'C_eligibility':refs[selected],
            'ordinary_projection_opportunity_eligible':rows[selected]['ordinary_projection_opportunity_eligible'],
            'D_actual_trigger':'unmeasured; no D has been read or run',
            'frozen_before_D':True}
    result={'schema':'m6-046-independent-holdout-freeze-v1','status':'pass' if choice else 'no_real_eligible_holdout',
        'plan':plan,'C_only_controls':refs,'selected':choice,'exclusions':[
            {'case':case['id'],'selected':i==selected,'known_C':True,'positive_bounds':len(row['positive_real_bounds']),
             'nonparallel_events':len(row['nonparallel_previous_events']),'later_exact_opportunities':len(row['nonparallel_with_later_exact_need']),
             'projection_tests':row['ordinary_projection_tests'],'reason':'selected fixed-order eligible' if i==selected else
                'no nonparallel previous followed by exact work' if not row['geometry_eligible'] else
                'no original ordinary projection opportunity' if not row['ordinary_projection_opportunity_eligible'] else 'later fixed-order eligible family'}
            for i,(case,row) in enumerate(zip(cases,rows))],
        'runtime_identity':{k:identity[k] for k in ('source_sha256','distribution_version','implementation_revision')},
        'C_files_verified':143,'D_imports':0,'D_results_read':0,'new_geometry':0,'Blender':0,'MCP':0,
        'cost_wall_ns':time.perf_counter_ns()-began,'cost_cpu_ns':time.process_time_ns()-cpu,
        'cost_scope':'whole Python selection function inclusive source verification and C-only passive calls; startup excluded'}
    ref=save(RAW/'RESULTS.json',result);print(json.dumps({'result':ref,'status':result['status'],'selected':choice and choice['case']}))

if __name__=='__main__':main()
