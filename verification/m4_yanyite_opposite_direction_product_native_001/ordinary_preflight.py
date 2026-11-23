"""Qualify the common ordinary tools on the sealed opposite-direction regions."""

import argparse
from fractions import Fraction
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from textwrap import dedent
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
RETAINED = V/'m4_yanyite_bilateral_region_native_001/data_preflight.py'
ORACLE = V/'m4_yanyite_dual_curved_region_native_001/score/oracle.py'
ordinary_path = run_path(str(RETAINED))
read, save, pin, require = (ordinary_path[key] for key in ('read','save','pin','require'))
SOURCE_ROOT = Path('D:/he_m1_yanyite_foot_region_image_evidence_consumption_001')
SOURCE_MEMBER = 'slots/B1/TERMINAL_SOURCE.json'
TERMINAL_SHA = 'f52fc746cea933725ffe5a0c7602b2893914c331b427b83366259b283de1f5fb'
ARCHIVE_SHA = '09adac87dd0405385a30a4f04dd7831ee17dcfb56323c27f07189384e2b355c7'
BOXES = {
    'negative_y': ((-.08,-.112,0),(.08,-.09,.05)),
    'positive_y': ((-.08,.085,0),(.08,.105,.05)),
}
EXPECTED = {
    'negative_y': (301,225,0.8884277344390303,-1,
                   'c5094b937cdc4e22d516efe7cfca999b6ed36fa22956038b693e2d848b60310d'),
    'positive_y': (136,107,0.8952636703382715,1,
                   'c35941e6477bef1347e6e034b0526f792bba981cdc364da2a1b3d969a934eab5'),
}
THRESHOLD = Fraction(223,250)
LABELS = ('N1','P1')


def retained_ordinary(catalogue):
    text = dedent(getsource(ordinary_path['ordinary']))
    original = "(('left','LEFT'), ('right','RIGHT'))"
    require(text.count(original) == 1, 'retained_ordinary_crop_anchor_changed')
    text = text.replace(original, "(('negative_y','RIGHT'), ('positive_y','SCENE'))")
    scope = dict(ordinary_path, BOXES=BOXES, CATALOGUE=catalogue, RUNTIME=HERE)
    exec(compile(text,str(RETAINED),'exec'),scope)
    return scope['ordinary']


def frozen_source():
    terminal = SOURCE_ROOT/SOURCE_MEMBER
    index = SOURCE_ROOT/'sealed/RAW_INDEX.json'
    archive = SOURCE_ROOT/'sealed/ORIGINAL_RUNTIME.zip'
    terminal_pin, archive_pin = pin(terminal),pin(archive)
    listing = read(index)
    require(terminal_pin['sha256'] == TERMINAL_SHA and terminal_pin['bytes'] == 9_614_533
            and archive_pin['sha256'] == ARCHIVE_SHA and listing['archive'] == archive_pin
            and listing['member_count'] == 1184
            and listing['members'][SOURCE_MEMBER] == {'bytes':terminal_pin['bytes'],'sha256':TERMINAL_SHA},
            'fixed_archived_terminal_identity_changed')
    raw = terminal.read_bytes()
    with ZipFile(archive) as preserved:
        require(raw == preserved.read(SOURCE_MEMBER), 'fixed_archived_terminal_bytes_changed')
    return json.loads(raw),[terminal_pin,pin(index),archive_pin]


