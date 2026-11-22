"""Verify original exact geometry, then measure actual installed partition dispatch."""

import argparse
from contextlib import contextmanager
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from time import perf_counter_ns
from types import SimpleNamespace
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
REPO = V.parent
BASE = '7e096daf3bb24596905f76abefa5e07a96a9f5d1'
MAIN_RUNTIME = Path('D:/he_m4_yanyite_dual_curved_region_native_001/sealed')
MAIN_RESULT = V/'m4_yanyite_dual_curved_region_native_001/RESULT.json'
HOLDOUT = V/'m1_source_region_task_entry_holdout_001'
RECTANGLE = V/'m4_source_region_active_view_001'
CASES = (
    dict(label='yanyite_upper', archive=MAIN_RUNTIME/'ORIGINAL_RUNTIME.zip',
         index=MAIN_RUNTIME/'RAW_INDEX.json', namespace='runtime/slots/QP',
         archive_source=(MAIN_RESULT,'eeae0719'), producer_index=2, owner_index=3, wire=(3,4),
         triangles=311, points=184, product_name='0135bbc4-c6c7-4003-a402-6f2e0283497d',
         view='SCENE', pixels=49480, sampled=116, nonplanar=True),
    dict(label='obj08_nonplanar_holdout', archive=HOLDOUT/'ORIGINAL_RUNTIME.zip',
         index=HOLDOUT/'RAW_INDEX.json', namespace='runtime/slots/QA',
         archive_source=(HOLDOUT/'RAW_INDEX.json','721ed392'), producer_index=1, owner_index=3, wire=(3,),
         triangles=4, points=6, product_name='Obj_08', view='SCENE', nonplanar=True),
    dict(label='n15_supported_rectangle', archive=Path('D:/he_m4_source_region_active_view_001/ORIGINAL_RUNTIME.zip'),
         index=RECTANGLE/'RUNTIME_INDEX.json', namespace='slots/B',
         archive_source=(RECTANGLE/'RUNTIME_INDEX.json','c18b7bdc'), producer_index=1, owner_index=1, wire=(2,3),
         triangles=2, points=4, product_name='N15', view='RIGHT', nonplanar=False),
)


