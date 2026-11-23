"""Qualify both shared ordinary client paths with the sealed assembly source."""

import argparse
import json
from fractions import Fraction
from inspect import getsource
from itertools import product
from math import dist
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
INDEX = V/'m4_cross_scale_assembly_transfer_001/RUNTIME_INDEX.json'
prior = run_path(str(RETAINED))
read, save, pin, require = (prior[key] for key in ('read', 'save', 'pin', 'require'))
SOURCE_ROOT = Path('D:/he_m4_cross_scale_assembly_transfer_001')
TERMINAL_MEMBER = 'slots/P1/TERMINAL_SOURCE.json'
ASSET_MEMBER = 'slots/P1/native/input.blend'
TERMINAL_SHA = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
ARCHIVE_SHA = 'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627'
BOXES = {
    'N19': ((.449, .135, .690), (.490, .174, .751)),
    'N25': ((-.131, -.291, .295), (.011, -.250, .373)),
}
REFERENCES = {'N19':'N14', 'N25':'N07'}
EXPECTED = {
    'N19': (list(range(10, 20)), 12, .044500013813, (1, 0, 0)),
    'N25': (list(range(8)), 8, .414366994068, (0, .941194701330, .337864668453)),
}
LABELS = ('N1', 'P1')


def original_source():
    index = read(INDEX)
    archive = SOURCE_ROOT/'ORIGINAL_RUNTIME.zip'
    listing = {row['path']:row for row in index['files']}
    require(len(listing) == index['count'] == 789 and
            pin(archive) == index['archive'] and index['archive']['sha256'] == ARCHIVE_SHA,
            'assembly_original_archive_identity_changed')
    pins = [pin(INDEX), index['archive']]
    originals = {}
    with ZipFile(archive) as preserved:
        for name in (TERMINAL_MEMBER, ASSET_MEMBER, 'slots/P1/SLOT_RESULT.json', 'slots/P1/SLOT_PUBLICATION.json'):
            path = SOURCE_ROOT/name
            current = pin(path)
            require(current['sha256'] == listing[name]['sha256'] and current['bytes'] == listing[name]['bytes']
                    and path.read_bytes() == preserved.read(name), 'original_member_not_preserved/'+name)
            pins.append(current)
            originals[name] = current
    ts = originals[TERMINAL_MEMBER]
    require((ts['bytes'], ts['sha256']) == (154_323, TERMINAL_SHA)
            and (originals[ASSET_MEMBER]['bytes'], originals[ASSET_MEMBER]['sha256']) == (106_640, ASSET_SHA),
            'fixed_assembly_source_or_asset_changed')
    result = read(SOURCE_ROOT/'slots/P1/SLOT_RESULT.json')
    publication = read(SOURCE_ROOT/'slots/P1/SLOT_PUBLICATION.json')
    require(result['status'] == publication['status'] == 'completed'
            and publication['result_sha256'] == originals['slots/P1/SLOT_RESULT.json']['sha256']
            and result['terminal_source']['sha256'] == TERMINAL_SHA
            and result['independent_before_after']['passed'] and result['closure_verification']['passed'],
            'original_assembly_source_not_from_closed_preserved_slot')
    terminal = read(SOURCE_ROOT/TERMINAL_MEMBER)
    meshes = terminal['objects']
    offsets = [0]
    for obj in meshes:
        offsets.append(offsets[-1]+len(obj['evaluated']['triangles']))
    require(terminal['source']['asset_sha256'] == ASSET_SHA and terminal['source']['scale_length'] == 1.0
            and len(meshes) == 28 and sum(len(x['evaluated']['vertices_world_m']) for x in meshes) == 416
            and offsets[-1] == 744 and offsets == terminal['source_face_offsets']
            and [True]*28 == terminal['display_object_mask'], 'assembly_shape_or_display_changed')
    return terminal, pins