def independent_truth(terminal):
    oracle = run_path(str(ORACLE))
    actor,cube = terminal['objects']
    captured = actor['evaluated']['vertices_world_m']
    native = actor['evaluated']['vertices']
    triangles = actor['evaluated']['triangles']
    reference = cube['evaluated']['vertices_world_m']
    cube_triangles = cube['evaluated']['triangles']
    mapped = oracle['transform'](native,actor['matrix_world'],1)
    require(oracle['near_world'](captured,mapped), 'ordinary_mapped_and_captured_world_disagree')
    low,high,covered = oracle['boxed_reference'](reference,cube_triangles)
    require(terminal['source']['asset_sha256'] == ordinary_path['ASSET_SHA']
            and (actor['name'],cube['name']) == (ordinary_path['TARGET'],'Cube')
            and terminal['display_object_mask'] == [True,False]
            and terminal['source_face_offsets'] == [0,53264,53276], 'ordinary_source_or_display_changed')
    regions = {}
    for side, bounds in BOXES.items():
        triangles_expected,points_expected,meters,sign,digest = EXPECTED[side]
        faces,vertices = oracle['selected_indices'](captured,triangles,bounds)
        require((faces,vertices) == oracle['selected_indices'](mapped,triangles,bounds)
                and (len(faces),len(vertices)) == (triangles_expected,points_expected)
                and sha256(json.dumps(faces,separators=(',',':')).encode()).hexdigest() == digest,
                'ordinary_frozen_source_rows_changed/'+side)
        minima = [min(captured[i][axis] for i in vertices) for axis in range(3)]
        maxima = [max(captured[i][axis] for i in vertices) for axis in range(3)]
        gaps = [Fraction(a)-Fraction(b) for a,b in zip(minima,low,strict=True)]
        gaps += [Fraction(a)-Fraction(b) for a,b in zip(high,maxima,strict=True)]
        nearest = min(gaps)
        plane = 0 if sign < 0 else 1
        require(all(gap > 0 for gap in gaps) and gaps.count(nearest) == 1
                and gaps.index(nearest) == 3*plane+1 and abs(float(nearest)-meters) < 1e-12,
                'ordinary_opposite_world_reference_not_proved/'+side)
        extreme = (minima,maxima)[plane][1]
        point = next(captured[i] for i in vertices if captured[i][1] == extreme)
        on_cube = [point[0],(low,high)[plane][1],point[2]]
        supporting_rows = [i for i in covered[plane,1]
                           if oracle['triangle_contains'](on_cube,[reference[j] for j in cube_triangles[i]])]
        require(supporting_rows and abs(Fraction(on_cube[1])-Fraction(point[1])) == nearest,
                'ordinary_cube_surface_witness_not_proved/'+side)
        regions[side] = {'native':{'triangle_count':len(faces),'triangle_ids':faces,'vertex_count':len(vertices),
            'distance_m':float(nearest),'direction_world':[0,sign,0],
            'a':point,'b':on_cube,'cube_witness_triangle_ids':supporting_rows,'meets_threshold':nearest >= THRESHOLD}}
    require(regions['negative_y']['native']['distance_m'] < regions['positive_y']['native']['distance_m']
            and not regions['negative_y']['native']['meets_threshold'] and regions['positive_y']['native']['meets_threshold'],
            'ordinary_threshold_or_region_order_changed')
    return regions


