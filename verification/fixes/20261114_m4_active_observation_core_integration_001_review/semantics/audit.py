"""Independent static AST and sealed-result checks. No product imports."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
BATCH = ROOT / 'verification/m4_active_observation_core_integration_001'
checks = []
def check(label, condition, detail=None):
    checks.append({'check':label, 'passed':bool(condition), 'detail':detail})
def read(path): return json.loads(path.read_bytes())
def parse(path): return ast.parse(path.read_text(encoding='utf8'))
def named(tree, name): return copy.deepcopy(next(n for n in tree.body if getattr(n,'name',None)==name))
def dump(node): return ast.dump(node, include_attributes=False)
class StripDocs(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str): return None
        return self.generic_visit(node)
class StripCounters(StripDocs):
    def root(self,node):
        while isinstance(node,(ast.Subscript,ast.Attribute)): node=node.value
        return node.id if isinstance(node,ast.Name) else None
    def visit_Assign(self,node):
        if all(self.root(x) in ('work','stats') for x in node.targets): return None
        return self.generic_visit(node)
    def visit_AugAssign(self,node):
        if self.root(node.target) in ('work','stats'): return None
        return self.generic_visit(node)
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and self.root(node.value.func) in ('work','stats'): return None
        return super().visit_Expr(node)
    def visit_Call(self,node):
        node=self.generic_visit(node)
        node.args=[x for x in node.args if not(isinstance(x,ast.Name) and x.id in ('work','stats'))]
        return node
    def visit_arguments(self,node):
        node.args=[x for x in node.args if x.arg not in ('work','stats')]
        return self.generic_visit(node)
    def visit_For(self,node):
        node=self.generic_visit(node)
        return node if node.body else None
    def visit_If(self,node):
        if (isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name)
                and node.test.left.id=='variant' and isinstance(node.test.ops[0],ast.Eq)
                and isinstance(node.test.comparators[0],ast.Constant) and node.test.comparators[0].value=='optimized'):
            result=[]
            for x in node.body:
                y=self.visit(x)
                if y is not None: result.extend(y if isinstance(y,list) else [y])
            return result
        return self.generic_visit(node)

core_path=ROOT/'human_eye_plugin/active_observation.py'
image_path=ROOT/'human_eye_plugin/active_observation_images.py'
core=parse(core_path)
old=parse(BATCH/'baseline/m4_active_coverage_001/coverage.py')
discovery=parse(BATCH/'baseline/m4_triangulation_invariant_discovery_001/discovery.py')
check('fixed_author_HEAD', subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()=='cd863183b18e35d2ca38f75c0756e1c46e1a1ccb')
check('fixed_core_SHA', hashlib.sha256(core_path.read_bytes()).hexdigest()=='b99871b94ef74b9e92d422b09fabe4e32024a2a099a3e77d4248b94ff588f652')
for name in ('vector','subtract','dot','cross','fingerprint','canonical_triangle','Region','Triangle','geometry','signed_area','clip_halfspace','clip_convex','screen_basis','bounds','bounds_overlap','camera_planes','plane_distances','inside_frustum','CoverageState'):
    check('AST_unchanged_'+name,dump(StripDocs().visit(named(core,name)))==dump(StripDocs().visit(named(old,name))))
for name in ('project','triangle_shadow'):
    check('AST_counter_removal_'+name,dump(StripDocs().visit(named(core,name)))==dump(StripCounters().visit(named(old,name))))
for oldname,newname in (('_candidate_area','_oriented_triangle_area'),('_rectangle_boundary','_rectangle_boundary')):
    before=StripCounters().visit(named(discovery,oldname)); before.name=newname
    check('AST_discovery_'+newname,dump(before)==dump(StripDocs().visit(named(core,newname))))
before=StripCounters().visit(named(discovery,'_topology'))
class InlinePoint(ast.NodeTransformer):
    def visit_Assign(self,node):
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='point': return None
        return self.generic_visit(node)
    def visit_Name(self,node):
        if node.id=='point': return ast.Subscript(value=ast.Name(id='vertices',ctx=ast.Load()),slice=ast.Name(id='vertex_index',ctx=ast.Load()),ctx=ast.Load())
        return node
before=InlinePoint().visit(before)
check('AST_topology_counter_removal_and_point_inline',dump(before)==dump(StripDocs().visit(named(core,'_topology'))))
before=StripCounters().visit(named(old,'build_index'))
after=named(core,'build_index_from_parsed')
before_loop=next(n for n in before.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='pose')
after_loop=next(n for n in after.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='pose')
check('AST_full_coverage_loop_is_static_optimized_without_counters',dump(before_loop)==dump(after_loop))
def assignment(fn,var): return next(n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id==var for x in n.targets))
check('AST_candidate_identity_retained',dump(assignment(before,'candidate_identity'))==dump(assignment(after,'candidate_identity')))
prepare=named(core,'prepare_scene')
check('one_geometry_normalization_call_in_prepare',sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='geometry' for n in ast.walk(prepare))==1)
check('no_geometry_calls_in_discovery_or_coverage',all(not(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='geometry' for n in ast.walk(named(core,name)))) for name in ('regions_from_objects','build_index_from_parsed')))
check('default_core_has_no_work_or_bitlength',not any(isinstance(n,ast.Name) and n.id=='work' or isinstance(n,ast.Attribute) and n.attr=='bit_length' for n in ast.walk(core)))
check('no_dynamic_verification_runtime_in_core',all(value not in core_path.read_text(encoding='utf8') for value in ('verification','FunctionType','sys.path','spec_from_file_location')))
check('diagnostics_only_opt_in_clocks_and_aggregate',all(isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='diagnostics' for n in prepare.body if any(isinstance(x,ast.Attribute) and x.attr=='perf_counter_ns' for x in ast.walk(n))))

# These checks examine source qualification outputs independently of author COMPARISON booleans.
expected=read(BATCH/'admin/OLD_SELECTED.json')
baseline_git='b638c499c049604902415965f500f50a9947d34f'
def baseline_blob(rel):return subprocess.check_output(['git','show',baseline_git+':'+rel],cwd=ROOT)
for rel in ('m4_active_coverage_001/coverage.py','m4_triangulation_invariant_discovery_001/discovery.py'):
    check('baseline_git_source_'+rel,(BATCH/'baseline'/rel).read_bytes()==baseline_blob('verification/'+rel))
old_result=json.loads(baseline_blob('verification/m4_triangulation_invariant_discovery_001/runs/correctness/RESULTS.json'))
for row in old_result['rows']:
    if row['variant']!='candidate':continue
    if 'scene' in row:check('selected_source_from_fixed_git_'+row['scene'],expected['scenes'][row['scene']]==row['index'])
    else:check('selected_source_from_fixed_git_'+row['control'],expected['controls'][row['control']]==row['regions'])
for ident,wanted in expected['replays'].items():
    previous=json.loads(baseline_blob('verification/m4_triangulation_invariant_discovery_001/runs/observe_'+ident+'/RESULTS.json'))
    check('replay_expected_from_fixed_git_'+ident,wanted=={'final_state':previous['final_state'],'steps':previous['steps'],'pixel_rows_by_view':{name:frame['pixel_rows'] for name,frame in previous['frames'].items()}})
semantic_keys=('scene_identity','candidate_identity','regions','view_order','view_masks','classifications')
qualifications=[]
for label,rel in (('source','runs/source_qualification/QUALIFICATION.json'),('installed','external/run/qualify_r2/QUALIFICATION.json')):
    q=read(BATCH/rel);qualifications.append(q)
    expected_rep={(scene,diag) for scene in expected['scenes'] for diag in (False,True)}
    keys=[(r['scene'],r['diagnostics_enabled']) for r in q['representations']]
    check(label+'_ten_distinct_representation_modes',set(keys)==expected_rep and len(keys)==10)
    for row in q['representations']:
        key=f"{label}_{row['scene']}_{row['diagnostics_enabled']}"
        check(key+'_exact_index',row['index']=={k:expected['scenes'][row['scene']][k] for k in semantic_keys})
        check(key+'_diagnostic_mode',(row['diagnostics'] is not None)==row['diagnostics_enabled'])
        idx=row['index'];ids=[r['roi_id'] for r in idx['regions']]
        for view in idx['view_order']:
            mask=sum(1<<i for i,rid in enumerate(ids) if idx['classifications'][view][rid]['complete'])
            check(key+'_'+view+'_mask_from_classification',mask==idx['view_masks'][view])
    keys=[(r['control'],r['diagnostics_enabled']) for r in q['controls']]
    check(label+'_four_distinct_control_modes',len(keys)==4 and set(keys)=={(name,diag) for name in expected['controls'] for diag in (False,True)})
    for row in q['controls']:check(label+'_'+row['control']+'_'+str(row['diagnostics_enabled'])+'_control_ROIs',row['regions']==expected['controls'][row['control']])
    check(label+'_historical_frame_denominator',q['historical_frame_count']==8 and q['new_renders']==0 and len(q['offline_replays'])==4)
    for replay in q['offline_replays']:
        want=expected['replays'][replay['id']]
        check(label+'_'+replay['id']+'_replay_state',replay['summary']==want['final_state'])
        check(label+'_'+replay['id']+'_two_replay_frames',len(replay['steps'])==len(want['steps'])==2 and replay['historical_frames_read']==2 and replay['new_renders']==0)
        for actual,original in zip(replay['steps'],want['steps']):
            check(label+'_'+replay['id']+'_'+original['view']+'_update',actual['update']==original['update'])
        facts=replay['facts'];summary=replay['summary'];covered=set(summary['covered_roi_ids']);unavailable=set(summary['candidate_pool_uncovered_roi_ids'])
        check(label+'_'+replay['id']+'_facts_scope',facts['image_delivery_scope']=='local_core_validation' and facts['coverage']==summary)
        check(label+'_'+replay['id']+'_facts_object_and_reason',all(r['object_name'] and r['status']==('covered' if r['roi_id'] in covered else 'unknown') and r['reason']==('observed_readable' if r['roi_id'] in covered else 'finite_camera_pool_uncovered' if r['roi_id'] in unavailable else 'pixel_evidence_insufficient') for r in facts['regions']))
        check(label+'_'+replay['id']+'_facts_minimal_payload', 'triangle_indices' not in json.dumps(facts) and [r['view_name'] for r in facts['observations']]==summary['observed_views'])
    change=q['repeat_and_invalidation_case']
    check(label+'_reported_identity_changes',change['initial_identity']!=change['final_identity'] and change['final_summary']['state_updates']==0 and change['final_summary']['observed_views']==[] and change['final_summary']['covered_roi_ids']==[])

# Source/installed exact semantic output comparison independent of phase timings and file locations.
def indexes(q):return {(r['scene'],r['diagnostics_enabled']):r['index'] for r in q['representations']}
check('source_installed_same_semantic_indexes',indexes(qualifications[0])==indexes(qualifications[1]))
check('source_installed_same_controls',qualifications[0]['controls']==qualifications[1]['controls'])

result={'schema':'independent-core-integration-semantics-v1','author_commit':'cd863183b18e35d2ca38f75c0756e1c46e1a1ccb','review_method':'AST normalization and direct sealed JSON comparison; no product import/execution, model, raster, Blender or benchmark','check_count':len(checks),'passed':all(r['passed'] for r in checks),'checks':checks,'source_sha256':hashlib.sha256(core_path.read_bytes()).hexdigest(),'scope_limits':['Exact single-object connected planar rectangles only','scene identity excludes names/host metadata and is order-independent','short facts list supported discovered ROIs, not domain exits','dynamic API execution was not repeated'],'audit_correction':{'first_run':'AST normalizer AssertionError: matched legacy variant not-in validation as if it were optimized branch','fix':'Restrict branch selection to exact Eq optimized; leave validation AST untouched','product_calls':0,'benchmark_calls':0,'new_rasters':0}}
(HERE/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'check_count':len(checks),'passed':result['passed'],'failed':[r['check'] for r in checks if not r['passed']]},ensure_ascii=False))
