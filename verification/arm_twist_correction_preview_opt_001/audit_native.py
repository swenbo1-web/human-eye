"""Independent stdlib-only audit of existing source-to-preview native artifacts.

No producer/oracle import, preview call, normalization output, model, or Blender
run occurs here. Weight divisions only compare the existing source export.
"""
import ast
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NATIVE=HERE/'native_01'
GATES={'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5}
CASES=(('round_120','candidate',120.,120.),('round_minus150','candidate',-150.,-150.),
       ('elliptic_120','candidate',120.,120.),('elliptic_minus150','candidate',-150.,-150.),
       ('balanced_120','no_op',120.,60.),('small_twist_30','no_op',30.,30.),
       ('unreachable_120','unreachable',120.,120.),('noncoaxial','not_applicable',None,None))
REASONS={'candidate':'area_target_met_with_fixed_end_poses','no_op':'area_target_already_met',
         'unreachable':'best_allowed_u_exceeds_area_target','not_applicable':'non_axial_or_ambiguous_pose'}
checks=0


def require(value,reason):
    global checks
    checks+=1
    if not value:raise AssertionError(reason)


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def distance(a,b):return norm(sub(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def center(points,section):return [math.fsum(points[i][k] for i in section)/len(section) for k in range(3)]
def matrix_error(a,b):return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))
def multiply(a,b):return [[math.fsum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def transform(matrix,point):return [dot(row,point+[1.]) for row in matrix[:3]]


def inverse4(matrix):
    rows=[list(row)+[float(i==j) for j in range(4)] for i,row in enumerate(matrix)]
    for column in range(4):
        pivot=max(range(column,4),key=lambda row:abs(rows[row][column]));rows[column],rows[pivot]=rows[pivot],rows[column]
        divisor=rows[column][column];require(abs(divisor)>1e-14,'native matrix nonsingular')
        rows[column]=[v/divisor for v in rows[column]]
        for row in range(4):
            if row!=column:
                factor=rows[row][column];rows[row]=[v-factor*w for v,w in zip(rows[row],rows[column])]
    return [row[4:] for row in rows]


def area_vector(points,section):
    anchor=points[section[0]]
    triangles=[cross(sub(points[section[i]],anchor),sub(points[section[i+1]],anchor)) for i in range(1,len(section)-1)]
    return [.5*math.fsum(v[k] for v in triangles) for k in range(3)]


def areas(points,sections):
    result=[norm(area_vector(points,s)) for s in sections]
    require(all(v>0 and math.isfinite(v) for v in result),'positive finite independent 3D areas')
    return result


def frame(matrix):
    def unit(a):
        length=norm(a);require(length>0,'native frame nonzero column');return [v/length for v in a]
    x=unit([matrix[k][0] for k in range(3)]);raw_y=[matrix[k][1] for k in range(3)]
    projection=dot(x,raw_y);y=unit([raw_y[k]-projection*x[k] for k in range(3)]);z=cross(x,y)
    require(dot(z,[matrix[k][2] for k in range(3)])>0,'proper native frame')
    return x,y,z


def angle_error(a,b):
    a,b=frame(a),frame(b);m=[[dot(x,y) for y in b] for x in a]
    sine=.5*norm([m[2][1]-m[1][2],m[0][2]-m[2][0],m[1][0]-m[0][1]])
    return math.degrees(math.atan2(sine,.5*(math.fsum(m[k][k] for k in range(3))-1)))


def lbs_points(rest,weights,rests,poses):
    maps=[multiply(p,inverse4(r)) for r,p in zip(rests,poses)];result=[]
    for point,row in zip(rest,weights):
        values=[transform(matrix,point) for matrix in maps]
        result.append([math.fsum(w*v[k] for w,v in zip(row,values)) for k in range(3)])
    return result


def canonical(face):
    start=face.index(min(face));return tuple(face[start:]+face[:start])


def independent_floor(packet,optimal,theta):
    # Independent matrix arithmetic and triangle-fan area normals. This repeats
    # the reviewed certificate mathematics, without importing its implementation.
    rests=[b['rest_matrix'] for b in packet['bone_chain']];poses=[b['pose_matrix'] for b in packet['bone_chain']]
    inverses=[inverse4(r) for r in rests];pinv=inverse4(poses[0]);a=poses[0]
    cols=[[a[k][i] for k in range(3)] for i in range(3)]
    cof=[cross(cols[1],cols[2]),cross(cols[2],cols[0]),cross(cols[0],cols[1])]
    c=math.sqrt(1+max(math.fsum(abs(dot(cof[i],cof[j])-float(i==j)) for j in range(3)) for i in range(3)))
    def inverse_residual(x,y):
        return math.sqrt(math.fsum((math.fsum(x[i][k]*y[k][j] for k in range(3))-float(i==j))**2 for i in range(3) for j in range(3)))
    residual=max([inverse_residual(a,pinv)]+[inverse_residual(r,i) for r,i in zip(rests,inverses)]+[inverse_residual(i,r) for r,i in zip(rests,inverses)])
    last=multiply(multiply(pinv,poses[2]),multiply(inverses[2],rests[0]))
    radians=math.radians(theta);cy,sy=math.cos(radians),math.sin(radians)
    ideal=[[cy,0,sy],[0,1,0],[-sy,0,cy]]
    end_delta=math.sqrt(math.fsum((last[i][j]-ideal[i][j])**2 for i in range(3) for j in range(3)))
    local=[transform(inverses[0],point) for point in packet['rest_vertices']]
    base=areas(packet['rest_vertices'],packet['sections']);coordinate=max(abs(v) for p in packet['rest_vertices']+packet['current_vertices'] for v in p)
    errors=[]
    for joint,pattern in enumerate(([.5,.5,0.],[0.,.5,.5])):
        section=next(s for s in packet['sections'] if all(packet['weights'][i]==pattern for i in s))
        number=packet['sections'].index(section);area0=base[number];mid=center(local,section)
        ring=[sub(local[i],mid) for i in section];vector=[v/area0 for v in area_vector(local,section)]
        cross_edges=[cross(p,q) for p,q in zip(ring,ring[1:]+ring[:1])]
        radius=max(norm(p) for p in ring);perimeter=math.fsum(distance(p,q) for p,q in zip(ring,ring[1:]+ring[:1]))
        condition=max(1.,math.fsum(norm(p) for p in cross_edges)/(2*area0),len(ring)*radius*radius/(2*area0),coordinate*perimeter/area0)
        e=4*residual+(end_delta/2 if joint else 0.);g=math.sqrt(3)*(2*e+e*e)
        errors.append(max(0.,c*abs(vector[1])-1)+c*math.hypot(vector[0],vector[2])+c*g*norm(vector)+max(128,8*len(ring))*2.220446049250313e-16*condition)
    ideal_loss=max(math.sin(math.radians(optimal)/2)**2,math.sin(math.radians(theta-optimal)/2)**2)
    return max(0.,ideal_loss-max(errors))


def main():
    result=read(NATIVE/'RESULT.json');frozen=read(NATIVE/'SOURCE_FREEZE.json');cpu=read(HERE/'cpu_02/RESULT.json')
    require(result['native_gates']==frozen['native_gates']==GATES,'unchanged native gates')
    require(result['source_hashes_before']==result['source_hashes_after']==frozen['files'],'source freeze before/after')
    for path,expected in frozen['files'].items():require(sha(ROOT/path)==expected,'frozen bytes '+path)
    identity=result['runtime_source_identity'];manifest=identity['source_files']
    identity_tree=ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_text(encoding='utf8'))
    constants={node.targets[0].id:ast.literal_eval(node.value) for node in identity_tree.body
               if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
               and node.targets[0].id in ('_ROOT_MODULES','BASE_VERSION','IMPLEMENTATION_REVISION')}
    enumerated=set(constants['_ROOT_MODULES'])
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        enumerated.update(package+'/'+path.name for path in (ROOT/package).glob('*.py'))
    require(sorted(enumerated)==[r['path'] for r in manifest],'independently complete runtime enumeration')
    require(constants['BASE_VERSION']==identity['base_version'] and constants['IMPLEMENTATION_REVISION']==identity['implementation_revision'],'version metadata from frozen source literals')
    require(len(manifest)==137 and [r['path'] for r in manifest]==frozen['runtime_source_files'],'137 canonical source paths')
    actual=[{'path':r['path'],'sha256':sha(ROOT/r['path'])} for r in manifest]
    require(actual==manifest,'runtime manifest bytes independently verified')
    source_hash=digest({'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':actual})
    require(source_hash==identity['source_sha256'] and identity['build_id']=='sha256:'+source_hash,'canonical build digest')
    require(frozen['product_setters']==frozen['qa_normalizers']==0,'no product setters or QA normalizer')
    require(len(result['cases'])==8,'fixed eight native tasks')
    input_hashes={str(p.relative_to(ROOT)):sha(p) for p in (NATIVE/'RESULT.json',NATIVE/'SOURCE_FREEZE.json',NATIVE/'process.json',NATIVE/'process_exit.json',NATIVE/'blender.log',HERE/'cpu_02/RESULT.json')}
    rows=[];instances=set();identity4=[[float(i==j) for j in range(4)] for i in range(4)]
    for index,(case_id,status,theta,current_u) in enumerate(CASES,1):
        path=NATIVE/('case_'+str(index).zfill(2)+'.json');raw=read(path);summary=result['cases'][index-1]
        input_hashes[str(path.relative_to(ROOT))]=sha(path)
        require(raw['case_id']==summary['case_id']==case_id and sha(path)==summary['raw_sha256'],'raw case binding '+case_id)
        patch,task,capture=raw['input_patch'],raw['input_task'],raw['capture'];preview=raw['preview']
        require(digest([patch,task])==raw['input_sha256'],'actual input packet/task hash')
        expected=read(path)['capture']['static_patch']
        expected['current_vertices']=capture['current_vertices']
        for bone,pose in zip(expected['bone_chain'],capture['pose_matrices']):bone['pose_matrix']=pose
        require(patch==expected,'full actual capture to preview input binding')
        require(preview['status']==status and preview['reason']==REASONS[status],'precise status and rejection reason')
        require(summary['expected_status']==summary['preview_status']==status and summary['preview_reason']==REASONS[status],'summary status binding')
        require(task['max_section_area_loss']==.4 and task['area_tolerance']==1e-6 and task['position_tolerance_m']==5e-6 and task['angle_tolerance_deg']==.001,'declared task and unchanged target')
        require(task['fixed_end_pose_matrices']==[capture['pose_matrices'][i] for i in (0,2)],'task fixed end targets from capture')
        src=capture['source'];require(src==summary['source_identity'] and src['epoch']==src['revision']==src['static_revision']==1,'source current epoch and summary')
        require(src['tracking']=='scene_residency' and src['frame']=={'number':1,'subframe':0.} and src['coordinate_frame']=='armature_local' and src['unit']=='m','source frame and unit')
        require(src['selection_key']==digest(raw['selection']) and src['selected_vertices']==402 and src['selected_bones']==raw['selection']['bone_names'],'selection source binding')
        require(src['instance_id'] not in instances,'distinct actual source host instance');instances.add(src['instance_id'])
        before,after=raw['native_before'],raw['native_after'];static=raw['native_static_before']
        require(static==raw['native_static_after'],'full static bookends exact')
        require(raw['sentinel_before']==raw['sentinel_after']==result['sentinel_before']==result['sentinel_after'],'full sentinel bookends exact')
        require(static['mesh_matrix_world']==static['rig_matrix_world']==identity4 and static['unit_scale_m']==1.,'identity fixture coordinate mapping')
        require(static['vertex_groups']==[{'index':i,'name':'arm_'+str(i)} for i in range(3)] and
                [b['name'] for b in static['bones']]==['arm_0','arm_1','arm_2'],'effective group columns bind selected deform bones')
        require(static['modifiers']==[{'type':'ARMATURE','object':raw['selection']['armature_name'],
            'use_deform_preserve_volume':False,'use_vertex_groups':True,'use_bone_envelopes':False}], 'declared native LBS modifier')
        require(patch['vertex_ids']==raw['selection']['vertex_indices']==list(range(402)) and len(patch['sections'])==25,'native vertex/section denominator')
        require(len(raw['logical_to_native_vertex_id_mapping'])==len({p[0] for p in raw['logical_to_native_vertex_id_mapping']})==402
                and [p[1] for p in raw['logical_to_native_vertex_id_mapping']]==patch['vertex_ids'],'logical native ID mapping')
        require(patch['rest_vertices']==static['rest_vertices'] and patch['current_vertices']==before['current_vertices'] and capture['pose_matrices']==before['pose_matrices'],'actual native coordinates and poses supplied unchanged')
        require(patch['sections']==raw['selection']['sections'],'actual section index mapping')
        require(sorted(canonical(t) for t in static['triangles'])==[tuple(t) for t in patch['triangles']],'all oriented native topology canonical mapping')
        require([b['rest_matrix'] for b in patch['bone_chain']]==[b['rest_matrix'] for b in static['bones']],'native rest matrix export')
        require(raw['raw_rna_weights']==static['raw_rna_weights'] and raw['source_exported_effective_weights']==patch['weights']==capture['static_patch']['weights'],'raw and effective exports unchanged')
        max_weight_delta=0.
        for rna,effective,raw_sum,effective_sum in zip(raw['raw_rna_weights'],patch['weights'],raw['raw_rna_weight_sums'],raw['source_effective_weight_sums']):
            total=math.fsum(rna)
            require(total==raw_sum and abs(total-1)<=1e-6 and total>0,'raw total accepted by existing source')
            require(all(e==r/total for r,e in zip(rna,effective)) and effective_sum==math.fsum(effective),'existing source effective-weight division semantics')
            max_weight_delta=max(max_weight_delta,max(abs(a-b) for a,b in zip(rna,effective)))
        sections=patch['sections'];base=areas(patch['rest_vertices'],sections)
        before_ratios=[a/b for a,b in zip(areas(before['current_vertices'],sections),base)]
        after_ratios=[a/b for a,b in zip(areas(after['current_vertices'],sections),base)]
        before_j=max(0.,1-min(before_ratios));after_j=max(0.,1-min(after_ratios))
        require(abs(before_j-raw['before_objective']['max_section_area_loss'])<1e-12 and abs(after_j-raw['after_objective']['max_section_area_loss'])<1e-12,'actual J independently recomputed')
        if theta is not None:
            initial_j=max(math.sin(math.radians(current_u)/2)**2,math.sin(math.radians(theta-current_u)/2)**2)
            expected_after=max(math.sin(math.radians(theta/2)/2)**2,math.sin(math.radians(theta/2)/2)**2) if status=='candidate' else initial_j
            require(abs(before_j-initial_j)<=GATES['section_area_loss'] and abs(after_j-expected_after)<=GATES['section_area_loss'],'actual 3D areas agree with independent analytic J')
        rests=[b['rest_matrix'] for b in patch['bone_chain']]
        before_lbs=lbs_points(patch['rest_vertices'],patch['weights'],rests,before['pose_matrices'])
        after_lbs=lbs_points(patch['rest_vertices'],patch['weights'],rests,after['pose_matrices'])
        lbs_delta=max(distance(a,b) for predicted,observed in ((before_lbs,before['current_vertices']),(after_lbs,after['current_vertices'])) for a,b in zip(predicted,observed))
        require(lbs_delta<=GATES['position_m'],'same-index native LBS independently verified')
        protected=raw['protected_vertex_ids'];pure=[v for v,w in zip(patch['vertex_ids'],patch['weights']) if w==[1.,0.,0.] or w==[0.,0.,1.]]
        require(protected==task['protected_vertex_ids']==pure and len(pure)==194,'all and only 194 pure-end protected IDs')
        require(raw['protected_points_before']==[before['current_vertices'][i] for i in pure] and raw['protected_points_after']==[after['current_vertices'][i] for i in pure],'full protected bookends bind native points')
        protection=max(distance(a,b) for a,b in zip(raw['protected_points_before'],raw['protected_points_after']))
        endpoint_matrix=max(matrix_error(before['global_pose_matrices'][i],after['global_pose_matrices'][i]) for i in (0,2))
        endpoint_angle=max(angle_error(before['global_pose_matrices'][i],after['global_pose_matrices'][i]) for i in (0,2))
        heads_tails=max(distance(a,b) for field in ('head_positions','tail_positions') for a,b in zip(before[field],after[field]))
        ring_centers=max(distance(center(before['current_vertices'],s),center(after['current_vertices'],s)) for s in sections)
        require(max(protection,heads_tails,ring_centers,endpoint_matrix)<=GATES['position_m'] and endpoint_angle<=GATES['angle_deg'],'native endpoints heads tails centers and protection')
        if status=='candidate':
            candidate=preview['candidate'];require(candidate is not None and summary['qa_candidate_pose_assignments']==2,'two QA candidate writes')
            require([c['name'] for c in candidate['bone_changes']]==['arm_1','arm_2'],'only middle/end changes')
            require(after_j<=task['max_section_area_loss']+GATES['section_area_loss'],'actual native target achieved')
            candidate_delta=max(distance(a,b) for a,b in zip(candidate['current_vertices'],after['current_vertices']))
            require(candidate_delta<=GATES['position_m'],'predicted candidate and actual native points')
            require(max(angle_error(a,b) for a,b in zip(candidate['pose_matrices'],after['pose_matrices']))<=GATES['angle_deg'],'all candidate native pose rotations')
            require(preview['work']['full_vertex_bone_transforms']==4,'four full vertex bone transforms')
        else:
            require(preview['candidate'] is None and summary['qa_candidate_pose_assignments']==0,'non-candidate zero QA writes')
            require(all(before[k]==after[k] for k in before if k!='elapsed_ns'),'full non-candidate native state unchanged')
        certificate=None
        if status=='unreachable':
            certificate=independent_floor(patch,preview['optimal_u_deg'],preview['theta_deg'])
            reported=preview['objective']['minimum_loss_lower_bound']
            require(abs(certificate-reported)<=2e-11 and reported>task['max_section_area_loss']+task['area_tolerance'],'independent cofactor infeasibility bound')
            require(preview['optimal_u_deg']==110. and preview['work']['infeasibility_section_bounds']==2,'fixed unreachable interval and two witness sections')
        require(summary['host_residency_closed'] and summary['handler_counts_before_host']==summary['handler_counts_after_close'],'per source handler cleanup')
        require(raw['source_work_totals']==summary['source_work_totals']=={'captures':1,'static_reads':1,'preparations':1,'rest_vertices':402,'weight_rows':402,'current_vertices':402,'rest_bones':3,'pose_bones':3,'topology_reads':1},'one actual source capture')
        rows.append({'case_id':case_id,'status':status,'reason':preview['reason'],'before_j':before_j,'actual_after_j':after_j,
            'source_epoch':src['epoch'],'source_current_rest_pose_exact':True,'raw_effective_max_weight_difference':max_weight_delta,
            'native_LBS_max_m':lbs_delta,'protected_max_m':protection,'endpoint_matrix_max_abs':endpoint_matrix,
            'endpoint_angle_deg':endpoint_angle,'heads_tails_max_m':heads_tails,'all_ring_centers_max_m':ring_centers,
            'static_sentinel_bookends_exact':True,'independent_infeasibility_floor':certificate,'raw_sha256':sha(path)})
    require(result['work']=={'fixtures_constructed':8,'source_captures':8,'preview_calls':8,'model_calls':0,'product_setters':0,'qa_initial_pose_assignments':24,'qa_candidate_pose_assignments':8,'native_readbacks':16},'actual source preview QA operation counts')
    require(cpu['passed'] and cpu['tests']==13 and cpu['inputs_sources_unchanged'],'CPU recorded regression result')
    for path,expected in cpu['before_sha256'].items():require(sha(Path(path))==expected and cpu['after_sha256'][path]==expected,'CPU/witness unchanged artifact '+path)
    witness=cpu['feasible_witness'];old_witness=read(Path(witness['original_FEASIBLE_WITNESS_path']))
    require(witness['u_deg']==old_witness['u_deg']==59.999999995 and witness['target_max_section_area_loss']==.250000000055 and witness['area_tolerance']==1e-12,'unchanged micro-weight witness task')
    require(cpu['root_details']['accepted_weight_slack']['epsilon']==5e-11 and cpu['root_details']['accepted_weight_slack']['status']=='not_applicable' and cpu['root_details']['accepted_weight_slack']['reason']=='non_adjacent_weights','tiny positive third influence explicitly rejected')
    u=witness['u_deg'];epsilon=5e-11
    real=(.5-epsilon)+.5*math.cos(math.radians(u))+epsilon*math.cos(math.radians(120.))
    imag=.5*math.sin(math.radians(u))+epsilon*math.sin(math.radians(120.))
    witness_j=max(1-real*real-imag*imag,math.sin(math.radians(120.-u)/2)**2)
    require(witness_j<=witness['target_max_section_area_loss']+witness['area_tolerance'] and abs(witness_j-witness['measured_max_section_area_loss'])<5e-15,'independent feasible witness remains feasible')
    require(cpu['old_failure_preserved']['failures']==1 and cpu['old_failure_preserved']['passed'] is False,'old failure retained')
    pg=cpu['precision_guard'];require(pg['status']=='not_applicable' and pg['reason']=='area_target_below_supported_precision' and pg['minimum_loss_lower_bound']<=pg['target_j']+pg['area_tolerance'],'near-boundary incomplete certificate does not claim infeasibility')
    require(result['handler_counts_before_all_fixtures']==result['handler_counts_after_all_fixtures'] and result['all_source_handlers_removed'],'all source handlers removed')
    require(all(result[k] for k in ('owned_objects_removed','owned_meshes_removed','owned_rigs_removed','source_bytes_unchanged','blend_file_still_unsaved')),'owned cleanup and zero save receipts')
    process=read(NATIVE/'process_exit.json');require(process['pid']==17732 and process['returncode']==0 and process['closed'],'owned process exit receipt')
    require('Blender quit' in (NATIVE/'blender.log').read_text(encoding='utf8'),'owned Blender exit log')
    for path,expected in frozen['files'].items():require(sha(ROOT/path)==expected,'source remains unchanged after audit '+path)
    output={'schema':'arm-correction-opt-independent-native-audit-v1','passed':True,'checks':checks,'runtime_source_count':137,
        'runtime_source_sha256':source_hash,'cases':rows,'micro_weight_witness_independent_j':witness_j,
        'new_product_calls':0,'new_Blender_runs':0,'model_calls':0,'input_sha256':input_hashes,'script_sha256':sha(Path(__file__)),
        'scope':'Eight actual BoundArmPatch captures supplied unchanged to preview, four QA candidate realizations, four no-write branches; only fixed generated assets.',
        'limitations':['Canonical source identity is a local implementation binding, not authorization.',
            'Operation counts and process closure combine immutable source/record evidence; no new live PID query or instrumented execution.',
            'Full capture/input/static/sentinel/protected values are independently compared; after-call packet immutability also relies on the frozen pure-source review and producer receipt.',
            'No native UI/MCP execution integration, real-character repair, full volume, comparative speed or learning-benefit claim.']}
    (HERE/'INDEPENDENT_NATIVE_AUDIT.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'checks':checks,'source_sha256':source_hash,'cases':rows,'witness_j':witness_j},ensure_ascii=False))


if __name__=='__main__':main()
