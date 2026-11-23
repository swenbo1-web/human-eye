"""Replay the common ordinary client with the frozen foot-region source."""

import argparse
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from textwrap import dedent
from inspect import getsource


HERE = Path(__file__).resolve().parent
V = HERE.parent
RETAINED = V/'m4_yanyite_bilateral_region_native_001/data_preflight.py'
retained = run_path(str(RETAINED))
read, save, pin, require = (retained[key] for key in ('read','save','pin','require'))
TERMINAL = Path('D:/he_m4_yanyite_low_bilateral_product_native_001/slots/P1/TERMINAL_SOURCE.json')
TERMINAL_SHA = 'f022aa6addb84c34bff78bf077765c97951ac2f47a969d1684796d828dae9eea'
LABELS = ('A1','B1')


def retained_ordinary(label, boxes, catalogue):
    # The old ordinary proof ran as N1 and P1. Here both registered slots
    # expose the same ordinary tools and their corresponding installed tool.
    text = dedent(getsource(retained['ordinary']))
    for before,after,count in (
        ("group+'1'", 'registered_label', 2),
        ("(('left','LEFT'), ('right','RIGHT'))", "(('negative_y','FRONT'), ('positive_y','BACK'))", 1),
    ):
        require(text.count(before) == count, 'retained_ordinary_entry_anchor_changed')
        text = text.replace(before,after)
    scope = dict(retained, registered_label=label, BOXES=boxes, CATALOGUE=catalogue, RUNTIME=HERE)
    exec(compile(text, str(RETAINED), 'exec'), scope)
    return scope['ordinary']


def arm(host, label, directory):
    from score import BOXES

    proof = host.RUN/'preflight/FOOT_TRUTH_FINAL.json'
    truth = read(proof)
    require(truth['passed'] and truth['source'] == pin(TERMINAL)
            and truth['source']['sha256'] == TERMINAL_SHA and truth['source']['bytes'] == 9_614_519
            and set(truth['regions']) == set(BOXES), 'fixed_foot_geometry_required')
    folder = directory/label/'slots'
    folder.mkdir(parents=True, exist_ok=False)
    _, _, bridge, _, binding = host.runtime_graph(folder.parent,label)
    sys.path.insert(0,binding['install_root'])
    import numpy as np
    import human_eye_plugin.attention_raster as raster

    runtime = Path(raster.__file__).resolve(strict=True)
    require(runtime.is_relative_to(Path(binding['install_root']).resolve(strict=True)), 'ordinary_raster_not_from_current_install')
    terminal = read(TERMINAL)
    raw = {key:terminal[key] for key in ('source','display_object_mask','source_face_offsets','layer_collections','scene_cameras')}
    raw.update(source_ref='offline-preserved-foot-region-current-source', objects=[])
    for obj in terminal['objects']:
        row = {key:obj[key] for key in ('object_id','instance_id','name','mesh_name','matrix_world','visible_get','display')}
        evaluated = obj['evaluated']
        row.update(vertices=evaluated['vertices_world_m'],triangles=evaluated['triangles'],
                   polygon_count=evaluated['polygon_count'])
        raw['objects'].append(row)
    require(raw['display_object_mask'] == [True,False]
            and raw['source_face_offsets'] == [0,53264,53276], 'ordinary_display_participation_changed')
    catalogue = host.catalogue_path(label)
    current_observe, = [r for r in read(catalogue) if r['name'] == bridge.PRODUCT_TOOL]
    expected = {side:{'native':value} for side,value in truth['regions'].items()}
    current = folder/label
    result = retained_ordinary(label,boxes=BOXES,catalogue=catalogue)(current,'P',raw,expected,np)
    require(result['tools'] == [*bridge.TOOLS,current_observe], 'ordinary_wire_catalogue_not_current_install')
    for side,item in result['quantities'].items():
        known = truth['regions'][side]
        require(item['triangle_count'] == known['triangle_count']
                and np.allclose(item['a'],known['source_point_world_m'],rtol=0,atol=1e-12)
                and np.allclose(item['b'],known['reference_point_world_m'],rtol=0,atol=1e-12),
                'ordinary_point_pair_not_independently_bound/'+side)
        item['signed_margin_m'] = item['distance_m']-truth['threshold_m']
        item['meets_threshold'] = item['distance_m'] >= truth['threshold_m']
        require(item['meets_threshold'] is known['at_least_0_82_m'], 'ordinary_threshold_changed/'+side)
    owner_result = current/'owner/BRIDGE_RESULT.json'
    rows = read(owner_result)['calls']
    require([(row['name'],row['is_error']) for row in rows] == [
        ('execute_python',False),('render_local',True),('execute_python',False),('read_images',False)],
        'ordinary_read_render_recovery_or_png_delivery_changed')
    result.update({'passed':True,'arm':label,'actual_Blender':0,'actual_models':0,
                   'product_calls':0,'product_git':binding['preparation_git'],
                   'product_source_sha256':binding['source_sha256'],'owner_result':pin(owner_result),
                   'source_pins':[pin(path) for path in (
                       Path(__file__),RETAINED,TERMINAL,proof,HERE/'score.py',HERE/'host.py',
                       HERE/'thin_stdio.py',catalogue,runtime,Path(sys.executable))]})
    save(directory/label/'ARM.json',result)