def arm(host,label,directory):
    terminal,source_pins = frozen_source()
    truth = independent_truth(terminal)
    raw = {key:terminal[key] for key in ('source','display_object_mask','source_face_offsets','layer_collections','scene_cameras')}
    raw.update(source_ref='offline-preserved-opposite-direction-current-source', objects=[])
    for obj in terminal['objects']:
        row = {key:obj[key] for key in ('object_id','instance_id','name','mesh_name','matrix_world','visible_get','display')}
        evaluated = obj['evaluated']
        row.update(vertices=evaluated['vertices_world_m'],triangles=evaluated['triangles'],
                   polygon_count=evaluated['polygon_count'])
        raw['objects'].append(row)
    folder = directory/label/'slots'
    folder.mkdir(parents=True,exist_ok=False)
    _,_,bridge,_,binding = host.runtime_graph(folder.parent,label)
    sys.path.insert(0,binding['install_root'])
    import numpy as np
    import human_eye_plugin.attention_raster as raster

    runtime = Path(raster.__file__).resolve(strict=True)
    require(runtime.is_relative_to(Path(binding['install_root']).resolve(strict=True)),
            'ordinary_raster_not_from_current_install')
    catalogue = host.catalogue_path('P1')
    current_observe, = [row for row in read(catalogue) if row['name'] == bridge.PRODUCT_TOOL]
    current = folder/label
    result = retained_ordinary(catalogue)(current,label[0],raw,truth,np)
    expected_tools = bridge.TOOLS if label == 'N1' else [*bridge.TOOLS,current_observe]
    require(result['tools'] == expected_tools, 'ordinary_wire_catalogue_not_current_arm')
    for side,value in result['quantities'].items():
        expected = truth[side]['native']
        require(value['triangle_count'] == expected['triangle_count']
                and np.allclose(value['a'],expected['a'],rtol=0,atol=1e-12)
                and np.allclose(value['b'],expected['b'],rtol=0,atol=1e-12)
                and (value['distance_m'] >= THRESHOLD) is expected['meets_threshold'],
                'ordinary_point_pair_or_threshold_changed/'+side)
        value['meets_threshold'] = expected['meets_threshold']
    owner_result = current/'owner/BRIDGE_RESULT.json'
    rows = read(owner_result)['calls']
    require([(row['name'],row['is_error']) for row in rows] == [
        ('execute_python',False),('render_local',True),('execute_python',False),('read_images',False)],
        'ordinary_read_render_recovery_or_png_delivery_changed')
    result.update(passed=True,arm=label,actual_Blender=0,actual_models=0,product_calls=0,
                  product_git=binding['preparation_git'],product_source_sha256=binding['source_sha256'],
                  owner_result=pin(owner_result),source_pins=[*source_pins,*(pin(path) for path in (
                      Path(__file__),RETAINED,ORACLE,HERE/'host.py',HERE/'thin_stdio.py',catalogue,runtime,Path(sys.executable)))])
    save(directory/label/'ARM.json',result)


def main(directory):
    directory.mkdir(parents=True,exist_ok=False)
    arms,pins = {},{}
    for label in LABELS:
        process = subprocess.run([sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),
                                  '--output',str(directory),'--arm',label],
                                 cwd=V.parent,capture_output=True,timeout=140)
        (directory/(label+'_STDOUT.bin')).write_bytes(process.stdout)
        (directory/(label+'_STDERR.bin')).write_bytes(process.stderr)
        require(process.returncode == 0,'actual_ordinary_preflight_failed/'+label)
        receipt = directory/label/'ARM.json'
        proof = read(receipt)
        require(proof['passed'] and proof['arm'] == label
                and proof['actual_Blender'] == proof['actual_models'] == proof['product_calls'] == 0
                and proof['calls'] == 4 and proof['geometry_reads'] == 1 and proof['rasters'] == 2,
                'actual_ordinary_preflight_incomplete/'+label)
        arms[label] = proof
        for row in [*proof['source_pins'],pin(receipt)]:
            require(pins.setdefault(row['path'],row) == row,'ordinary_input_changed_between_arms')
    n,p = (arms[label] for label in LABELS)
    require(n['tools'] == p['tools'][:-1] and n['quantities'] == p['quantities'],
            'ordinary_capability_or_measurement_differs')
    require(all(n['frames'][side]['PNG']['sha256'] == p['frames'][side]['PNG']['sha256']
                and all(n['frames'][side][key] == p['frames'][side][key]
                        for key in ('selected_pixels','sampled_source_rows','sample_row_column_source'))
                for side in BOXES),'ordinary_pixel_evidence_differs_between_arms')
    save(directory/'SUMMARY.json',{'passed':True,'arms':arms,'Blender':0,'models':0,
         'product_calls':0,'offline_ordinary_calls':8,'offline_native_rasters':4,'source_pins':list(pins.values())})
    print(directory/'SUMMARY.json',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode
            and pin(sys.executable)['sha256'] == ordinary_path['PYTHON_SHA'],'fixed_offline_python_required')
    sys.path.insert(0,str(HERE))
    import host

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=host.RUN/'preflight/ordinary')
    parser.add_argument('--arm',choices=LABELS)
    args = parser.parse_args()
    output = args.output.resolve()
    preflight = (host.RUN/'preflight').resolve()
    require(output.is_relative_to(preflight) and output != preflight,'ordinary_offline_namespace_required')
    if args.arm:
        arm(host,args.arm,output)
    else:
        main(output)