def axis_witness_candidates(a, b):
    """Minimizing coordinate pairs for the two point-set bounding intervals."""
    lo_a, hi_a, lo_b, hi_b = min(a), max(a), min(b), max(b)
    if hi_a < lo_b:
        return [(hi_a, lo_b)]
    if hi_b < lo_a:
        return [(lo_a, hi_b)]
    low, high = max(lo_a, lo_b), min(hi_a, hi_b)
    candidates = sorted({low, high, (low+high)/2, *(v for v in [*a, *b] if low <= v <= high)})
    return [(v, v) for v in candidates]


def independent_truth(terminal):
    oracle = run_path(str(ORACLE))
    meshes = {obj['name']:obj for obj in terminal['objects']}
    regions = {}
    for name, bounds in BOXES.items():
        actor, target = (meshes[key] for key in (name, REFERENCES[name]))
        for obj in (actor, target):
            evaluate = obj['evaluated']
            transformed = oracle['transform'](evaluate['vertices'], obj['matrix_world'], 1)
            require(oracle['near_world'](evaluate['vertices_world_m'], transformed),
                    'mapped_and_captured_world_disagree/'+obj['name'])
        source, reference = (obj['evaluated'] for obj in (actor, target))
        a, b = (row['vertices_world_m'] for row in (source, reference))
        faces, vertices = oracle['selected_indices'](a, source['triangles'], bounds)
        expected, point_count, distance, direction = EXPECTED[name]
        require(faces == expected and len(vertices) == point_count, 'fixed_source_region_changed/'+name)
        low_bound = None
        for pairs in product(*(axis_witness_candidates([a[i][axis] for i in vertices], [v[axis] for v in b])
                               for axis in range(3))):
            pa, pb = zip(*pairs, strict=True)
            matches_a = [i for i in faces if oracle['triangle_contains'](pa, [a[v] for v in source['triangles'][i]])]
            matches_b = [i for i, face in enumerate(reference['triangles'])
                         if oracle['triangle_contains'](pb, [b[v] for v in face])]
            if matches_a and matches_b:
                delta = [Fraction(y)-Fraction(x) for x,y in zip(pa,pb,strict=True)]
                low_bound = sum(d*d for d in delta)
                require(abs(dist(pa,pb)-distance)<1e-12 and all(abs(float(d)/distance-e)<1e-10
                        for d,e in zip(delta,direction,strict=True)), 'wrong_surface_bound/'+name)
                break
        require(low_bound is not None, 'no_surface_witness_for_separating_box_bound/'+name)
        regions[name] = {'native': {'triangle_ids':faces, 'triangle_count':len(faces),
            'vertex_count':len(vertices), 'distance_m':dist(pa,pb),
            'direction_world': [float(d)/dist(pa,pb) for d in delta], 'a':list(pa), 'b':list(pb),
            'witness_triangle_ids':[matches_a, matches_b],
            'meets_threshold': low_bound >= Fraction(7,20)**2}}
    require(not regions['N19']['native']['meets_threshold'] and
            regions['N25']['native']['meets_threshold'], 'threshold_order_changed')
    return regions


