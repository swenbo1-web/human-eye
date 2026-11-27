"""043 independent, predeclared mathematical and budget checks; never a timing benchmark.

All geometry and test orders are sealed before the first tested kernel import.
Fraction reference is the independent 029 feature enumerator, not any A/B/C kernel.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback
from types import ModuleType

HERE = Path(__file__).resolve().parent
VER = HERE.parents[1]
RAW = Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/quality')
OLD = VER/'m6_bvh_work_credit_031'
ORACLE = VER/'m6_bvh_witness_projection_029/oracle.py'
SITES = {
    'A': Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/032/.human-eye/releases/9.7.2+k041hook032/site-packages'),
    'B': Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/r3/.human-eye/releases/9.7.2+k041hookr3/site-packages'),
    'C': Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region/site-packages'),
}
SOURCE_IDENTITIES={
    'A':'a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d',
    'B':'ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e',
    'C':'b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e',
}
SEMANTIC = ('measurement_valid','distance_m','point_a_world','point_b_world','direction_a_to_b',
    'witness_status','direction_status','reason','witness_reason','direction_reason',
    'witness_triangle_indices','exact_witness_triangles','method','topology','_exact_distance_sq')


def pin(path):
    p=Path(path).resolve(strict=True); raw=p.read_bytes()
    return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def save(path, value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n') as out:
        json.dump(value,out,ensure_ascii=False,allow_nan=False,indent=2);out.write('\n')
    return pin(p)


def read(ref):
    p=Path(ref['path']);assert pin(p)==ref, p
    return json.loads(p.read_bytes())


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod


class Mesh:
    def __init__(self,name,vertices,faces):
        self.name=self.object_id=name
        # Lists deliberately disable immutable-object tree caches in these cold correctness calls.
        self.vertices=[tuple(map(float,p)) for p in vertices]
        self.faces=[tuple(map(int,f)) for f in faces]
    def json(self):return {'name':self.name,'vertices':self.vertices,'faces':self.faces}


def cube(name,radii=(1.,1.,1.),offset=(0.,0.,0.),repeat=1,rotation=False):
    points=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
            (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    vertices=[]
    for p in points:
        x,y,z=(p[i]*radii[i] for i in range(3))
        if rotation:x,y=-y,x  # exact 90-degree orthogonal rotation, no trigonometric rounding.
        vertices.append((x+offset[0],y+offset[1],z+offset[2]))
    faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
           (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return Mesh(name,vertices,faces*repeat)


def bounds(mesh):
    used={i for f in mesh.faces for i in f}
    return ([min(Q(mesh.vertices[i][k]) for i in used) for k in range(3)],
            [max(Q(mesh.vertices[i][k]) for i in used) for k in range(3)])


def contained(a,b):
    lo,hi=bounds(a);otherlo,otherhi=bounds(b)
    return all(otherlo[k]<lo[k] and hi[k]<otherhi[k] for k in range(3)) or all(
        lo[k]<otherlo[k] and otherhi[k]<hi[k] for k in range(3))


def fixtures():
    result=[]
    specifications=[
        ('contained_symmetric_ties',{},{}),
        ('touch_root_boundary',{'offset':(1.,0.,0.)},{}),
        ('external',{'offset':(4.,0.,0.)},{}),
        ('partial_overlap',{'offset':(1.5,0.,0.),'radii':(1.,2.,1.)},{}),
        ('rotated_asymmetric',{'radii':(.5,.75,1.),'rotation':True},{'radii':(2.,3.,4.)}),
        ('near_equal_dyadic',{'radii':(1.,1.,1.+2.**-30)},{}),
        ('large_common_origin',{'offset':(2.**40,)*3},{'offset':(2.**40,)*3}),
    ]
    for name,inside,outside in specifications:
        left=cube('left',repeat=2,**inside);right=cube('right',**({'radii':(2.,2.,2.)}|outside))
        for swap in (False,True):
            a,b=(right,left) if swap else (left,right)
            result.append({'id':name+('_swap' if swap else ''),'left':a.json(),'right':b.json(),
                'root_strict_containment':contained(a,b),'oracle':'029 exhaustive Fraction original ordered triangle pairs',
                'public_float_input':True,'priority_shift_expected':0,
                'large_origin_is_not_the_internal_shift_guard':name=='large_common_origin'})
    return result


def prepare(output):
    output=Path(output).resolve();assert output.is_relative_to(RAW.resolve());output.mkdir(parents=True,exist_ok=False)
    began=time.perf_counter_ns();cpu=time.process_time_ns()
    frozen=save(output/'FIXTURES.json',fixtures())
    archive=VER/'m6_bvh_witness_projection_029/private/inputs/M4_snapshot.json'
    blend=archive.with_name('M4_blend.blend')
    assert pin(archive)['sha256']=='7caf71a71d66e1576c069bdc47a60f8e7ab6dd680c29eaf8f9375415bb255436'
    assert pin(blend)['sha256']=='7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66'
    snap=json.loads(archive.read_bytes());objects={x['name']:x for x in snap['objects']}
    pair=[Mesh(name,objects[name]['vertices_world'],objects[name]['triangles']) for name in ('Obj_014','Obj_003')]
    truth_path=OLD/'private/ORACLE_FOR_ENTRY.json';historical=json.loads(truth_path.read_bytes())['m4_independent_heavy']
    archive_ref=save(output/'ARCHIVE_BINDING.json',{'scene':'original unrotated 24-piece assembly','pair':['Obj_014','Obj_003'],
        'snapshot':pin(archive),'blend':pin(blend),'truth_source':pin(truth_path),'truth':historical,
        'triangle_counts':[len(x.faces) for x in pair],'root_strict_containment':contained(*pair),
        'selection':'fixed pre-candidate from 029 existing independent family index, no replacement if inactive',
        'query':{'mode':'task','objects':[{'name':n} for n in ('Obj_014','Obj_003')],'requested_facts':['surface_proximity']}})
    plan=save(output/'PLAN.json',{'schema':'m6-043-independent-correctness-prereg-v1','source':pin(__file__),
        'oracle_source':pin(ORACLE),'fixtures':frozen,'archive':archive_ref,
        'historical_generator':pin(OLD/'test_controls.py'),
        'historical_generator_dependency':pin(VER/'m6_bvh_projection_yield_030/test_controls.py'),
        'historical_corrected_AF_barrier':pin(OLD/'private/controls/attempt_002_AF/AF_BARRIER.json'),
        'arms':{k:str(v) for k,v in SITES.items()},'arm_order':['A','B','C'],
        'budget_cases':[{'kind':'zero489','prepaid':n} for n in (0,39,40,41,42,43)]+
            [{'kind':'first_yield','prepaid':0},{'kind':'original030','prepaid':0}],
        'budget_analytic_truth':{'squared':'3','canonical':{'zero489':[0,0],'first_yield':[0,1],'original030':[0,0]}},
        'internal_shift_fixture':'031 exact prepared integer fixture, full three-axis containing roots, 4097-bit total span',
        'extra_controls':['original face limit','narrow/work hard limit','independent credit lifecycle',
            'forged prior diagnostics cannot fund query','cooperative abort identity','unchanged actual original deadline'],
        'rules':['inactive C result and every work counter bit-identical to B',
            'all successful synthetic and archive distances/earliest source pairs checked by independent Fraction',
            'all A/B existing status differences explicit; every new C unknown fails',
            'no raised limits or deadlines; no face/object/frame selector in candidate'],
        'not_a_timing_benchmark':True,'Blender':0,'models':0})
    oracle=load('_043_fraction_reference',ORACLE);answers=[]
    for item in read(frozen):
        a,b=(Mesh(**item[side]) for side in ('left','right'))
        value=oracle.exhaustive(a,b)
        answers.append({'id':item['id'],**oracle.json_exact(value),
            'correctly_rounded_distance':oracle.nearest_float_sqrt(value['distance_squared'])})
    oracle_ref=save(output/'ORACLES.json',answers)
    # Independent full Fraction proof also rechecks, rather than trusting, the selected historic pair.
    value=oracle.exhaustive(*pair)
    assert str(value['distance_squared'])==historical['distance_squared'] and list(value['input_pair'])==historical['input_pair']
    archive_proof=save(output/'ARCHIVE_ORACLE.json',oracle.json_exact(value))
    receipt=save(output/'PREPARED.json',{'status':'pass','plan':plan,'oracles':oracle_ref,'archive_oracle':archive_proof,
        'case_count':len(answers),'cost_wall_ns':time.perf_counter_ns()-began,'cost_cpu_ns':time.process_time_ns()-cpu,
        'tested_kernel_imports':0,'Blender':0,'MCP':0})
    print(json.dumps(receipt));return receipt


def binary(v):
    if type(v) is float:return {'float64':struct.pack('<d',v).hex()}
    if isinstance(v,dict):return {k:binary(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [binary(x) for x in v]
    return v


def semantic(v):return {k:v[k] for k in SEMANTIC if k in v}


def key_fraction(key):
    n,d,e=key;return Q(n,d)*(Q(2)**e)


def engine(arm,site):
    alias='_043_correctness_'+arm;package=ModuleType(alias);package.__path__=[str(Path(site)/'human_eye_plugin')]
    sys.modules[alias]=package
    return importlib.import_module(alias+'.surface_proximity')


def call(kernel,left,right,*,prepaid=0,checkpoint=None,diagnostics=None):
    holder={};stages=[];credits=[];original_work=kernel._Work;original_credit=kernel._ProjectionCredit.__init__
    class Prepaid(original_work):
        def __init__(self,check,stats):
            super().__init__(check,stats)
            if prepaid:self.consume(prepaid,'equivalent_prepaid_prior_work')
    def credit_init(self,work):original_credit(self,work);credits.append(self)
    def check(stage):
        stages.append(stage)
        if checkpoint:checkpoint(stage)
    kernel._Work=Prepaid;kernel._ProjectionCredit.__init__=credit_init
    began=time.perf_counter_ns();cpu=time.process_time_ns()
    try:
        value=kernel.measure_surface_proximity(left,right,check,retain_exact_rank=True,
            retain_witness_triangles=True,_prepared_holder=holder,diagnostics=diagnostics)
    finally:
        kernel._Work=original_work;kernel._ProjectionCredit.__init__=original_credit
    row={'result':value,'work':dict(holder['work'].counts),'checkpoint_stages':sorted(set(stages)),
        'cost_wall_ns':time.perf_counter_ns()-began,'cost_cpu_ns':time.process_time_ns()-cpu,
        'prepaid':prepaid,'credits':[],'credit_valid':True}
    for credit in credits:
        fields={k:getattr(credit,k) for k in ('balance','spent','earned_bounds','earned_narrow','earned_node_prune','available_credit','pending_work_start') if hasattr(credit,k)}
        row['credits'].append(fields)
        valid=fields.get('balance',0)>=0 and fields.get('available_credit',0)>=0 and fields.get('pending_work_start') is None
        if 'earned_bounds' in fields:
            valid=valid and fields['balance']==fields['earned_bounds']+fields['earned_narrow']+fields.get('earned_node_prune',0)-fields['spent']
        row['credit_valid']=row['credit_valid'] and valid
    if 'witness_points' in holder:
        origin,factor=holder['pair'][2:4]
        row['exact_points_world']=[[str(origin[k]+Q(x[k])/factor) for k in range(3)] for x in holder['witness_points']]
    return row


def validate(row,reference,left,right,oracle):
    assert row['credit_valid'],row['credits']
    result=row['result'];assert result['measurement_valid'],result
    exact=Q(reference['distance_squared']);pair=reference['input_pair']
    assert key_fraction(result['_exact_distance_sq'])==exact
    native=result.get('exact_witness_triangles',{}).get('indices',result.get('witness_triangle_indices'))
    assert native==list(pair)
    points=tuple(tuple(Q(x) for x in p) for p in row['exact_points_world'])
    oracle.validate_exact_witness({'distance_squared':exact,'input_pair':pair},pair,points,left,right)
    assert result['distance_m'].hex()==oracle.nearest_float_sqrt(exact).hex()


def run(prepared,output,candidate_site=None):
    prepared=Path(prepared);out=Path(output).resolve();assert out.is_relative_to(RAW.resolve());out.mkdir(parents=True,exist_ok=False)
    prep=json.loads(prepared.read_bytes());plan=read(prep['plan']);assert pin(__file__)==plan['source']
    for key in ('oracle_source','historical_generator','historical_generator_dependency','historical_corrected_AF_barrier'):
        assert pin(plan[key]['path'])==plan[key]
    sites=dict(plan['arms']);
    if candidate_site:sites['C']=str(Path(candidate_site).resolve())
    sources={arm:pin(Path(site)/'human_eye_plugin/surface_proximity.py') for arm,site in sites.items()}
    bindings={}
    for arm,site in sites.items():
        binding_path=Path(site).parent/'admin/RUNTIME_BINDING.json';binding=json.loads(binding_path.read_bytes())
        assert Path(binding['site_packages']).resolve()==Path(site).resolve()
        assert binding['identity']['source_sha256']==SOURCE_IDENTITIES[arm] and len(binding['source_files'])==143
        for item in binding['source_files']:assert pin(Path(site)/item['path'])['sha256']==item['sha256']
        bindings[arm]={'binding':pin(binding_path),'identity':binding['identity'],'files_verified':143}
    run_plan=save(out/'PLAN.json',{'prepared':pin(prepared),'source':pin(__file__),'kernel_sources':sources,
        'installation_bindings':bindings,'sites':sites,'not_timing':True})
    started=time.perf_counter_ns();cpu=time.process_time_ns();refs=[];errors=[]
    result={'status':'fail','plan':run_plan,'rows':refs,'errors':errors,'not_timing':True,'Blender':0,'models':0}
    try:
        kernels={arm:engine(arm,site) for arm,site in sites.items()}
        assert all(k.MAX_WORK_UNITS==1179648 and k.MAX_FACES==4096 and k.MAX_NARROW_PHASE_PAIRS==16384 for k in kernels.values())
        # Check the whole module rather than only selected budget helpers: exactly _nearest_tree may differ.
        for name,original in vars(kernels['B']).items():
            candidate=getattr(kernels['C'],name,None)
            if name=='_nearest_tree' or not (inspect.isfunction(original) or inspect.isclass(original)):continue
            if getattr(original,'__module__',None)!=kernels['B'].__name__:continue
            assert inspect.getsource(original)==inspect.getsource(candidate),name
        oracle=load('_043_reference_run',ORACLE);truth={x['id']:x for x in read(prep['oracles'])}
        for item in read(plan['fixtures']):
            a,b=(Mesh(**item[side]) for side in ('left','right'));arms={}
            for arm,k in kernels.items():
                row=call(k,a,b);save(out/'raw'/f'{item["id"]}_{arm}.json',row)
                validate(row,truth[item['id']],a,b,oracle);arms[arm]=row
            assert binary(semantic(arms['B']['result']))==binary(semantic(arms['C']['result']))
            if not item['root_strict_containment']:assert binary(arms['B']['work'])==binary(arms['C']['work'])
            refs.append(save(out/(item['id']+'.json'),{'case':item,'arms':arms,'status':'pass','independent_oracle':truth[item['id']]}))
            print(item['id']+' pass',flush=True)
        binding=read(plan['archive']);snapshot=read(binding['snapshot']);objects={x['name']:x for x in snapshot['objects']}
        a,b=[Mesh(n,objects[n]['vertices_world'],objects[n]['triangles']) for n in binding['pair']]
        exact=read(prep['archive_oracle']);arms={}
        for arm,k in kernels.items():
            row=call(k,a,b);save(out/'raw'/f'other_family_{arm}.json',row)
            validate(row,exact,a,b,oracle);arms[arm]=row
        assert binary(semantic(arms['B']['result']))==binary(semantic(arms['C']['result']))
        if not binding['root_strict_containment']:assert binary(arms['B']['work'])==binary(arms['C']['work'])
        refs.append(save(out/'other_family.json',{'status':'pass','binding':plan['archive'],'arms':arms,'independent_reference':prep['archive_oracle']}))
        old=load('_043_historical_fixtures',OLD/'test_controls.py')
        for spec in plan['budget_cases']:
            a,b=old.problem(spec['kind']);arms={}
            for arm,k in kernels.items():
                row=call(k,a,b,prepaid=spec['prepaid']);arms[arm]=row
                save(out/'raw'/f'{spec["kind"]}_prepaid_{spec["prepaid"]}_{arm}.json',row)
                assert row['credit_valid'],row['credits']
                assert row['work']['work_units']<=k.MAX_WORK_UNITS and row['work']['narrow_phase_pairs']<=k.MAX_NARROW_PHASE_PAIRS
                if row['result']['measurement_valid']:
                    assert key_fraction(row['result']['_exact_distance_sq'])==3
                    witness=row['result'].get('exact_witness_triangles',{}).get('indices',row['result'].get('witness_triangle_indices'))
                    if witness:assert witness==plan['budget_analytic_truth']['canonical'][spec['kind']]
            assert not contained(a,b),'historical budget fixture unexpectedly activates candidate'
            assert binary(arms['B']['result'])==binary(arms['C']['result'])
            assert binary(arms['B']['work'])==binary(arms['C']['work'])
            refs.append(save(out/(spec['kind']+'_prepaid_'+str(spec['prepaid'])+'.json'),{'status':'pass','case':spec,'arms':arms,
                'analytical_distance_squared':'3','root_strict_containment':False,'original_status_differences':{
                    arm:{'valid':x['result']['measurement_valid'],'reason':x['result'].get('reason'),'witness':x['result'].get('witness_triangle_indices')} for arm,x in arms.items()}}))
            print(spec['kind']+' prepaid '+str(spec['prepaid'])+' pass',flush=True)
        controls=extra_controls(kernels,old,out)
        result['controls']=save(out/'EXTRA_CONTROLS.json',controls);result['status']='pass'
    except BaseException as exc:
        errors.append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        result.update(cost_wall_ns=time.perf_counter_ns()-started,cost_cpu_ns=time.process_time_ns()-cpu,completed_rows=len(refs))
        receipt=save(out/'RESULTS.json',result);print(json.dumps(receipt),flush=True)
    return result


def extra_controls(kernels,old,out):
    result={'status':'pass','limits':{},'deadlines':{},'shift':{}}
    a,b=old.problem('pair129')
    for arm,k in kernels.items():
        # Actual input admission failure, no patched cap.
        invalid=Mesh('invalid',[(0,0,0)],[(0,0,0)]*4096)
        value=k.measure_surface_proximity(invalid,Mesh('other',[(1,0,0)],[(0,0,0)]),lambda _:None)
        assert not value['measurement_valid'] and value['reason']=='surface_geometry_work_limit'
        forged={'witness_projection_credit_balance':1000000,'witness_projection_credit_node_units':1000000,
                'witness_projection_credit_spent_units':1000000,'witness_projection_tests':1000}
        fresh=call(k,a,b,diagnostics=forged)
        save(out/'extra_raw'/f'forged_diagnostics_{arm}.json',fresh)
        assert fresh['credit_valid'],fresh['credits']
        # Pair129 deliberately can hit the original pair cap. Unknown is retained,
        # not treated as failure of the independently checked fresh-query ledger.
        assert fresh['work']['witness_projection_credit_balance']<1000000
        # Original consume and narrow caps reject exactly before exceeding their real caps.
        work=k._Work(lambda _:None,{})
        work.consume(k.MAX_WORK_UNITS,'exact_limit')
        try:work.consume(1,'past_limit')
        except k._DomainError as exc:assert str(exc)=='surface_work_budget'
        else:raise AssertionError('work limit did not reject')
        work=k._Work(lambda _:None,{});work.counts['narrow_phase_pairs']=k.MAX_NARROW_PHASE_PAIRS
        try:work.narrow_pair()
        except k._DomainError as exc:assert str(exc)=='surface_pair_budget'
        else:raise AssertionError('narrow limit did not reject')
        result['limits'][arm]={'original_invalid':value,'fresh_forged_diagnostics':fresh}
        marker=RuntimeError('043 cooperative abort identity')
        def abort(stage):
            if stage=='surface_proximity_queue_pushes':raise marker
        try:call(k,a,b,checkpoint=abort)
        except BaseException as exc:assert exc is marker
        else:raise AssertionError('cooperative abort was swallowed')
        # The installed service also imports its pinned top-level operator modules.
        # Add this actual installation temporarily; the tested kernel stays under its arm alias.
        sys.path.insert(0,str(Path(k.__file__).parents[1]))
        try:service=importlib.import_module(k.__package__+'.live_service')
        finally:sys.path.pop(0)
        instance=object.__new__(service.LiveSpatialService)
        instance.request_budget_s=.025;receipt={}
        with instance._request_budget() as request:
            fixed=request['deadline'];receipt['deadline']=fixed
            def check(stage):
                if stage=='surface_proximity_queue_pushes':
                    remaining=fixed-time.monotonic()
                    if remaining>0:time.sleep(remaining+.001)
                    receipt['stage']=stage
                instance._check_request_budget(stage)
            try:call(k,a,b,checkpoint=check)
            except service.RequestBudgetError as exc:
                assert exc.code=='live_request_expired' and request['deadline']==fixed
                receipt.update(code=exc.code,expired=True,deadline_renewed=False)
            else:raise AssertionError('original deadline returned success')
        result['deadlines'][arm]=receipt
        # Public binary64 total spans cannot reach this 4097-bit priority branch.
        # Reuse original 031 prepared representation, but make all three root dimensions strictly containing.
        H=1<<4095;point=old.prepared_triangle
        prepared=([point(((0,0,0),)*3)]*17,[point(((1,0,0),)*3)]*128+
            [point(((-H,-H,-H),)*3)]*128+[point(((H,H,H),)*3)])
        work=k._Work(lambda _:None,{});roots=k._distance_roots(prepared,work)
        span=max(max(x,y)-min(z,w) for x,y,z,w in zip(roots[0][1],roots[1][1],roots[0][0],roots[1][0]))
        shift=max(0,span.bit_length()-(k.MAX_BITS-1));assert shift>0
        try:value=k._nearest_tree(prepared,roots,work,[]);outcome={'value':str(value)}
        except k._DomainError as exc:outcome={'domain_error':str(exc)}
        result['shift'][arm]={'shift':shift,'root_strict_containment':True,'outcome':outcome,'work':work.counts}
    assert binary(result['shift']['B'])==binary(result['shift']['C'])
    return result


def finish(prior_path,output):
    """Finish only the previously reached extra-control phase; do not rerun passed workloads."""
    out=Path(output).resolve();assert out.is_relative_to(RAW.resolve());out.mkdir(parents=True,exist_ok=False)
    prior_path=Path(prior_path);prior=json.loads(prior_path.read_bytes());runplan=read(prior['plan'])
    assert prior['completed_rows']==23 and len(prior['errors'])==1
    assert 'extra_controls' in prior['errors'][0]['traceback']
    for ref in prior['rows']:assert read(ref)['status']=='pass'
    for arm,site in runplan['sites'].items():
        assert pin(Path(site)/'human_eye_plugin/surface_proximity.py')==runplan['kernel_sources'][arm]
        binding=read(runplan['installation_bindings'][arm]['binding'])
        for ref in binding['source_files']:assert pin(Path(site)/ref['path'])['sha256']==ref['sha256']
    plan=save(out/'PLAN.json',{'prior_actual_case_results':pin(prior_path),'prior_test_source':pin(prior_path.parent/'SOURCE.py'),
        'unchanged_kernel_sources':runplan['kernel_sources'],'source':pin(__file__),
        'scope':'only remaining predeclared original cap, independent credit, deadline, and shifted guard controls',
        'known_statuses_not_required_to_be_success':True,'no_new_geometry':True})
    began=time.perf_counter_ns();cpu=time.process_time_ns();result={'status':'fail','plan':plan,'original_passed_case_count':23}
    try:
        kernels={arm:engine(arm,site) for arm,site in runplan['sites'].items()}
        old=load('_043_extra_historical_fixtures',OLD/'test_controls.py')
        result['controls']=save(out/'EXTRA_CONTROLS.json',extra_controls(kernels,old,out));result['status']='pass'
    except BaseException as exc:result['errors']=[{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}]
    result.update(cost_wall_ns=time.perf_counter_ns()-began,cost_cpu_ns=time.process_time_ns()-cpu,Blender=0,MCP=0,not_timing=True)
    receipt=save(out/'RESULTS.json',result);print(json.dumps(receipt));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','finish'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--candidate-site',type=Path);p.add_argument('--prior',type=Path);args=p.parse_args()
    if args.mode=='prepare':prepare(args.output)
    elif args.mode=='finish':sys.exit(0 if finish(args.prior,args.output)['status']=='pass' else 1)
    else:sys.exit(0 if run(args.prepared,args.output,args.candidate_site)['status']=='pass' else 1)
