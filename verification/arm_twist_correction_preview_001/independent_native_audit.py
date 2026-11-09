"""Recompute native evidence with stdlib math; no product/oracle/model imports."""
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NATIVE=HERE/'native_01'
OUTPUT=HERE/'INDEPENDENT_NATIVE_AUDIT.json'
FIXED=(('round_120',120.),('round_minus150',-150.),('elliptic_120',120.),('elliptic_minus150',-150.))
GATES={'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5}
checks=0


def require(value,label):
    global checks
    checks+=1
    if not value:raise AssertionError(label)


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')).hexdigest()
def subtract(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def distance(a,b):return norm(subtract(a,b))
def unit(a):
    length=norm(a)
    require(length>0 and math.isfinite(length),'nonzero finite rotation column')
    return [v/length for v in a]


def area(points,section):
    # A triangle fan anchored at the first actual 3D vertex, using compensated
    # sums, independently of production's centred NumPy polygon cross-sum.
    anchor=points[section[0]]
    vectors=[cross(subtract(points[section[i]],anchor),subtract(points[section[i+1]],anchor))
             for i in range(1,len(section)-1)]
    value=.5*norm([math.fsum(v[k] for v in vectors) for k in range(3)])
    require(value>0 and math.isfinite(value),'positive finite ordered 3D ring area')
    return value


def frame(matrix):
    # Independent Gram-Schmidt for measuring float32 rotation discrepancy.
    x=unit([matrix[k][0] for k in range(3)])
    raw_y=[matrix[k][1] for k in range(3)];projection=dot(x,raw_y)
    y=unit([raw_y[k]-projection*x[k] for k in range(3)])
    z=cross(x,y)
    require(dot(z,[matrix[k][2] for k in range(3)])>0,'proper native rotation frame')
    return x,y,z


def rotation_degrees(left,right):
    a,b=frame(left),frame(right)
    relative=[[dot(x,y) for y in b] for x in a]
    sine=.5*norm([relative[2][1]-relative[1][2],relative[0][2]-relative[2][0],relative[1][0]-relative[0][1]])
    cosine=.5*(math.fsum(relative[k][k] for k in range(3))-1.)
    return math.degrees(math.atan2(sine,cosine))


def center(points,section):return [math.fsum(points[i][k] for i in section)/len(section) for k in range(3)]
def matrix_error(a,b):return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def inverse4(matrix):
    augmented=[list(row)+[float(i==j) for j in range(4)] for i,row in enumerate(matrix)]
    for column in range(4):
        pivot=max(range(column,4),key=lambda row:abs(augmented[row][column]))
        augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        divisor=augmented[column][column]
        require(abs(divisor)>1e-14,'nonsingular native matrix')
        augmented[column]=[v/divisor for v in augmented[column]]
        for row in range(4):
            if row!=column:
                factor=augmented[row][column]
                augmented[row]=[v-factor*w for v,w in zip(augmented[row],augmented[column])]
    return [row[4:] for row in augmented]


def native_lbs_error(static,poses,current):
    inverses=[inverse4(matrix) for matrix in static['rest_matrices']]
    worst=0.
    for point,weights,actual in zip(static['rest_vertices'],static['weights'],current):
        transformed=[]
        for original_inverse,pose in zip(inverses,poses):
            local=[dot(row,point+[1.]) for row in original_inverse]
            transformed.append([dot(row,local) for row in pose[:3]])
        predicted=[math.fsum(w*p[k] for w,p in zip(weights,transformed)) for k in range(3)]
        worst=max(worst,distance(predicted,actual))
    return worst


def main():
    frozen=read(NATIVE/'SOURCE_FREEZE.json');result=read(NATIVE/'RESULT.json')
    cpu=read(HERE/'cpu_final/RESULT.json');input_freeze=read(HERE/'cpu_final/INPUT_FREEZE.json')
    cpu_packets_path=HERE/'cpu_final/INPUT_PACKETS.json';cpu_packets=read(cpu_packets_path)
    reconstruction_path=HERE/'cpu_final/INPUT_RECONSTRUCTION.json';reconstruction=read(reconstruction_path)
    require(reconstruction['sha256']==sha(cpu_packets_path) and reconstruction['pre_run_full_packet_snapshot_claimed'] is False,
            'CPU input archive explicitly is a post-run reconstruction')
    require(all(reconstruction[k]==0 for k in ('new_preview_calls','new_model_calls','new_Blender_runs')),'no new product/native runs for input reconstruction')
    require(len(cpu_packets)==len(input_freeze['cases'])==8,'eight reconstructed CPU input packets')
    for packet,saved in zip(cpu_packets,input_freeze['cases']):
        require(packet['case_id']==saved['case_id'],'reconstructed CPU case identity')
        require(digest(packet['patch'])==saved['patch_sha256'] and digest(packet['task'])==saved['task_sha256'],
                'reconstructed CPU patch/task match pre-run canonical SHA256')
    legacy_path=ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz'
    require(sha(legacy_path)==input_freeze['files']['verification/m6_arm_expert_001/run_01/dataset.json.gz'],'frozen legacy asset reference')
    legacy=json.loads(gzip.decompress(legacy_path.read_bytes()))
    require(result['native_gates']==frozen['native_gates']==GATES,'predeclared native gates unchanged')
    require(result['source_hashes_before']==result['source_hashes_after']==frozen['files'],'matching frozen source maps')
    for name,expected in frozen['files'].items():require(sha(ROOT/name)==expected,'frozen current source '+name)
    require(len(result['cases'])==len(FIXED),'exactly the four fixed native positives')
    rows=[];input_hashes={str(p.relative_to(ROOT)):sha(p) for p in (
        NATIVE/'SOURCE_FREEZE.json',NATIVE/'RESULT.json',NATIVE/'process.json',NATIVE/'process_exit.json',NATIVE/'blender.log',
        HERE/'cpu_final/RESULT.json',HERE/'cpu_final/INPUT_FREEZE.json',cpu_packets_path,reconstruction_path,legacy_path)}
    for index,(name,theta) in enumerate(FIXED,1):
        path=NATIVE/('case_'+str(index).zfill(2)+'.json');raw=read(path);summary=result['cases'][index-1]
        input_hashes[str(path.relative_to(ROOT))]=sha(path)
        require(raw['case_id']==summary['case_id']==cpu['cases'][index-1]['case_id']==name,'fixed native/CPU case identity')
        require(sha(path)==summary['raw_native_readback_sha256'],'raw case bytes bound to result')
        require(raw['source_input_sha256']==summary['input_sha256_before'],'native input binding within native records')
        cpu_input=cpu_packets[index-1]
        require(digest([cpu_input['patch'],cpu_input['task']])==cpu['cases'][index-1]['input_sha256'],
                'complete reconstructed CPU arguments bind original CPU result')
        require(input_freeze['cases'][index-1]['case_id']==name,'fixed task identity')
        require(input_freeze['cases'][index-1]['task']['max_section_area_loss']==.4,'fixed target .4')
        sections=raw['sections'];ids=raw['vertex_ids'];static=raw['native_static']
        before=raw['native_before'];after=raw['native_after']
        cpu_patch=cpu_input['patch']
        require(ids==cpu_patch['vertex_ids'] and sections==cpu_patch['sections'] and static['triangles']==cpu_patch['triangles'],
                'native IDs sections topology exactly equal reconstructed CPU input')
        cpu_native_weights=max(abs(a-b) for wa,wb in zip(static['weights'],cpu_patch['weights']) for a,b in zip(wa,wb))
        cpu_native_rest=max(distance(a,b) for a,b in zip(static['rest_vertices'],cpu_patch['rest_vertices']))
        cpu_native_rest_matrices=max(matrix_error(a,b['rest_matrix']) for a,b in zip(static['rest_matrices'],cpu_patch['bone_chain']))
        cpu_native_initial_poses=max(matrix_error(a,b['pose_matrix']) for a,b in zip(before['pose_matrices'],cpu_patch['bone_chain']))
        cpu_native_initial_points=max(distance(a,b) for a,b in zip(before['current_vertices'],cpu_patch['current_vertices']))
        require(cpu_native_initial_points<=GATES['position_m'],'native before points agree with reconstructed CPU input')
        asset=next(item['packet'] for item in legacy if item['metadata']['asset_id']==summary['asset_id'])
        require(ids==asset['vertex_ids'] and sections==asset['sections'] and static['triangles']==asset['triangles'],
                'native IDs sections topology equal saved legacy baseasset')
        weight_delta=max(abs(a-b) for wa,wb in zip(static['weights'],asset['weights']) for a,b in zip(wa,wb))
        float32_weights=[[struct.unpack('<f',struct.pack('<f',w))[0] for w in row] for row in asset['weights']]
        require(static['weights']==float32_weights,'native weights equal float32 legacy weights')
        rest_vertex_delta=max(distance(a,b) for a,b in zip(static['rest_vertices'],asset['rest_vertices']))
        rest_matrix_delta=max(matrix_error(a,b['rest_matrix']) for a,b in zip(static['rest_matrices'],asset['bone_chain']))
        require(len(sections)==25 and all(len(s)==16 for s in sections),'25 rings of 16 vertices')
        require(len(ids)==len(set(ids))==402,'same-index 402 unique IDs')
        require(len(before['current_vertices'])==len(after['current_vertices'])==len(static['rest_vertices'])==402,'native point denominator')
        require(len(static['triangles'])==800 and len(static['weights'])==402,'native triangles and weights denominators')
        require(all(len(set(s))==16 and all(type(i) is int and 0<=i<402 for i in s) for s in sections),'valid ring indices')
        areas0=[area(static['rest_vertices'],s) for s in sections]
        before_ratios=[area(before['current_vertices'],s)/a0 for s,a0 in zip(sections,areas0)]
        after_ratios=[area(after['current_vertices'],s)/a0 for s,a0 in zip(sections,areas0)]
        before_j=max(0.,1.-min(before_ratios));after_j=max(0.,1.-min(after_ratios))
        expected_before=math.sin(math.radians(theta)/2)**2
        expected_after=math.sin(math.radians(theta)/4)**2
        require(abs(before_j-expected_before)<=GATES['section_area_loss'],'before independent analytic J')
        require(abs(after_j-expected_after)<=GATES['section_area_loss'],'after independent analytic J')
        require(after_j<=.4+GATES['section_area_loss'] and after_j<before_j,'actual native target and improvement')
        require(abs(raw['candidate']['u_deg']-theta/2)<=GATES['angle_deg'],'candidate u independently equals theta/2')
        for actual,label in ((before_ratios,'before'),(after_ratios,'after')):
            require(max(abs(a-b) for a,b in zip(actual,raw[label+'_objective']['section_area_ratios']))<1e-12,
                    'all 25 raw area ratios independently reproduce '+label)
        ring_errors=[]
        for section,b0,b1 in zip(sections,before_ratios,after_ratios):
            weights=static['weights'][section[0]]
            require(all(max(abs(a-b) for a,b in zip(static['weights'][i],weights))<1e-7 for i in section),'constant native ring weights')
            values=[]
            for angles in ((0.,theta,theta),(0.,theta/2,theta)):
                real=math.fsum(w*math.cos(math.radians(a)) for w,a in zip(weights,angles))
                imaginary=math.fsum(w*math.sin(math.radians(a)) for w,a in zip(weights,angles))
                values.append(real*real+imaginary*imaginary)
            ring_errors.extend((abs(b0-values[0]),abs(b1-values[1])))
        require(max(ring_errors)<=GATES['section_area_loss'],'all 25 rings agree with independent weighted SO2 determinant')
        for section_index,weights in ((8,[.5,.5,0.]),(16,[0.,.5,.5])):
            require(all(static['weights'][i]==weights for i in sections[section_index]),'native joint half-weight evidence')
        end_matrix=max(matrix_error(before['global_pose_matrices'][i],after['global_pose_matrices'][i]) for i in (0,2))
        end_angle=max(rotation_degrees(before['global_pose_matrices'][i],after['global_pose_matrices'][i]) for i in (0,2))
        end_position=max(distance([before['global_pose_matrices'][i][k][3] for k in range(3)],
                                  [after['global_pose_matrices'][i][k][3] for k in range(3)]) for i in (0,2))
        require(end_matrix<=GATES['position_m'] and end_angle<=GATES['angle_deg'] and end_position<=GATES['position_m'],
                'full fixed end matrices independently preserved')
        center_delta=max(distance(a,b) for key in ('head_positions','tail_positions') for a,b in zip(before[key],after[key]))
        ring_center_delta=max(distance(center(before['current_vertices'],s),center(after['current_vertices'],s)) for s in sections)
        require(max(center_delta,ring_center_delta)<=GATES['position_m'],'all heads/tails and 25 ring centers preserved')
        id_map={v:i for i,v in enumerate(ids)}
        protected=raw['protected_vertex_ids']
        pure={ids[i] for i,w in enumerate(static['weights']) if w==[1.,0.,0.] or w==[0.,0.,1.]}
        require(len(protected)==len(set(protected))==194 and set(protected)==pure,'all 194 pure end vertices protected')
        require(protected==cpu_input['task']['protected_vertex_ids'],'protected IDs equal reconstructed CPU task')
        protected_delta=max(distance(before['current_vertices'][id_map[v]],after['current_vertices'][id_map[v]]) for v in protected)
        require(protected_delta<=GATES['position_m'],'all protected native vertices preserved')
        cpu_candidate=cpu['cases'][index-1]['preview']['candidate']
        cross_runtime_delta=max(matrix_error(a,b) for key in ('pose_matrices','local_basis_matrices')
                                for a,b in zip(raw['candidate'][key],cpu_candidate[key]))
        require(cross_runtime_delta<=1e-12,'cross-runtime candidate numeric consistency, not byte identity')
        require([change['name'] for change in raw['candidate']['bone_changes']]==['arm_1','arm_2'],'only middle/end declared changes')
        for i,change in zip((1,2),raw['candidate']['bone_changes']):
            require(change['basis_matrix']==raw['candidate']['local_basis_matrices'][i],'declared change and supplied basis exact')
        require(raw['checks']['static_data_exact'] and raw['checks']['outside_object_exact'] and raw['checks']['input_packet_and_task_exact'],
                'author runtime static/outside/input preservation receipts')
        cross_task_end_delta=max(matrix_error(raw['candidate']['pose_matrices'][i],matrix)
                                 for i,matrix in zip((0,2),input_freeze['cases'][index-1]['task']['fixed_end_pose_matrices']))
        before_lbs=native_lbs_error(static,before['pose_matrices'],before['current_vertices'])
        after_lbs=native_lbs_error(static,after['pose_matrices'],after['current_vertices'])
        require(max(before_lbs,after_lbs)<=GATES['position_m'],'native readbacks independently match native static LBS')
        cpu_predicted_native_delta=max(distance(a,b) for a,b in zip(cpu_candidate['current_vertices'],after['current_vertices']))
        require(cpu_predicted_native_delta<=GATES['position_m'],'native after points agree with CPU predicted candidate points')
        rows.append({'case_id':name,'before_j':before_j,'after_j':after_j,'analytic_before_j':expected_before,
            'analytic_after_j':expected_after,'max_25_ring_determinant_error':max(ring_errors),
            'fixed_end_matrix_max_abs':end_matrix,'fixed_end_rotation_deg':end_angle,'fixed_end_translation_m':end_position,
            'all_heads_tails_max_m':center_delta,'all_25_ring_centers_max_m':ring_center_delta,
            'protected_vertices':194,'protected_vertices_max_m':protected_delta,'raw_sha256':sha(path),
            'CPU_native_input_hash_equal':raw['source_input_sha256']==cpu['cases'][index-1]['input_sha256'],
            'CPU_native_candidate_matrix_max_abs':cross_runtime_delta,'CPU_task_native_preview_fixed_end_matrix_max_abs':cross_task_end_delta,
            'CPU_candidate_points_native_after_max_m':cpu_predicted_native_delta,
            'native_same_index_LBS_before_max_m':before_lbs,'native_same_index_LBS_after_max_m':after_lbs,
            'reconstructed_CPU_input_vs_native_RNA':{'vertex_ids_exact':True,'sections_exact':True,'triangles_exact':True,
                'protected_ids_exact':protected==cpu_input['task']['protected_vertex_ids'],
                'weights_exact_float64':static['weights']==cpu_patch['weights'],'weights_max_abs':cpu_native_weights,
                'rest_vertices_exact_float64':static['rest_vertices']==cpu_patch['rest_vertices'],'rest_vertices_max_m':cpu_native_rest,
                'rest_matrices_max_abs':cpu_native_rest_matrices,'initial_pose_matrices_max_abs':cpu_native_initial_poses,
                'initial_current_points_max_m':cpu_native_initial_points},
            'saved_legacy_reference_vs_native_static':{'vertex_ids_exact':True,'sections_exact':True,'triangles_exact':True,
                'weights_exact_float64':static['weights']==asset['weights'],'weights_exact_float32_conversion':True,
                'weights_max_abs':weight_delta,'rest_vertices_exact':static['rest_vertices']==asset['rest_vertices'],
                'rest_vertices_max_m':rest_vertex_delta,'rest_matrices_max_abs':rest_matrix_delta}})
    require(result['work']=={'preview_calls':4,'model_calls':0,'product_setters':0,'qa_initial_pose_assignments':12,
                            'qa_candidate_pose_assignments':8,'native_readbacks':8,'fixtures_constructed':4},'separate product and QA operation counts')
    product_tree=ast.parse((ROOT/'human_eye_plugin/arm_twist_correction.py').read_text(encoding='utf8'))
    require(not any(isinstance(node,ast.Attribute) and isinstance(node.ctx,ast.Store) for node in ast.walk(product_tree)),
            'preview source has no attribute setters')
    require(not any(isinstance(node,ast.Import) and any(a.name=='bpy' for a in node.names) for node in ast.walk(product_tree)),
            'preview has no direct bpy import')
    qa_tree=ast.parse((HERE/'native_probe.py').read_text(encoding='utf8'))
    setters=[node for node in ast.walk(qa_tree) if isinstance(node,ast.Attribute) and isinstance(node.ctx,ast.Store) and node.attr=='matrix_basis']
    require(len(setters)==2,'QA source has initial and candidate basis assignment sites')
    require(all(result[key] for key in ('owned_objects_removed','owned_meshes_removed','owned_rigs_removed',
                                      'source_bytes_unchanged','blend_file_still_unsaved','outside_object_exact')),'runtime cleanup and no-save receipts')
    exit_record=read(NATIVE/'process_exit.json');process=read(NATIVE/'process.json')
    require(exit_record['pid']==process['pid']==19144 and exit_record['returncode']==0 and exit_record['closed'],'owned process exit receipt')
    require('Blender quit' in (NATIVE/'blender.log').read_text(encoding='utf8'),'native exit log')
    require(all(flag in process['command'] for flag in ('--factory-startup','--disable-autoexec','--background')),'isolated native process flags')
    for name,expected in frozen['files'].items():require(sha(ROOT/name)==expected,'source remains unchanged after audit '+name)
    output={'schema':'arm-correction-independent-native-audit-v1','passed':True,'checks':checks,'cases':rows,
        'script_sha256':sha(Path(__file__)),'source_sha256':frozen['files'],'input_sha256':input_hashes,'gates':GATES,
        'independent_native_area_evaluations':300,'new_effect_cases':0,'new_Blender_runs':0,'product_imports':0,'model_calls':0,
        'scope':'Native runtime regenerated the fixed synthetic definitions and recomputed preview candidates before QA application; comparison with CPU candidates is numeric. Generated-fixture geometry/pose feasibility only.',
        'limitations':[
            'Static-after arrays, outside-object arrays and input packets were not fully persisted; those exact-preservation facts remain author runtime receipts, not independent bytewise recomputations.',
            'Process closure is checked from matching receipt and log, not a new live PID query.',
            'Native/CPU input hashes differ across their numerical runtimes; native records are hash-bound separately and candidate numeric differences are measured, not described as byte-identical. Original input packets are not independently reconstructed here.',
            'Complete CPU inputs were reconstructed after the run and independently matched to original pre-run canonical SHA256s; they were not a pre-run full snapshot. Original native-runtime double input packets remain absent, so their cross-runtime byte identity cannot be asserted. Comparisons distinguish CPU double inputs from native RNA float32 and the frozen saved legacy baseasset.',
            'No claim that preview accepts native packets, no product setter, real-character repair, animation, volume or learned correction benefit.']}
    OUTPUT.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'checks':checks,'cases':rows,'output':str(OUTPUT)},ensure_ascii=False))


if __name__=='__main__':main()
