"""Prove the current common client can publish both original local frames."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import host
from score import BOXES, load, pin, require, write


ROOT = host.RUN/'preflight/ordinary_v2'
OUTPUT = ROOT/'SUMMARY.json'
SOURCE = Path('D:/he_m4_yanyite_bilateral_region_native_001/slots/P1/TERMINAL_SOURCE.json')
OLD = HERE.parent/'m4_yanyite_bilateral_region_native_001/data_preflight.py'


def main(truth):
    require(truth['passed'] and pin(SOURCE) == truth['source'], 'same_current_ordinary_truth_required')
    ROOT.mkdir(exist_ok=False)
    _, _, _, _, binding = host.runtime_graph(ROOT, 'N1')
    sys.path.insert(0, binding['install_root'])
    import numpy as np

    text = OLD.read_text(encoding='utf-8')
    old_pair = "(('left','LEFT'), ('right','RIGHT'))"
    require(text.count(old_pair) == 1, 'retained_ordinary_crop_anchor_changed')
    text = text.replace(old_pair, "(('left','FRONT'), ('right','FRONT'))")
    scope = {'__file__':str(OLD), '__name__':'_archived_common_ordinary'}
    exec(compile(text, str(OLD), 'exec'), scope)
    ordinary = scope['ordinary']
    ordinary.__globals__.update(BOXES=BOXES, CATALOGUE=HERE/'inputs/EVIDENCE_TOOLS_SCHEMA.json', RUNTIME=HERE)
    terminal = load(SOURCE)
    raw = {key: terminal[key] for key in ('source','display_object_mask','source_face_offsets','layer_collections','scene_cameras')}
    raw.update(source_ref='offline-preserved-low-bilateral-current-source', objects=[])
    for obj in terminal['objects']:
        row = {key:obj[key] for key in ('object_id','instance_id','name','mesh_name','matrix_world','visible_get','display')}
        evaluated = obj['evaluated']
        row.update(vertices=evaluated['vertices_world_m'], triangles=evaluated['triangles'],
                   polygon_count=evaluated['polygon_count'])
        raw['objects'].append(row)
    expected = {side:{'native':value} for side,value in truth['regions'].items()}
    arms = {}
    for group in ('N','P'):
        directory = ROOT/group/'slots'
        directory.mkdir(parents=True)
        arms[group] = ordinary(directory/(group+'1'), group, raw, expected, np)
    require(all(arms['N']['frames'][side]['PNG']['sha256'] == arms['P']['frames'][side]['PNG']['sha256']
                and arms['N']['quantities'][side] == arms['P']['quantities'][side] for side in BOXES),
            'ordinary_low_pair_not_equivalent')
    write(OUTPUT, {'passed':True, 'arms':arms, 'Blender':0, 'models':0,
                   'offline_native_rasters':4, 'offline_ordinary_calls':sum(arm['calls'] for arm in arms.values()),
                   'source_pins':[pin(p) for p in (Path(__file__), OLD, SOURCE, HERE/'thin_stdio.py')]})
    print(OUTPUT, flush=True)


if __name__ == '__main__':
    main(load(host.RUN/'preflight/LOW_SOURCE_TRUTH.json'))