def require(condition, name):
    if not condition:
        raise ValueError(name)


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return {'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def pin(path):
    path = path.resolve(strict=True)
    return {'path':str(path),**digest(path.read_bytes())}


def canonical_sha256(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def archive_path(slot, original):
    parts = PureWindowsPath(original).parts
    position = parts.index('slots')
    require(parts[position+1] == slot.rsplit('/',1)[-1], 'archived_frame_is_from_another_slot')
    return '/'.join(parts[position+2:])


def archived(case):
    """Accept only the indexed original terminal, request, producer, wire and frames."""
    static, commit = case['archive_source']
    git = subprocess.check_output(['git','show',f'{commit}:{static.relative_to(REPO).as_posix()}'],cwd=REPO)
    require(git == static.read_bytes(),'changed_archive_provenance/'+case['label'])
    record = read(static)
    index = read(case['index'])
    wanted = record.get('original_local_raw_archive',index['archive'])
    actual = pin(case['archive'])
    require(all(actual[key] == wanted[key] == index['archive'][key] for key in ('bytes','sha256')),
            'changed_archive_artifact/'+case['label'])
    entries = index['members'] if 'members' in index else {r['path']:r for r in index['files']}
    with ZipFile(case['archive']) as z:
        def member(path):
            name = case['namespace']+'/'+path
            data = z.read(name)
            receipt = digest(data)
            require(all(receipt[key] == entries[name][key] for key in receipt),'archive_member_hash/'+name)
            return data, {'member':name,**receipt}

        terminal, terminal_pin = member('TERMINAL_SOURCE.json')
        producer, producer_pin = member(f"product_full/call_{case['producer_index']:03d}/SERVICE_RESULT.json")
        request, request_pin = member(f"owner/tool_{case['owner_index']:02d}/PRODUCT_REQUEST.json")
        terminal, producer, request = map(json.loads,(terminal,producer,request))
        if case['label'] == 'yanyite_upper':
            require(terminal_pin['sha256']=='977078b4ac86cdaf75cfb15151ca5ddf8c197895ce0bb7fa6691547c428e1d6f'
                    and terminal_pin['bytes']==9614523 and
                    producer_pin['sha256']=='af7f24a52f584f40eb0d7c3ff9acd9c23f19a530e7a5c818f732c848cf097289',
                    'frozen_main_terminal_or_producer_changed')
        packets, packet_pins = [], []
        for sequence in case['wire']:
            raw, receipt = member(f'native/WIRE/{sequence:03d}/RESPONSE.bin')
            envelope = json.loads(raw)['result']['result']
            prefix = 'HUMAN_EYE_BLENDER_MCP:'
            require(envelope.startswith(prefix),'invalid_archived_capture_envelope')
            packet = json.loads(envelope[len(prefix):])['result']
            require(packet['schema']=='human-eye-scene-delta-v1','unexpected_capture_protocol')
            packets.append(packet)
            packet_pins.append(receipt)
        frame_pins = []
        for frame in {f['frame_identity']:f for f in [*producer['frames'], *producer.get('constructed_frames',[])]}.values():
            assets = {}
            for field, checksum, size in (
                    ('image_path','image_sha256','PNG_bytes'),
                    ('arrays_path','arrays_sha256','compressed_array_file_bytes')):
                _, receipt = member(archive_path(case['namespace'],frame[field]))
                require((receipt['sha256'],receipt['bytes']) == (frame[checksum],frame[size]),
                        'archived_frame_png_npz_not_bound/'+case['label'])
                assets[field] = receipt
            frame_pins.append({'frame_identity':frame['frame_identity'],'view':frame['view_name'],**assets})
    originals = {'archive':actual,'terminal':terminal_pin,'producer':producer_pin,'request':request_pin,
                 'capture_packets':packet_pins,'frames':frame_pins}
    pins = [pin(path) for path in {static,case['index'],case['archive']}]
    return terminal, producer, request['params']['arguments'], packets, originals, pins


def offsets(row, origin):
    return tuple(end-start for end,start in zip(row,origin))


def plane_minor(a, b):
    return tuple(a[i]*b[j]-a[j]*b[i] for i,j in ((1,2),(2,0),(0,1)))


def det3(a, b, c):
    return a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0])


def exact_witness(vertices, faces, selected):
    """Find a concrete face/corner witness using independent determinant arithmetic."""
    for basis in selected:
        origin,left,right = (vertices[i] for i in faces[basis])
        u,v = offsets(left,origin),offsets(right,origin)
        if not any(plane_minor(u,v)):
            continue
        for row in selected:
            for vertex in faces[row]:
                value = det3(u,v,offsets(vertices[vertex],origin))
                if value:
                    return {'basis_triangle_index':basis,'point_triangle_index':row,'point_vertex_index':vertex,
                            'determinant':str(value)}
        return None
    return None


