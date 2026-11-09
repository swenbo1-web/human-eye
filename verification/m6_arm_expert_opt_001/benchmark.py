"""One light frozen-weight acceptance/cost pass; never trains or opens Blender."""
import os
for _name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_name]='1'

import argparse
import ast
import copy
from collections import defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback
import types

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE='ef84ecc59f107321225d0d832fde119ed0b91e3f'
DATA=ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz'
WEIGHTS=ROOT/'human_eye_plugin/arm_twist_weights.py'
PRODUCT=ROOT/'human_eye_plugin/arm_twist_expert.py'
CALLS=0


def sha(raw):return hashlib.sha256(raw).hexdigest()


def call(fn,*args,**kwargs):
    global CALLS
    CALLS+=1
    return fn(*args,**kwargs)


def static(patch):
    result=copy.deepcopy(patch);result.pop('current_vertices',None)
    for bone in result['bone_chain']:bone.pop('pose_matrix',None)
    return result


def poses(patch):return [bone['pose_matrix'] for bone in patch['bone_chain']]


@contextmanager
def tap(owner,name):
    original=getattr(owner,name);observations=[]
    def wrapped(*args,**kwargs):
        result=original(*args,**kwargs)
        observations.append((np.array(result[0],copy=True),copy.deepcopy(result[1])))
        return result
    setattr(owner,name,wrapped)
    try:yield observations
    finally:setattr(owner,name,original)


def features_equal(left,right):
    a,ca=left;b,cb=right
    assert ca['reason']==cb['reason'],(ca['reason'],cb['reason'])
    assert [list(s) for s in ca['sections']]==[list(s) for s in cb['sections']]
    assert list(ca['vertex_ids'])==list(cb['vertex_ids'])
    np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-14)
    return float(np.max(np.abs(a-b))) if a.size else 0.


def reports_equal(left,right):
    excluded={'regions','max_severity'}
    assert {k:v for k,v in left.items() if k not in excluded}=={k:v for k,v in right.items() if k not in excluded}
    assert len(left['regions'])==len(right['regions'])
    maximum=0.
    for a,b in zip(left['regions'],right['regions']):
        assert set(a)==set(b)
        assert {k:v for k,v in a.items() if k!='predicted_severity'}=={k:v for k,v in b.items() if k!='predicted_severity'}
        difference=abs(a['predicted_severity']-b['predicted_severity']);assert difference<=1e-11
        maximum=max(maximum,difference)
    assert ('max_severity' in left)==('max_severity' in right)
    if 'max_severity' in left:assert abs(left['max_severity']-right['max_severity'])<=1e-11
    return maximum


def geometry_report(scores,sections,ids,threshold):
    values=[None if not np.isfinite(v) else float(v) for v in scores]
    return dict(schema='indexed-section-area-baseline-v1',status='unknown' if None in values else 'observed',
        meaning='ordered_polygon_area_loss_not_constructed_damage',
        regions=[dict(section_index=i,vertex_ids=[ids[j] for j in section],
            severity=values[i],flagged=None if values[i] is None else values[i]>=threshold)
            for i,section in enumerate(sections)])


class PreparedGeometry:
    """Same scalar area baseline, with rest and section checks prepared once."""
    def __init__(self,patch,baseline):
        if not isinstance(patch,dict) or patch.get('schema')!='arm-twist-patch-v1':raise ValueError('geometry_baseline_patch_schema')
        rest=np.asarray(patch['rest_vertices'],dtype=np.float64)
        if rest.ndim!=2 or rest.shape[1:]!=(3,) or len(rest)<3 or not np.isfinite(rest).all():raise ValueError('geometry_baseline_vertex_correspondence')
        self.shape=rest.shape;self.sections=[];self.areas=[];self.resolved=[];self.baseline=baseline
        self.ids=tuple(patch['vertex_ids'])
        sections=patch['sections']
        if not isinstance(sections,(list,tuple)) or not sections:raise ValueError('geometry_baseline_sections')
        for section in sections:
            if (not isinstance(section,(list,tuple,np.ndarray)) or len(section)<3
                    or any(isinstance(i,(bool,np.bool_)) or not isinstance(i,(int,np.integer)) or not 0<=i<len(rest) for i in section)
                    or len(set(section))!=len(section)):raise ValueError('geometry_baseline_section_indices')
            indices=np.asarray(section,dtype=np.int64);area,error=baseline._area(rest[indices])
            self.sections.append(tuple(int(i) for i in indices));self.areas.append(area)
            self.resolved.append(np.isfinite(area) and area>error)

    def predict(self,current,threshold):
        current=np.asarray(current,dtype=np.float64)
        if current.shape!=self.shape or not np.isfinite(current).all():raise ValueError('geometry_baseline_vertex_correspondence')
        values=[]
        for section,area,resolved in zip(self.sections,self.areas,self.resolved):
            value,_=self.baseline._area(current[list(section)])
            values.append(max(0.,1-value/area) if resolved and np.isfinite(value) else np.nan)
        return geometry_report(values,self.sections,self.ids,threshold)


