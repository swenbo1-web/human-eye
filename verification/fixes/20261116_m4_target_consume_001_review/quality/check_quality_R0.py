"""Independent fixed-source and actual-frame checks for six task answers."""
import base64
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = AUTHOR / 'verification/m4_target_task_consumption_001'
RUN = Path('D:/he_m4_target_consume_001/formal')
ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
CHECKS = []


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(name, condition):
    CHECKS.append(name)
    if not condition:
        raise AssertionError(name)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def table(value):
    return [dict(zip(value['columns'], row)) for row in value['rows']]


def face_ids(value):
    return [i for lo, hi in value['source_triangle_index_ranges'] for i in range(lo, hi+1)]


geometry_path = NS / 'reference/FROZEN_GEOMETRY.json'
check('fixed source geometry', sha(geometry_path) == 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da')
geometry = load(geometry_path)
objects = {o['name']: o for o in geometry['objects']}
target = objects['M4_Far_00']
points = [tuple(map(F, p)) for p in target['world_vertices_m']]
faces = target['triangles']
edge_faces = {}
for i, face in enumerate(faces):
    for a, b in zip(face, face[1:]+face[:1]):
        edge_faces.setdefault(tuple(sorted((a, b))), set()).add(i)
neighbors = [set() for _ in faces]
for incidence in edge_faces.values():
    for i in incidence:
        neighbors[i].update(incidence-{i})
unseen = set(range(len(faces)))
groups = []
while unseen:
    stack = [min(unseen)]
    component = set()
    while stack:
        i = stack.pop()
        if i in component:
            continue
        component.add(i)
        stack.extend(neighbors[i]-component)
    unseen -= component
    groups.append(sorted(component))
check('independent full connected region partition', groups == [list(range(512)), [512, 513]])
truth = {}
for group in groups:
    used = {v for i in group for v in faces[i]}
    low = tuple(min(points[v][k] for v in used) for k in range(3))
    high = tuple(max(points[v][k] for v in used) for k in range(3))
    area = F(0)
    weighted = [F(0)]*3
    normal = None
    for i in group:
        a, b, c = (points[v] for v in faces[i])
        n = cross(sub(b, a), sub(c, a))
        magnitude = sum(map(abs, n))
        axis_normal = tuple(v/magnitude for v in n)
        check('same exact axis-oriented plane', sum(v != 0 for v in n) == 1 and (normal is None or normal == axis_normal))
        normal = axis_normal
        triangle_area = magnitude/2
        area += triangle_area
        for k in range(3):
            weighted[k] += triangle_area*(a[k]+b[k]+c[k])/3
    center = tuple(v/area for v in weighted)
    truth[group[0]] = dict(ids=group, low=low, high=high, center=center, normal=normal)
    check('each independent region has unit area', area == 1)

near = [tuple(map(F, p)) for p in objects['M4_Near']['world_vertices_m']]
d = near[0][0]
check('Near exact triangle', near == [(d, 0, 0), (d, 1, 0), (d, 0, 1)] and 0 < d < 1)
occluded_area = d*d/2
check('independent LEFT shadow area', occluded_area == F(73786983304225, 9223372036854775808))
check('horizontal region above every other surface', all(F(p[2]) <= 1 for name, obj in objects.items() if name != 'M4_Far_00' for p in obj['world_vertices_m']) and max(p[2] for p in points[:289]) == 1)
device = load(NS / 'fixtures/DEVICE_CAMERAS.json')
views = {v['name']: v for v in device['views']}
classes = {0: {'SCENE': 'back_facing', 'TOP': 'edge_on', 'LEFT': 'positive_area_occlusion', 'RIGHT': 'back_facing', 'FRONT': 'edge_on', 'BACK': 'edge_on'}, 512: {v: 'complete' for v in views}}
for key, t in truth.items():
    positions = np.array([[float(x) for x in points[v]] for v in {v for i in t['ids'] for v in faces[i]}])
    h = np.column_stack((positions, np.ones(len(positions))))
    for name, pose in views.items():
        q = h @ np.asarray(pose['view_matrix']).T @ np.asarray(pose['projection_matrix']).T
        check('region fully in actual fixed frustum', bool(np.all(np.abs(q[:, :3]) < 1)))

schema = load(NS / 'inputs/ANSWER_SCHEMA.json')
schema_git = subprocess.check_output(['git', 'show', 'bfd4279e52c80e16c7909729b70569178b70587f:verification/m4_target_task_consumption_001/inputs/ANSWER_SCHEMA.json'], cwd=AUTHOR)
check('public schema frozen before formal', schema_git == (NS/'inputs/ANSWER_SCHEMA.json').read_bytes())
scoring_git = subprocess.check_output(['git', 'show', 'bfd4279e52c80e16c7909729b70569178b70587f:verification/m4_target_task_consumption_001/SCORING_PLAN.md'], cwd=AUTHOR)
check('natural language equivalence frozen before formal', scoring_git == (NS/'SCORING_PLAN.md').read_bytes() and '未知原因可由等价明确自然语言归一化'.encode() in scoring_git)

results = []
total_frames = 0
extra_views = 0
for slot in ORDER:
    folder = RUN/slot
    final_path = folder/'consumer/PUBLIC_FINAL.txt'
    raw_final = final_path.read_text(encoding='utf8')
    answer = json.loads(raw_final)
    check(slot+' required top-level fields', set(schema['required']) <= set(answer))
    check(slot+' coordinate and task binding', answer['object_name'] == 'M4_Far_00' and answer['coordinate_frame'] == 'world' and answer['unit'] == 'm' and answer['finite_view_pool_only'] is True)
    check(slot+' exact region count', len(answer['regions']) == 2)
    saved = load(folder/'SAVED_EVIDENCE.json')
    responses = [load(p) for p in sorted((folder/'owner').glob('tool_*/RESPONSE.json'))]
    blocks = [b for response in responses for b in response['result']['content']]
    delivered = [hashlib.sha256(base64.b64decode(b['data'], validate=True)).hexdigest() for b in blocks if b['type'] == 'image']
    for source in saved['sources']:
        check(slot+' current raw source hash', sha(source['path']) == source['sha256'])
        current = load(source['path'])
        for obj in current['objects']:
            expected = objects[obj['name']]
            check(slot+' raw current source points/faces', [[F(x) for x in p] for p in obj['vertices_world']] == [list(map(F, p)) for p in expected['world_vertices_m']] and obj['triangles'] == expected['triangles'])
    if slot.startswith('P'):
        actual = json.loads(responses[0]['result']['content'][0]['text'])
        public_regions = {r['roi_id']: r for r in table(actual['regions'])}
        check(slot+' actual brief consumed', actual['schema'] == 'active-observation-brief-v5' and actual['binding']['runtime_source_sha256'] == '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be')
        cited_hashes = [v for k, v in actual['binding'].items() if k.endswith('sha256') and type(v) is str]
        check(slot+' current explicit public binding citation', any(v in raw_final for v in cited_hashes))
    pixels = {}
    for frame in saved['frames']:
        check(slot+' NPZ/PNG actual hashes', sha(frame['NPZ']) == frame['NPZ_sha256'] and sha(frame['PNG']) == frame['PNG_sha256'])
        with np.load(frame['NPZ'], allow_pickle=False) as arrays:
            color, ids = arrays['color'].copy(), arrays['triangle_ids'].copy()
            owners = arrays['owners'].copy()
        check(slot+' PNG independently decoded', np.array_equal(color, np.asarray(Image.open(frame['PNG']))))
        names = frame['object_names']
        offsets = frame['source_face_offsets']
        target_index = names.index('M4_Far_00')
        offset = offsets[target_index]
        check(slot+' actual full source-face offsets', offsets == list(np.cumsum([0]+[len(objects[n]['triangles']) for n in names])))
        for key, t in truth.items():
            mask = (ids >= offset+t['ids'][0]) & (ids <= offset+t['ids'][-1])
            check(slot+' owner/source triangle agreement', bool(np.all(owners[mask] == target_index)))
            boundary = np.zeros(mask.shape, dtype=bool)
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                ys, ye = max(0, -dy), min(512, 512-dy)
                xs, xe = max(0, -dx), min(512, 512-dx)
                a = (slice(ys, ye), slice(xs, xe))
                b = (slice(ys+dy, ye+dy), slice(xs+dx, xe+dx))
                delta = color[a].astype(np.int32)-color[b].astype(np.int32)
                boundary[a] |= mask[a] & ~mask[b] & (np.sum(delta*delta, axis=2) >= 24**2)
            pixels[(frame['ref'], key)] = dict(surface=int(mask.sum()), boundary=int(boundary.sum()), view=frame['view_name'], png=frame['PNG_sha256'])
        total_frames += 1
    region_rows = []
    seen = set()
    for region in answer['regions']:
        ids = face_ids(region['identity'])
        key = min(ids)
        check(slot+' unique complete source set', key in truth and key not in seen and ids == truth[key]['ids'])
        seen.add(key)
        t = truth[key]
        check(slot+' center exact', tuple(map(F, region['center_world_m'])) == t['center'])
        check(slot+' bounds exact', [tuple(map(F, p)) for p in region['bounds_world_m']] == [t['low'], t['high']])
        check(slot+' oriented normal', tuple(map(F, region['unit_normal_world'])) == t['normal'])
        if 'boundary_vertices_world_m' in region:
            corners = {tuple(map(F, p)) for p in region['boundary_vertices_world_m']}
            check(slot+' exact boundary corners', len(corners) == 4 and all(all(p[k] in (t['low'][k], t['high'][k]) for k in range(3)) for p in corners))
        good = key == 512
        check(slot+' complete and readable status', region['geometry_complete_in_pool'] is good and region['complete_readable'] is good)
        check(slot+' current references present', bool(region['source_references']))
        if good:
            witness = region['complete_witness']
            pix = pixels[(witness['frame_ref'], key)]
            check(slot+' actual delivered readable witness', witness['view_name'] == pix['view'] and witness['surface_pixels'] == pix['surface'] >= 16 and witness['boundary_pixels'] == pix['boundary'] >= 4 and pix['png'] in delivered and classes[key][pix['view']] == 'complete')
        else:
            check(slot+' actual null witness', region['complete_witness'] is None)
            notes = region['notes']
            check(slot+' explicit unobserved reason in original notes', 'LEFT' in notes and '遮挡' in notes and ('朝向' in notes or '背向' in notes))
        if slot.startswith('P'):
            pub = public_regions[region['identity']['roi_id']]
            check(slot+' actual product source-face adoption', face_ids(pub) == ids and region['center_world_m'] == pub['center_world_m'] and region['unit_normal_world'] == pub['front_direction_world'])
            check(slot+' actual product outcome adoption', (pub['status'] == 'covered') is good)
        for extra in region.get('view_evidence', []):
            extra_views += 1
            name = extra['view_name']
            pix = pixels[(extra['frame_ref'], key)]
            check(slot+' extra view current reference', pix['view'] == name)
            for field, expected in (('surface_pixels', pix['surface']), ('boundary_pixels', pix['boundary']), ('geometrically_complete', classes[key][name] == 'complete'), ('entire_region_inside_frustum', True)):
                if field in extra:
                    check(slot+' extra view '+field, extra[field] == expected)
            if 'complete_readable' in extra:
                check(slot+' extra complete readability', extra['complete_readable'] == (classes[key][name] == 'complete' and pix['surface'] >= 16 and pix['boundary'] >= 4))
            if 'orientation' in extra:
                expected = 'front_facing' if classes[key][name] in ('complete', 'positive_area_occlusion') else classes[key][name]
                check(slot+' extra orientation', extra['orientation'] == expected)
            if 'normal_dot_direction_to_camera' in extra:
                direction = views[name]['target_to_eye_unit'] if 'target_to_eye_unit' in views[name] else [-v for v in views[name]['eye_to_scene_unit']]
                expected = sum(float(n)*v for n, v in zip(t['normal'], direction))
                check(slot+' extra dot', abs(extra['normal_dot_direction_to_camera']-expected) <= 2e-14)
            if 'occluded_area_world_m2' in extra:
                check(slot+' extra shadow area', math.isclose(extra['occluded_area_world_m2'], float(occluded_area), rel_tol=1e-12))
        region_rows.append(dict(first_source_face=key, source_count=len(ids), original_notes=region['notes'], actual_witness=region['complete_witness']))
    results.append(dict(slot=slot, raw_answer_sha256=sha(final_path), frames=len(saved['frames']), image_blocks=len(delivered), regions=region_rows, passed=True))

check('actual formal frame denominator', total_frames == 11)
check('N3 additional view evidence denominator', extra_views == 12)
out = dict(status='passed', checks=len(CHECKS), actual_frames=total_frames, actual_slots=6, additional_view_rows=extra_views, exact_shadow_area=str(occluded_area), slots=results, new_Blender=0, new_raster=0, new_models=0, scope='Independent source geometry, six original finals, actual frames and public product adoption. Manual semantic review complements these exact checks.')
HERE.mkdir(parents=True, exist_ok=True)
(HERE/'RESULT.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf8', newline='\n')
print(json.dumps({k:v for k,v in out.items() if k != 'slots'}, ensure_ascii=False))