def main(host,directory):
    directory.mkdir(parents=True,exist_ok=False)
    arms,source_pins = {},{}
    for label in LABELS:
        process = subprocess.run([sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),
                                  '--output',str(directory),'--arm',label],
                                 cwd=V.parent,capture_output=True,timeout=140)
        (directory/(label+'_STDOUT.bin')).write_bytes(process.stdout)
        (directory/(label+'_STDERR.bin')).write_bytes(process.stderr)
        require(process.returncode == 0, 'actual_ordinary_preflight_failed/'+label)
        receipt = directory/label/'ARM.json'
        proof = read(receipt)
        require(proof['passed'] and proof['arm'] == label
                and proof['actual_Blender'] == proof['actual_models'] == proof['product_calls'] == 0
                and proof['calls'] == 4 and proof['geometry_reads'] == 1 and proof['rasters'] == 2,
                'actual_ordinary_preflight_incomplete/'+label)
        arms[label] = proof
        for row in [*proof['source_pins'],pin(receipt)]:
            require(source_pins.setdefault(row['path'],row) == row,'ordinary_input_changed_between_arms')

    a,b = (arms[label] for label in LABELS)
    product_tool = 'human_eye_scene_observe'
    ordinary = lambda result: [r for r in result['tools'] if r['name'] != product_tool]
    require(ordinary(a) == ordinary(b) and a['quantities'] == b['quantities'],'ordinary_capability_or_measurement_differs')
    require(all(a['frames'][side]['PNG']['sha256'] == b['frames'][side]['PNG']['sha256']
                and all(a['frames'][side][key] == b['frames'][side][key]
                        for key in ('selected_pixels','sampled_source_rows','sample_row_column_source'))
                for side in a['frames']), 'ordinary_pixel_evidence_differs_between_arms')
    save(directory/'SUMMARY.json',{'passed':True,'arms':arms,'Blender':0,'models':0,
                                   'product_calls':0,'offline_ordinary_calls':8,'offline_native_rasters':4,
                                   'source_pins':list(source_pins.values())})
    print(directory/'SUMMARY.json',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode
            and pin(Path(sys.executable))['sha256'] == retained['PYTHON_SHA'],'fixed_offline_python_required')
    sys.path.insert(0,str(HERE))
    import host

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=host.RUN/'preflight/ordinary_final')
    parser.add_argument('--arm',choices=LABELS)
    args = parser.parse_args()
    output = args.output.resolve()
    preflight = (host.RUN/'preflight').resolve()
    require(output.is_relative_to(preflight) and output != preflight,'ordinary_offline_namespace_required')
    if args.arm:
        arm(host,args.arm,output)
    else:
        main(host,output)