def samples(values):
    return dict(calls=len(values),samples_ns=values,median_ns=statistics.median(values),
                p95_ns=float(np.percentile(values,95)),scope='single light pass over specified saved inputs; no stable performance-generalization claim')


def run(output):
    output=Path(output).resolve()
    assert output.is_relative_to(HERE.resolve()) and output!=HERE.resolve()
    output.mkdir(parents=True,exist_ok=False)
    log=[];result={};before={str(p):sha(p.read_bytes()) for p in (WEIGHTS,DATA,PRODUCT)}
    def note(text):log.append(text);print(text,flush=True)
    try:
        sys.path.insert(0,str(ROOT))
        # Freeze only the old module in memory, not a second archived product.
        old_bytes=subprocess.run(['git','show',BASE+':human_eye_plugin/arm_twist_expert.py'],cwd=ROOT,
            check=True,capture_output=True).stdout
        old=types.ModuleType('human_eye_plugin._frozen_arm_expert_ef84ecc')
        old.__file__='<git:'+BASE+':human_eye_plugin/arm_twist_expert.py>';old.__package__='human_eye_plugin'
        sys.modules[old.__name__]=old;exec(compile(old_bytes,old.__file__,'exec'),old.__dict__)
        new=importlib.import_module('human_eye_plugin.arm_twist_expert')
        baseline=importlib.import_module('verification.m6_arm_expert_001.geometry_baseline')
        assert old.FEATURE_NAMES==new.FEATURE_NAMES and old.FLAG_THRESHOLD==new.FLAG_THRESHOLD
        raw=gzip.decompress(DATA.read_bytes());cases=json.loads(raw)
        assignment=next(n for n in ast.parse(WEIGHTS.read_bytes()).body if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id=='PARAMETERS' for t in n.targets))
        parameters=ast.literal_eval(assignment.value)
        assert sha(raw)==parameters['training']['dataset_sha256']
        assert len(cases)==77
        assets=defaultdict(list)
        for case in cases:assets[case['metadata']['asset_id']].append(case['packet'])
        assert len(assets)==11 and all(len(rows)==7 for rows in assets.values())
        for rows in assets.values():
            signature=static(rows[0])
            assert all(static(p)==signature for p in rows)
        cold={};models={}
        for name,module in (('old',old),('new',new)):
            module.get_default_expert.cache_clear();sys.modules.pop('human_eye_plugin.arm_twist_weights',None)
            start=time.perf_counter_ns();models[name]=call(module.get_default_expert)
            cold[name]=time.perf_counter_ns()-start
        note('Loaded frozen tensors separately; no training. Cold means Python import/tensor construction, not cleared OS filesystem cache.')
        prepared={name:call(new.prepare_patch,static(rows[0])) for name,rows in assets.items()}
        max_feature=max_score=0.;parity=[]
        with tap(old,'extract_features') as old_features,tap(new.PreparedArmPatch,'_features') as new_features:
            for case in cases:
                patch=case['packet'];prep=prepared[case['metadata']['asset_id']]
                a=call(old.analyze,patch);fa=old_features[-1]
                b=call(new.analyze,patch);fb=new_features[-1]
                c=call(prep.analyze,patch['current_vertices'],poses(patch),model=models['new']);fc=new_features[-1]
                max_feature=max(max_feature,features_equal(fa,fb),features_equal(fa,fc))
                max_score=max(max_score,reports_equal(a,b),reports_equal(a,c))
                parity.append(dict(case_id=case['metadata']['case_id'],asset_id=case['metadata']['asset_id'],
                    section_count=len(a['regions']),status=a['status'],reason=a['reason']))
        note('All 77 raw and prepared full reports, features, flags, order and global vertex IDs matched old source; 11 static preparations across seven poses each.')
        heldout=[c['packet'] for c in cases if c['metadata']['split']=='test']
        variants=[]
        ragged=copy.deepcopy(heldout[0])
        for i,section in enumerate(ragged['sections']):
            if i%2:ragged['triangles'].append([section[-2],section[-1],section[0]]);section.pop()
        variants.append(('mixed_section_lengths',ragged))
        reordered=copy.deepcopy(ragged);reordered['sections']=reordered['sections'][::2]+reordered['sections'][1::2]
        reordered['vertex_ids']=[10**9+7*i for i in range(len(reordered['vertex_ids']))]
        variants.append(('mixed_lengths_original_order_and_global_IDs',reordered))
        collapsed=copy.deepcopy(heldout[0])
        for section in collapsed['sections']:
            center=np.asarray([collapsed['current_vertices'][i] for i in section]).mean(axis=0).tolist()
            for i in section:collapsed['current_vertices'][i]=center[:]
        variants.append(('collapsed_current',collapsed))
        nonplanar=copy.deepcopy(heldout[0]);nonplanar['current_vertices'][0][0]+=.1
        variants.append(('nonplanar_current',nonplanar))
        degenerate=copy.deepcopy(heldout[0])
        for i in degenerate['sections'][0]:degenerate['rest_vertices'][i]=degenerate['rest_vertices'][0][:]
        variants.append(('degenerate_rest',degenerate))
        extreme=copy.deepcopy(heldout[0])
        extreme['rest_vertices']=[[v*1e155 for v in p] for p in extreme['rest_vertices']]
        variants.append(('finite_extreme_centerline_short_circuit',extreme))
        extreme_branch=copy.deepcopy(extreme)
        parent,child=extreme_branch['bone_chain'][:2]
        relative=new.rig_pose.multiply(new.rig_pose.inverse(parent['rest_matrix']),child['rest_matrix'])
        half_turn=[[-1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,-1.,0.],[0.,0.,0.,1.]]
        child['pose_matrix']=new.rig_pose.multiply(parent['pose_matrix'],new.rig_pose.multiply(relative,half_turn))
        variants.append(('finite_extreme_angle_short_circuit',extreme_branch))
        checks={}
        for name,patch in variants:
            a=call(old.analyze,patch);b=call(new.analyze,patch)
            prep=call(new.prepare_patch,static(patch));c=call(models['new'].predict_prepared,prep,patch['current_vertices'],poses(patch))
            max_score=max(max_score,reports_equal(a,b),reports_equal(a,c))
            checks[name]=dict(status=a['status'],reason=a['reason'],sections=len(a['regions']))
        for name,patch in [('duplicate_IDs',copy.deepcopy(heldout[0])),('bad_weights',copy.deepcopy(heldout[0])),('bad_pose',copy.deepcopy(heldout[0]))]:
            if name=='duplicate_IDs':patch['vertex_ids'][1]=patch['vertex_ids'][0]
            elif name=='bad_weights':patch['weights'][0][0]=2.
            else:patch['bone_chain'][1]['pose_matrix'][0][0]=2.
            errors=[]
            for module in (old,new):
                try:call(module.analyze,patch)
                except ValueError as exc:errors.append(str(exc))
            assert len(errors)==2 and errors[0]==errors[1],(name,errors)
            checks[name]=dict(error=errors[0])
        first_rows=next(iter(assets.values()));first=first_rows[0]
        isolated={}
        prep=prepared[next(iter(assets))]
        base_features,_=call(prep.extract_features,first['current_vertices'],poses(first))
        base_report=call(prep.analyze,first['current_vertices'],poses(first),model=models['new'])
        for field in ('current_only','pose_only'):
            feature_changes=[];score_changes=[]
            for p in first_rows[1:]:
                current=p['current_vertices'] if field=='current_only' else first['current_vertices']
                pose=poses(p) if field=='pose_only' else poses(first)
                f,context=call(prep.extract_features,current,pose);r=call(prep.analyze,current,pose,model=models['new'])
                assert context['reason'] is None
                feature_changes.append(float(np.max(np.abs(f-base_features))))
                score_changes.append(max(abs(a['predicted_severity']-b['predicted_severity']) for a,b in zip(base_report['regions'],r['regions'])))
            assert max(feature_changes)>1e-6 and max(score_changes)>1e-6
            isolated[field]=dict(max_feature_change=max(feature_changes),max_severity_change=max(score_changes))
        mutable=static(first);detached=call(new.prepare_patch,mutable)
        a=call(detached.analyze,first['current_vertices'],poses(first),model=models['new'])
        mutable['rest_vertices'][0][0]+=100;mutable['weights'][0][0]=2;mutable['sections'][0][0]=mutable['sections'][0][1]
        mutable['vertex_ids'][0]+=999;mutable['triangles'].clear();mutable['bone_chain'][0]['rest_matrix'][0][0]=99
        reports_equal(a,call(detached.analyze,first['current_vertices'],poses(first),model=models['new']))
        try:call(new.prepare_patch,mutable)
        except ValueError:checks['changed_structure_requires_new_preparation']='rejected_invalid_changed_structure'
        else:raise AssertionError('invalid_mutated_structure_accepted')
        changed=copy.deepcopy(reordered);fresh_prepared=call(new.prepare_patch,static(changed))
        reports_equal(call(old.analyze,changed),call(fresh_prepared.analyze,changed['current_vertices'],poses(changed),model=models['new']))
        measurements=defaultdict(list)
        def timed(label,fn):
            start=time.perf_counter_ns();value=call(fn);measurements[label].append(time.perf_counter_ns()-start);return value
        geometry_prepared={name:call(PreparedGeometry,static(rows[0]),baseline) for name,rows in assets.items()}
        for p in heldout:
            asset=next(c['metadata']['asset_id'] for c in cases if c['packet'] is p)
            prep=prepared[asset];geo=geometry_prepared[asset];s=static(p);pose=poses(p)
            timed('old_full_raw_to_report',lambda:old.analyze(p))
            timed('new_full_raw_to_report',lambda:new.analyze(p))
            timed('new_static_prepare',lambda:new.prepare_patch(s))
            timed('new_prepared_dynamic_to_report',lambda:models['new'].predict_prepared(prep,p['current_vertices'],pose))
            rawgeo=timed('geometry_raw_to_indexed_report',lambda:geometry_report(baseline.predict(p),p['sections'],p['vertex_ids'],new.FLAG_THRESHOLD))
            timed('geometry_static_prepare',lambda:PreparedGeometry(s,baseline))
            hotgeo=timed('geometry_prepared_dynamic_to_indexed_report',lambda:geo.predict(p['current_vertices'],new.FLAG_THRESHOLD))
            assert rawgeo==hotgeo
        sequences={}
        for asset,rows in assets.items():
            if not asset.startswith('test/'):continue
            def old_sequence():return [call(old.analyze,p) for p in rows]
            def new_sequence():
                prep=call(new.prepare_patch,static(rows[0]))
                return [call(prep.analyze,p['current_vertices'],poses(p),model=models['new']) for p in rows]
            def geometry_sequence():
                prep=call(PreparedGeometry,static(rows[0]),baseline)
                return [call(prep.predict,p['current_vertices'],new.FLAG_THRESHOLD) for p in rows]
            values={}
            for label,fn in (('old_full_raw_seven_poses',old_sequence),('new_prepare_plus_seven_poses',new_sequence),('geometry_prepare_plus_seven_poses',geometry_sequence)):
                start=time.perf_counter_ns();fn();values[label]=time.perf_counter_ns()-start
            sequences[asset]=values
        note('Timed 14 held-out saved poses once per full/prepared mode and two complete seven-pose asset sequences; geometric baseline received the same preparation opportunity.')
        result=dict(status='passed',frozen_old_commit=BASE,frozen_old_source_sha256=sha(old_bytes),
            current_product_sha256=before[str(PRODUCT)],weights_sha256=before[str(WEIGHTS)],
            dataset_compressed_sha256=before[str(DATA)],dataset_raw_sha256=sha(raw),
            saved_cases=77,assets_prepared=11,poses_per_asset=7,parity=parity,
            max_feature_abs_difference=max_feature,max_severity_abs_difference=max_score,
            flags_sections_global_IDs_equal=True,extra_acceptance=checks,isolated_dynamic_changes=isolated,
            static_input_mutation_isolated=True,cold_weight_load_ns=cold,
            cold_scope='Fresh Python weights-module import plus tensor construction per variant; shared OS filesystem cache not flushed.',
            timing={label:samples(values) for label,values in measurements.items()},seven_pose_sequences=sequences,
            geometry_comparison_scope='Both raw and equally prepared variants produce complete indexed severity reports. Geometry baseline validates its own rest/current/sections contract, not the model rig contract; no capability-superiority claim.',
            timing_scope='Input is the already decoded complete Python patch. Dataset IO/decompression excluded for both. Pure network-only time is never substituted for full report time. Required returned copies remain included.',
            logical_calls=CALLS,training_calls=0,blender_calls=0,GPU_calls=0,external_API_calls=0,
            thread_settings={name:os.environ[name] for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        assert CALLS<700,'light_call_count_exceeded'
    except BaseException as exc:
        result=dict(status='failed',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),logical_calls=CALLS)
        note(result['traceback'])
    finally:
        after={str(p):sha(p.read_bytes()) for p in (WEIGHTS,DATA,PRODUCT)}
        result['input_sha256_before']=before;result['input_sha256_after']=after
        result['weights_dataset_and_product_unchanged']=before==after
        result['benchmark_source_sha256']=sha(Path(__file__).read_bytes())
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8',newline='\n')
        (output/'log.txt').write_text('\n'.join(log)+'\n',encoding='utf8',newline='\n')
    assert result['weights_dataset_and_product_unchanged']
    if result['status']!='passed':raise RuntimeError('benchmark_acceptance_failed:'+str(output/'result.json'))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    result=run(parser.parse_args().out)
    print(json.dumps({k:result[k] for k in ('status','logical_calls','max_feature_abs_difference','max_severity_abs_difference','timing')},indent=2))
