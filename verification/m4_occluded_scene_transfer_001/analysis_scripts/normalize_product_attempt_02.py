"""Source-only post-run transcription of the three saved product answers."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_occluded_transfer_001/formal')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def support(source, excerpt):
    return [{'source_id': source, 'excerpt': excerpt}]


def list_members(body, name):
    position = body.index('[', body.index('"' + name + '"')) + 1
    result = []
    decoder = json.JSONDecoder()
    while True:
        while body[position].isspace() or body[position] == ',':
            position += 1
        if body[position] == ']':
            return result
        item, end = decoder.raw_decode(body, position)
        result.append((item, body[position:end]))
        position = end


def identity(item):
    result = {k: item[k] for k in ('object_index', 'object_name') if k in item}
    result['source_triangle_indices'] = item.get('local_source_triangle_indices', item.get('source_triangle_indices'))
    if 'roi_alias' in item:
        result['roi_id'] = item['roi_alias']
    for key in ('center_world_m', 'front_direction_world'):
        if key in item:
            result[key] = item[key]
    corners = item.get('rectangle_corners_world_m', item.get('corners_world_m'))
    if corners is not None:
        result['quad_world_m'] = corners
    return result


def witness(value):
    result = {'view': value['view'], 'ref': value['image_ref']}
    for actual, normalized in [('visible_surface_pixels', 'surface_pixels'), ('contrasting_boundary_pixels', 'boundary_pixels')]:
        if actual in value:
            result[normalized] = value[actual]
    return result


def base(slot):
    folder = RUNTIME / slot
    answer_path = folder / 'c/PUBLIC_FINAL.txt'
    answer = answer_path.read_text(encoding='utf-8')
    row = {'slot_id': slot, 'raw_answer_path': str(answer_path), 'raw_answer_sha256': sha(answer_path),
           'sources': [], 'panels': [], 'remaining': [], 'unsupported': [], 'pixel_targets': [],
           'source_targets': [], 'finite_pool_only': True, 'global_invisibility_overclaim': False,
           'contradictions': [], 'extra_tool_classification': [], 'product_adoption': {'claims': []},
           'coverage_use_excerpt': next(line for line in answer.splitlines() if '61' in line and '18' in line)}
    scope = next(line for line in answer.splitlines() if 'only' in line.lower() and ('pool' in line or 'SCENE' in line))
    row['finite_pool_support'] = support('final', scope)
    requests = sorted((folder / 'o').glob('tool_*/REQUEST.json'))
    for path in requests[1:]:
        number = int(path.parent.name.split('_')[1])
        source_id = 'request_' + str(number)
        body = path.read_text(encoding='utf-8')
        value = json.loads(body)['params']
        row['sources'].append({'id': source_id, 'kind': 'tool_request', 'path': str(path), 'sha256': sha(path)})
        if value['name'] == 'render_views':
            category = 'new_native_observation'
        elif number in (2, 3):
            category = 'raw_source_read'
        elif number == (6 if slot in ('P1', 'P2') else 5):
            category = 'format_artifact' if slot != 'P2' else 'public_json_query'
        else:
            category = 'native_computation'
        # P3 tool3 constructs TOP while reading the existing LEFT frame.
        if slot == 'P3' and number == 3:
            category = 'new_native_observation'
        row['extra_tool_classification'].append({'attempt': number, 'category': category,
                                                 'support': support(source_id, body)})
    product_path = folder / 'o/tool_01/RESPONSE.json'
    text = json.loads(product_path.read_bytes())['result']['content'][0]['text']
    public = json.loads(text)
    region = dict(zip(public['regions']['columns'], public['regions']['rows'][0]))
    row['sources'].append({'id': 'active', 'kind': 'tool_result', 'path': str(product_path), 'sha256': sha(product_path)})
    # Full compact table row is an exact contiguous excerpt of the public JSON.
    public_row = public['regions']['rows'][0]
    excerpt = next(encoded for encoded in (json.dumps(public_row, ensure_ascii=False, separators=(',', ':')),
                                           json.dumps(public_row, ensure_ascii=False)) if encoded in text)
    row['product_adoption']['claims'].append({'identity': {'roi_id': region['roi_id']},
        'product_support': support('active', excerpt), 'final_use_excerpt': row['coverage_use_excerpt']})
    return row, answer


def from_artifact(slot):
    row, answer = base(slot)
    folder = RUNTIME / slot
    path = next((folder / 'o/scratch').glob('*.json'))
    body = path.read_text(encoding='utf-8')
    data = json.loads(body)
    citation = next(line for line in answer.splitlines() if path.name in line)
    row['sources'].append({'id': 'report', 'kind': 'cited_artifact', 'path': str(path),
                           'sha256': sha(path), 'final_citation_excerpt': citation})
    for item, excerpt in list_members(body, 'surfaces'):
        state = item['state']
        panel = {'identity': identity(item), 'status': state, 'finite_pool_only': data['finite_pool_only'],
                 'support': support('report', excerpt)}
        if state == 'covered':
            panel['views'] = [witness(item['complete_readable_witness'])]
        else:
            panel['reason_code'] = item['reason']
            row['remaining'].append(panel['identity'])
        row['panels'].append(panel)
    for item, excerpt in list_members(body, 'unsupported'):
        row['unsupported'].append({'identity': identity(item), 'status': 'unsupported',
            'domain': 'outside_supported_rectangle_domain', 'component_count': 1,
            'shape': 'nonrectangular', 'support': support('report', excerpt)})
    for item, excerpt in list_members(body, 'pixel_targets'):
        row['pixel_targets'].append({'id': item.get('id', item.get('name')), 'identity': identity(item),
            'center_world_m': item['center_world_m'], 'front_direction_world': item['front_direction_world'],
            'quad_world_m': item.get('rectangle_corners_world_m', item.get('corners_world_m')),
            'view': item['view'], 'ref': item['image_ref'], 'support': support('report', excerpt)})
    for item, excerpt in list_members(body, 'source_targets'):
        target = {'id': item.get('id', item.get('name')), 'identity': identity(item), 'status': item['state'],
                  'finite_pool_only': data['finite_pool_only'], 'support': support('report', excerpt)}
        if item['state'] == 'covered':
            target['witness'] = witness(item['complete_readable_witness'])
        else:
            target['reason_code'] = item['reason']
        row['source_targets'].append(target)
    return row


def from_table():
    row, answer = base('P2')
    short = dict(S='SCENE', T='TOP', L='LEFT', R='RIGHT', F='FRONT', B='BACK')
    refs = {}
    for name, view in short.items():
        lines = [line for line in answer.splitlines() if line.startswith('- **' + name + ' / ')]
        if lines:
            refs[view] = re.search(r'`([^`]+)`', lines[0]).group(1)
    legend = answer[answer.index('- **C:view**'):answer.index('| Object index/name |')].strip()
    for line in answer.splitlines():
        found = re.match(r'\| (\d+) ([A-Za-z]+) \| (.+) \|$', line)
        if not found:
            continue
        object_index, name, cells = int(found[1]), found[2], found[3].split(' | ')
        for face, cell in enumerate(cells):
            if cell == '—':
                continue
            identity_value = {'object_index': object_index, 'object_name': name, 'source_triangle_indices': [face*2, face*2+1]}
            panel = {'identity': identity_value, 'finite_pool_only': True,
                     'support': support('final', line) + support('final', legend)}
            if cell.startswith('C:'):
                view = short[cell[2:]]
                panel.update(status='covered', views=[{'view': view, 'ref': refs[view]}])
            else:
                panel.update(status='unknown', reason_code='no_front_facing_candidate' if cell == 'N' else 'positive_area_occlusion_all_front_views')
                row['remaining'].append(identity_value)
            row['panels'].append(panel)
    line = next(line for line in answer.splitlines() if line.startswith('**Unsupported:**'))
    row['unsupported'] = [{'identity': {'object_index': 11, 'object_name': 'ConnectedLBracket',
        'source_triangle_indices': [0, 1, 2, 3]}, 'status': 'unsupported', 'domain': 'outside_supported_rectangle_domain',
        'component_count': 1, 'shape': 'nonrectangular', 'support': support('final', line)}]
    for name, obj, faces, center, normal, corners, view in (
        ('sample_A', 1, [2,3], [0,0,6.5], [0,0,1], [[-7,-6,6.5],[7,-6,6.5],[7,6,6.5],[-7,6,6.5]], 'TOP'),
        ('sample_B', 0, [10,11], [-7,0,-.25], [-1,0,0], [[-7,-6,-.5],[-7,-6,0],[-7,6,0],[-7,6,-.5]], 'LEFT')):
        start = answer.index('**' + name + ' —')
        end = answer.find('\n## ', start)
        if name == 'sample_A':
            end = answer.index('**sample_B', start)
        excerpt = answer[start:end].strip()
        row['pixel_targets'].append({'id': name, 'identity': {'object_index': obj, 'source_triangle_indices': faces},
            'center_world_m': center, 'front_direction_world': normal, 'quad_world_m': corners,
            'view': view, 'ref': refs[view], 'support': support('final', excerpt)})
    for name, faces, reason in [('target_C',[2,3],'positive_area_occlusion_all_front_views'),
                               ('target_D',[0,1],'no_front_facing_candidate')]:
        line = next(line for line in answer.splitlines() if line.startswith('- **' + name + ' —'))
        row['source_targets'].append({'id': name, 'identity': {'object_index': 0, 'source_triangle_indices': faces},
            'status': 'unknown', 'reason_code': reason, 'finite_pool_only': True, 'support': support('final', line)})
    return row


def main():
    rows = [from_artifact('P1'), from_table(), from_artifact('P3')]
    value = {'schema': 'occluded-scene-transfer-normalized-product-part-v1', 'slots': rows,
             'source_only': True, 'truth_or_pixel_truth_read': False, 'cost_or_usage_read': False}
    with (HERE / 'admin/NORMALIZED_P.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps({'slots': [r['slot_id'] for r in rows], 'surfaces': [len(r['panels']) for r in rows]}))


if __name__ == '__main__':
    main()