def retained_ordinary(catalogue, raw):
    text = dedent(getsource(prior['ordinary']))
    begin = text.index('        numeric = execute(')
    end = text.index('        call(\'invalid-crop-rejected\'',begin)
    text = text[:begin]+'''        numeric = execute('source-rows-in-persistent-session', measurement_code)
'''+text[end:]
    begin = text.index('        rendered = execute(')
    end = text.index('        blocks = call(',begin)
    text = text[:begin]+'''        rendered = execute('local-both-and-pixel-source-from-buffer', render_code)
'''+text[end:]
    begin = text.index('                witnessed = sample_pixels(')
    end = text.index('            frames[side]',begin)
    text = text[:begin]+'''                index = frame['object_names'].index(side)
                require(index == object_indices[side] and list(value['face_patch_offsets']) == raw['source_face_offsets']
                        and value['display_object_mask'].tolist() == raw['display_object_mask'],
                        'ordinary_frame_owner_domain_changed/'+side)
                owner_buffer = value['owners']
                face_ids = value['triangle_ids']
                offset = raw['source_face_offsets'][index]
                included = (owner_buffer == index) & np.isin(face_ids, np.asarray(truth[side]['native']['triangle_ids'])+offset)
                locations = np.argwhere(included)
                require(len(locations)>0, 'ordinary_zero_selected_pixels/'+side)
                row, col = (int(n) for n in locations[len(locations)//2])
                require(capsule['selected_pixels']==len(locations)
                        and capsule['sampled_source_rows']==len(np.unique(face_ids[included]))
                        and capsule['sample_row_column_source']==[row,col,int(face_ids[row,col])-offset],
                        'ordinary_same_frame_current_source_pixel_not_verified/'+side)
'''+text[end:]
    contains = getsource(run_path(str(ORACLE))['triangle_contains'])
    measurement = f"""
import json
from itertools import product
from fractions import Fraction
{contains}
source = scene_data()
meshes = {{obj['name']: obj for obj in source['objects']}}
boxes = {BOXES!r}
references = {REFERENCES!r}
ids = {{}}
vertices = {{}}
faces = {{}}
counts = {{}}
for name, (lo, hi) in boxes.items():
    obj, target = meshes[name], meshes[references[name]]
    a = np.asarray(obj['vertices'])
    af = np.asarray(obj['triangles'])
    b = np.asarray(target['vertices'])
    bf = np.asarray(target['triangles'])
    inside = ((a>=lo)&(a<=hi)).all(axis=1)
    rows = np.flatnonzero(inside[af].all(axis=1))
    selected = np.unique(af[rows])
    ids[name], vertices[name], faces[name] = rows, a, af
    axes = []
    for av,bv in zip(a[selected].T,b.T):
        amin,amax,bmin,bmax = av.min(),av.max(),bv.min(),bv.max()
        if amax < bmin:
            axes.append([(amax,bmin)])
        elif bmax < amin:
            axes.append([(amin,bmax)])
        else:
            lower,upper = max(amin,bmin),min(amax,bmax)
            axes.append([(x,x) for x in sorted({{lower,upper,(lower+upper)/2,*(t for t in np.r_[av,bv] if lower<=t<=upper)}})])
    for pairs in product(*axes):
        p,q = map(np.asarray,zip(*pairs))
        if (any(triangle_contains(p.tolist(),t.tolist()) for t in a[af[rows]])
                and any(triangle_contains(q.tolist(),t.tolist()) for t in b[bf])):
            break
    else:
        raise ValueError('no_surface_point_pair/'+name)
    distance = np.linalg.norm(q-p)
    counts[name] = {{'triangle_count':len(rows),'vertex_count':len(selected),'triangle_ids':rows.tolist(),
                    'distance_m':float(distance),'a':p.tolist(),'b':q.tolist(),'direction':((q-p)/distance).tolist()}}
print(json.dumps(counts))
"""
    rendering = """
images = {}
for name, direction in (('N19','TOP'), ('N25','SCENE')):
    points = vertices[name][np.unique(faces[name][ids[name]])]
    focus = ((points.min(axis=0)+points.max(axis=0))/2).tolist()
    frame = render_local(direction,focus,.25)
    arrays = buffers[frame['ref']]
    index = frame['object_names'].index(name)
    offset = frame['source_face_offsets'][index]
    triangle_ids = arrays['triangle_ids']
    selected = (arrays['owners']==index)&np.isin(triangle_ids,ids[name]+offset)
    locations = np.argwhere(selected)
    row,col = map(int, locations[len(locations)//2])
    images[name] = {'ref':frame['ref'],'view':direction,'selected_pixels':len(locations),
                    'sampled_source_rows':len(np.unique(triangle_ids[selected])),
                    'sample_row_column_source':[row,col,int(triangle_ids[row,col])-offset]}
print(json.dumps(images))
"""
    scope = dict(prior, BOXES=BOXES, ASSET_SHA=ASSET_SHA, CATALOGUE=catalogue, RUNTIME=HERE,
                 measurement_code=measurement, render_code=rendering,
                 object_indices={obj['name']:i for i,obj in enumerate(raw['objects'])})
    exec(compile(text,str(RETAINED),'exec'),scope)
    return scope['ordinary']