def exact_capture_points(terminal, production, packets, capture, selection):
    original = {row['object_id']:row for row in terminal['objects']}
    resources = {(r['id'],r['revision']):r for r in packets[0]['resources']}
    first, current = (p['capture'] for p in (packets[0],packets[-1]))
    binding_fields = ('meshes','host_identity','revision','display_snapshot','unit','coordinate_frame')
    require(all(first[key]==current[key] for key in binding_fields) and all(not p['resources'] for p in packets[1:]) and
            first['capture_state']==capture['capture_state']==production['binding']['capture_state'],
            'replay_source_or_generation_not_its_original_current_pose')
    by_id = {}
    for i,mesh in enumerate(first['meshes']):
        desc = mesh['_scene_resource']
        res = resources[desc['id'],desc['revision']]
        historical = original[mesh['object_id']]
        eval_ = historical['evaluated']
        require(mesh['name']==historical['name']==capture['meshes'][i]['name'] and
                first['host_identity']['object_instances'][mesh['object_id']]==historical['instance_id'] and
                desc['matrix']==historical['matrix_world'] and desc['scale']==terminal['source']['scale_length'] and
                res['vertices_local']==eval_['vertices'] and res['faces']==eval_['triangles'],
                'capture_resource_does_not_match_live_terminal_geometry')
        matrix,scale = desc['matrix'],desc['scale']
        # Mirror the documented binary64 input domain before exact arithmetic.
        world = [[(sum(matrix[r][c]*p[c] for c in range(3))+matrix[r][3])*scale for r in range(3)]
                 for p in res['vertices_local']]
        require(world==capture['meshes'][i]['vertices'] and res['faces']==capture['meshes'][i]['faces'],
                'independent_resource_transform_not_equal_to_runtime')
        by_id[mesh['object_id']] = (world,res['faces'])
    ref = production['region_ref']
    raw_geometry = [{'host_id':m['object_id'],'instance_id':original[m['object_id']]['instance_id'],
                     'vertices':m['vertices'],'faces':m['faces']} for m in capture['meshes']]
    require(canonical_sha256(raw_geometry)==ref['ordered_geometry_sha256'] and
            ref['instance_id']==original[ref['host_id']]['instance_id'] and
            ref['source_triangle_indices']==selection['source_triangle_indices'] and
            selection['object']=={'name':original[ref['host_id']]['name']},
            'archived_selection_not_bound_to_this_ordered_mesh')
    return by_id[ref['host_id']]


@contextmanager
def counted_partition(sr, injected_error=None):
    actual = sr.partition_regions
    counts = {'calls':0,'target_face_rows':0}
    def trace(objects,*,target_object_index=None):
        counts['calls'] += 1
        counts['target_face_rows'] += len(objects[target_object_index][1])
        if injected_error is not None:
            raise ValueError(injected_error)
        return actual(objects,target_object_index=target_object_index)
    sr.partition_regions = trace
    try:
        yield counts
    finally:
        sr.partition_regions = actual


def rectangle_summary(region):
    if region is None:
        return None
    return {'object_index':region.object_index,'object_name':region.object_name,'roi_id':region.roi_id,
            'triangle_indices':list(region.triangle_indices),'ordered_corners':[[str(k) for k in p] for p in region.vertices],
            'directed_normal':[str(k) for k in region.normal]}


def real_case(case, sr, decoder_cls, is_candidate):
    terminal, producer, arguments, packets, origins, pins = archived(case)
    decoder = decoder_cls()
    for packet in packets:
        capture = decoder.apply(packet)
    selection = arguments['query']['region']
    selected = tuple(selection['source_triangle_indices'])
    world,faces = exact_capture_points(terminal,producer,packets,capture,selection)
    vertices = tuple(tuple(Fraction(c) for c in xyz) for xyz in world)
    source_vertices = tuple(sorted({v for face in selected for v in faces[face]}))
    require(len(selected)==case['triangles'] and len(source_vertices)==case['points']
            and producer['facts']['region']['source_vertex_indices']==list(source_vertices),
            'archived_selection_shape_changed/'+case['label'])
    witness = exact_witness(vertices,faces,selected)
    require(bool(witness)==case['nonplanar'],'independent_exact_plane_not_as_frozen/'+case['label'])
    if case['label']=='yanyite_upper':
        require((witness['basis_triangle_index'],witness['point_triangle_index'],witness['point_vertex_index'])
                ==(4332,4333,24260),'actual_main_nonzero_determinant_witness_changed')
    prepared = sr.prepare_region(capture,arguments['query'])
    require(prepared.source_triangle_indices==selected and prepared.source_vertex_indices==source_vertices
            and prepared.objects[prepared.object_index][:2] == (vertices,tuple(tuple(f) for f in faces)),
            'installed_preparation_not_independent_binary64_exact_geometry')
    with counted_partition(sr) as work:
        started=perf_counter_ns()
        result=sr._selected_rectangle(prepared)
        elapsed=perf_counter_ns()-started
    continued = not (is_candidate and case['nonplanar'])
    require(work['calls']==int(continued) and (result is not None)==(not case['nonplanar']),
            'installed_partition_or_rectangle_branch_changed/'+case['label'])
    visibility = producer['facts']['visibility']
    frame, = producer['frames']
    require(arguments['include_image'] is True and frame['view_name']==case['view'] and
            frame['image_ref']==visibility['image_ref'] and producer['status']=='complete',
            'archived_original_not_its_supported_image/'+case['label'])
    if 'pixels' in case:
        require(visibility['selected_surface_pixels']==case['pixels'] and
                len(visibility['visible_source_triangle_indices'])==case['sampled'],
                'main_archived_actual_pixel_support_changed')
    if result is not None:
        require(result.triangle_indices==selected and result.object_name==case['product_name'] and
                visibility['complete_witness']['view_name']==case['view'],
                'n15_positive_rectangle_witness_changed')
    return {'label':case['label'],'selected_source_triangles':len(selected),'selected_source_vertices':len(source_vertices),
            'proof':witness,'rectangle':rectangle_summary(result),'partition_dispatch':work,'observed_selection_elapsed_ns':elapsed,
            'picture':{'vision':frame['view_name'],'visible_surface_pixels':visibility['selected_surface_pixels'],
                       'sampled_triangles':len(visibility['visible_source_triangle_indices']),
                       'complete_witness':visibility['complete_witness'] is not None},
            'measurement':producer['task_result']['facts']['surface_proximity'],'archived_originals':origins}, pins


