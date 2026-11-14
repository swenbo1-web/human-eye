"""Read-only verification of quoted pixel counts and actual tool adoption."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_loc_001/formal')
INPUTS = {}


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def stdout(owner, number):
    response = read(owner/('tool_'+str(number).zfill(2))/'RESPONSE.json')
    text = next(block['text'] for block in response['result']['content'] if block['type'] == 'text')
    return json.loads(text)['stdout']


def table(owner, number, layout):
    text = stdout(owner, number)
    if layout == 'N2':
        return json.loads(text)['rows']
    return json.JSONDecoder().raw_decode(text, text.index('[['))[0]


def main():
    truth = read(HERE/'TRUTH.json')
    normalized = read(HERE/'NORMALIZED.json')
    targets = truth['targets']
    face_map = np.full(3337, -2, dtype=np.int32)
    by_faces, by_corners = {}, {}
    for index, target in enumerate(targets):
        face_map[target['source_triangle_indices']] = index
        by_faces[tuple(sorted(target['source_triangle_indices']))] = index
        by_corners[frozenset(tuple(Fraction(v) for v in point) for point in target['quad_world_m'])] = index
    result = []
    for slot in normalized['slots']:
        name = slot['slot_id']
        owner = RUNTIME/name/'o'
        observations = read(owner/'OBSERVATIONS.json')
        measured = {}
        for frame in observations['frames']:
            path = Path(frame['NPZ'])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            INPUTS[str(path.resolve())] = digest
            if digest != frame['NPZ_sha256']:
                raise ValueError('current_array_original_changed')
            with np.load(path, allow_pickle=False) as arrays:
                color, triangles = arrays['color'], arrays['triangle_ids']
            labels = np.full(triangles.shape, -1, dtype=np.int32)
            labels[triangles >= 0] = face_map[triangles[triangles >= 0]]
            edge = np.zeros(labels.shape, dtype=bool)
            for first, last in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[:, :-1], np.s_[:, 1:])):
                difference = color[first].astype(np.int32)-color[last].astype(np.int32)
                contrasting = (labels[first] != labels[last]) & ((difference*difference).sum(axis=2) >= 24*24)
                edge[first] |= contrasting
                edge[last] |= contrasting
            counts = np.bincount(labels[labels >= 0], minlength=len(targets))
            boundaries = np.bincount(labels[edge & (labels >= 0)], minlength=len(targets))
            measured[frame['ref']] = (frame['view_name'], counts, boundaries)
        checks, failures = 0, []
        if name == 'P3':
            artifact = read(owner/'scratch/scene_inspection.json')
            raw_claims = []
            for surface in artifact['surfaces']:
                identity = {'source_triangle_indices': surface['source_triangle_indices']}
                for view, facts in surface['evidence_by_view'].items():
                    raw_claims.append(dict(identity=identity, ref=facts['image_ref'], view=view,
                        surface=facts['surface_pixels'], boundary=facts['boundary_pixels'],
                        front=facts['front_facing'], complete=facts['complete'], readable=facts['readable']))
        else:
            specifications = {'N1': [(8, 'N1')], 'N2': [(8, 'N2')], 'N3': [(8, 'N3'), (9, 'N3')],
                              'P1': [(7, 'P1')], 'P2': [(8, 'P2')]}
            rows = [row for number, layout in specifications[name] for row in table(owner, number, layout)]
            if len(rows) != len(slot['panels']):
                raise ValueError('no_trailing_table_rows_may_be_ignored')
            raw_claims = []
            for index in range(len(rows)):
                row, panel = rows[index], slot['panels'][index]
                offset = 4 if name == 'P2' else 3
                status = row[3] if name == 'P2' else row[2]
                if status == 'observed':
                    raw_claims.append(dict(identity=panel['identity'], view=row[offset], ref=row[offset+1],
                                           surface=row[offset+2], boundary=row[offset+3]))
        for claim in raw_claims:
            identity = claim['identity']
            index = (by_faces[tuple(sorted(identity['source_triangle_indices']))] if 'source_triangle_indices' in identity
                     else by_corners[frozenset(tuple(Fraction(v) for v in point) for point in identity['quad_world_m'])])
            view, counts, boundaries = measured[claim['ref']]
            facts = targets[index]['by_view'][view]
            actual = dict(view=view, surface=int(counts[index]), boundary=int(boundaries[index]),
                          front=facts['front_facing'], complete=facts['geometry_complete'],
                          readable=bool(facts['geometry_complete'] and counts[index] >= 16 and boundaries[index] >= 4))
            for key, value in claim.items():
                if key in actual:
                    checks += 1
                    if value != actual[key]:
                        failures.append(dict(target=targets[index]['key'], ref=claim['ref'], field=key,
                                             claimed=value, actual=actual[key]))
        tools = read(owner/'TOOLS.json')['tools']
        names = [read(owner/('tool_'+str(tool['attempt']).zfill(2))/'REQUEST.json')['params']['name'] for tool in tools]
        result.append(dict(slot_id=name, current_frames=len(measured), original_claim_rows=len(raw_claims),
            scalar_checks=checks, failures=failures, passed=not failures,
            actual_tool_name_counts=dict(Counter(names)), active_observation_calls=len(observations['active']),
            raster_origin_counts=dict(Counter(row['origin'] for row in observations['render_attempts']))))
    output = dict(schema='region-localization-quoted-claim-audit-v1', slots=result,
        all_claim_counts_and_statuses_match=all(slot['passed'] for slot in result),
        actual_product_observation_calls=sum(slot['active_observation_calls'] for slot in result),
        cost_analysis_performed=False, new_product_calls=0, new_rasters=0, new_model_calls=0,
        inputs_sha256=INPUTS)
    with (HERE/'CLAIM_AUDIT.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: output[key] for key in ('all_claim_counts_and_statuses_match',
        'actual_product_observation_calls', 'cost_analysis_performed')}))
    print(json.dumps({'scalar_checks': sum(slot['scalar_checks'] for slot in result),
                      'failures': sum(len(slot['failures']) for slot in result)}))


if __name__ == '__main__':
    main()