def arm(host,label,directory):
    terminal,source_pins = original_source()
    truth = independent_truth(terminal)
    raw = {key:terminal[key] for key in ('source','display_object_mask','source_face_offsets','layer_collections','scene_cameras')}
    raw.update(source_ref='offline-preserved-assembly-terminal-source',objects=[])
    by_name = {}
    for obj in terminal['objects']:
        row = {key:obj[key] for key in ('object_id','instance_id','name','mesh_name','matrix_world','visible_get','display')}
        ev = obj['evaluated']
        row.update(vertices=ev['vertices_world_m'],triangles=ev['triangles'],polygon_count=ev['polygon_count'])
        raw['objects'].append(row)
        by_name[obj['name']] = row
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
    current_observe, = [row for row in read(catalogue) if row['name']==bridge.PRODUCT_TOOL]
    current = folder/label
    result = retained_ordinary(catalogue,raw)(current,label[0],raw,truth,np)
    require(result['tools'] == (bridge.TOOLS if label=='N1' else [*bridge.TOOLS,current_observe]),
            'ordinary_wire_catalogue_not_current_arm')
    oracle = run_path(str(ORACLE))
    for name,value in result['quantities'].items():
        expected = truth[name]['native']
        a,b = by_name[name],by_name[REFERENCES[name]]
        supports_a = [i for i in expected['triangle_ids'] if oracle['triangle_contains'](
            value['a'], [a['vertices'][v] for v in a['triangles'][i]])]
        supports_b = [i for i,face in enumerate(b['triangles']) if oracle['triangle_contains'](
            value['b'], [b['vertices'][v] for v in face])]
        require(supports_a and supports_b and value['triangle_count']==expected['triangle_count']
                and value['vertex_count']==expected['vertex_count'] and value['triangle_ids']==expected['triangle_ids']
                and abs(dist(value['a'],value['b'])-expected['distance_m'])<1e-12
                and abs(value['distance_m']-expected['distance_m'])<1e-12
                and np.allclose(value['direction'],expected['direction_world'],atol=1e-12,rtol=0)
                and (value['distance_m']>=.35) is expected['meets_threshold'],
                'ordinary_point_pair_or_threshold_changed/'+name)
        value.update(witness_triangle_ids=[supports_a,supports_b],meets_threshold=expected['meets_threshold'])
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
        require(proof['passed'] and proof['arm']==label
                and proof['actual_Blender']==proof['actual_models']==proof['product_calls']==0
                and proof['calls']==4 and proof['geometry_reads']==1 and proof['rasters']==2,
                'actual_ordinary_preflight_incomplete/'+label)
        arms[label] = proof
        for row in [*proof['source_pins'],pin(receipt)]:
            require(pins.setdefault(row['path'],row)==row,'ordinary_input_changed_between_arms')
    n,p = (arms[label] for label in LABELS)
    require(n['tools']==p['tools'][:-1] and n['quantities']==p['quantities'],
            'ordinary_capability_or_measurement_differs')
    require(all(n['frames'][side]['PNG']['sha256']==p['frames'][side]['PNG']['sha256']
                and all(n['frames'][side][key]==p['frames'][side][key]
                        for key in ('selected_pixels','sampled_source_rows','sample_row_column_source'))
                for side in BOXES),'ordinary_pixel_evidence_differs_between_arms')
    save(directory/'SUMMARY.json',{'passed':True,'arms':arms,'Blender':0,'models':0,
         'product_calls':0,'offline_ordinary_calls':8,'offline_native_rasters':4,'source_pins':list(pins.values())})
    print(directory/'SUMMARY.json',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode
            and pin(sys.executable)['sha256']==prior['PYTHON_SHA'],'fixed_offline_python_required')
    sys.path.insert(0,str(HERE))
    import host

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=host.RUN/'preflight/ordinary_verified')
    parser.add_argument('--arm',choices=LABELS)
    args = parser.parse_args()
    output = args.output.resolve()
    preflight = (host.RUN/'preflight').resolve()
    require(output.is_relative_to(preflight) and output!=preflight,'ordinary_offline_namespace_required')
    if args.arm:
        arm(host,args.arm,output)
    else:
        main(output)