def synthetic(sr,is_candidate):
    f=Fraction
    quad=[(0,0,0),(1,0,0),(1,1,0),(0,1,0)]
    w=[(0,1,2),(0,2,3)]
    offset_planes=quad+[(4,0,1),(5,0,1),(4,1,1)]
    two_planes=w+[(4,5,6)]
    tilted_quad=[(x,y,2*y) for x,y,z in quad]
    panels=quad+[(2,0,0),(2,1,0)]
    opposite=[w[0],tuple(reversed(w[1]))]
    tiny=quad[:3]+[(0,1,f(1, 2**1074))]
    degenerate=[(0,0,2),(1,0,2),(2,0,2),(0,1,3),(0,2,4)]
    cases = [
        ('ordinary_planar_rectangle',quad,w,(0,1),False,True),
        ('oblique_plane_exact',tilted_quad,w,(0,1),False,True),
        ('planar_nonmaximal_component_subset',panels,w+[(1,4,5),(1,5,2)],(0,1),False,False),
        ('coincident_independent_components',quad+quad,w+[(4,5,6),(4,6,7)],(0,1),False,False),
        ('selection_plane_checks_only_its_linked_vertices',offset_planes,two_planes,(0,1),False,True),
        ('opposite_winding_planar_rejection',quad,opposite,(0,1),False,False),
        ('zero_area_first_later_planar',quad,[(0,0,1),*w],(0,1,2),False,False),
        ('zero_area_first_later_strict_nonplanar',offset_planes,[(0,0,1),*two_planes],(0,1,3),True,False),
        ('degenerate_only_no_selected_basis',degenerate,[(0,1,2),(0,3,4)],(0,1),False,False),
        ('smallest_nonzero_binary64_residual',tiny,w,(0,1),True,False),
    ]
    records=[]
    for label, xyz, faces, selected, nonplanar, rectangle in cases:
        objects,_,_=sr.geometry({'objects':[{'name':'target','vertices':xyz,'triangles':faces}]})
        vertices, face_rows = objects[0][:2]
        witness = exact_witness(vertices,face_rows,selected)
        require(bool(witness)==nonplanar,'synthetic_independent_plane/'+label)
        chosen = tuple(sorted({i for row in selected for i in face_rows[row]}))
        prepared = SimpleNamespace(objects=objects,object_index=0,source_triangle_indices=selected,source_vertex_indices=chosen)
        with counted_partition(sr) as counts:
            result=sr._selected_rectangle(prepared)
        require((result is not None)==rectangle and counts['calls']==int(not (is_candidate and nonplanar)),
                'unexpected_synthetic_partition_or_region/'+label)
        records.append({'label':label,'passed':True,'proof':witness,'rectangle':rectangle_summary(result),'partition_dispatch':counts})
    objects,_,_=sr.geometry({'objects':[{'name':'same','vertices':quad,'triangles':w} for _ in range(2)]})
    first,second = ((m[0],m[1],(m[2],'same_host',index),m[3]) for index,m in enumerate(objects))
    prepared = SimpleNamespace(objects=(first,second),object_index=1,source_triangle_indices=(0,1),source_vertex_indices=(0,1,2,3))
    with counted_partition(sr) as counts:
        retained=sr._selected_rectangle(prepared)
    require(retained.object_index==1 and counts['calls']==1,'same_geometry_distinct_current_instance_lost')
    records.append({'label':'same_geometry_distinct_instances','passed':True,'rectangle':rectangle_summary(retained),'partition_dispatch':counts})
    for invalid in ([],[0,0],[2],[False]):
        try:
            sr._indices(invalid,2)
        except ValueError as error:
            require(str(error)=='source_region_unique_current_triangle_indices_required','malformed_selection_rejected_for_wrong_reason')
        else:
            raise ValueError('malformed_selection_not_rejected')
        require(sr._indices([1,0],2)==(0,1) and sr._selected_rectangle(prepared)==retained,
                'valid_rectangle_recovery_after_invalid_selection_failed')
    with counted_partition(sr,'unrelated_partition_error') as counts:
        try:
            sr._selected_rectangle(prepared)
        except ValueError as error:
            require(str(error)=='unrelated_partition_error','unrelated_partition_failure_was_reclassified')
        else:
            raise ValueError('unrelated_partition_failure_was_swallowed')
    require(counts['calls']==1 and sr._selected_rectangle(prepared)==retained,'valid_recovery_after_partition_failure')
    records.append({'label':'malformed_selection_then_recovery_and_partition_failure_passthrough','passed':True,
                    'invalid_public_source_index_shapes':4,'unexpected_partition_error_rethrown':True})
    return records


def run(binding_path):
    binding=read(binding_path)
    root=Path(binding['install_root']).resolve(strict=True)
    require(len(binding['source_manifest'])==143,'unexpected_installed_product_source_set')
    source=next(row for row in binding['source_manifest'] if row['path']=='human_eye_plugin/source_region.py')
    installed=pin(root/source['path'])
    require(installed['sha256']==source['sha256'],'source_region_import_does_not_match_install')
    candidate=binding['preparation_git']!=BASE
    sys.path[:0]=[str(root),binding['dependency_root']]
    from human_eye_plugin import source_region
    from human_eye_plugin.scene_residency import SceneDeltaDecoder
    require(Path(source_region.__file__).resolve()==Path(installed['path']),'source_region_import_not_from_frozen_install')
    cases,pins=[],[pin(binding_path),installed]
    for case in CASES:
        receipt, inputs=real_case(case,source_region,SceneDeltaDecoder,candidate)
        cases.append(receipt)
        pins.extend(inputs)
    return {'passed':True,'installed':True,'binding_git':binding['preparation_git'],
            'product_source_sha256':binding['source_sha256'],'wheel_sha256':binding['wheel_sha256'],
            'candidate_checked':candidate,'real_cases':cases,'synthetic_controls':synthetic(source_region,candidate),
            'source_pins':pins,'new_Blender':0,'new_models':0,'new_rasters':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binding',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    started=perf_counter_ns()
    report=run(args.binding)
    report['diagnostic_elapsed_ns']=perf_counter_ns()-started
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8',newline='\n') as out:
        json.dump(report,out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        out.write('\n')
    print(json.dumps({'passed':True,'binding_git':report['binding_git'],
                      'cases':[c['label'] for c in report['real_cases']],
                      'synthetic_controls':len(report['synthetic_controls'])}),flush=True)
