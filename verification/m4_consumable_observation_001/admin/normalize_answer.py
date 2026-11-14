"""Normalize actual product/native claims from this one closed consumer."""
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_consume_001/formal/P1')
INPUTS = {}


def read_bytes(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(read_bytes(path))


def save(name, value):
    with (HERE/name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def line(final, marker):
    found = [text for text in final.splitlines() if marker in text]
    if len(found) != 1:
        raise ValueError('unique_final_excerpt:'+marker)
    return found[0]


def table(value):
    if any(len(row) != len(value['columns']) for row in value['rows']):
        raise ValueError('complete_table_columns')
    return [dict(zip(value['columns'], row)) for row in value['rows']]


def strip(value):
    if type(value) is dict:
        return {key: strip(item) for key, item in value.items()
                if not re.search(r'(^|_)(ns|ms|seconds|elapsed|duration|usage|tokens|cost|timing|metrics|stages|perf)(_|$)', key)}
    if type(value) is list:
        return [strip(item) for item in value]
    return value


def main():
    answer_path = RUNTIME/'c/PUBLIC_FINAL.txt'
    final = read_bytes(answer_path).decode('utf8')
    calls, sources, parsed, bodies = [], [], {}, {}
    tools = read(RUNTIME/'o/TOOLS.json')['tools']
    for item in tools:
        number = item['attempt']
        folder = RUNTIME/'o'/('tool_'+str(number).zfill(2))
        request, response = read(folder/'REQUEST.json'), read(folder/'RESPONSE.json')
        body = '\n'.join(block['text'] for block in response['result']['content'] if block.get('type') == 'text')
        text_blocks = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
        values = [json.loads(block) if block.startswith('{') else block for block in text_blocks]
        parsed[number] = next((value for value in values if type(value) is dict), {})
        bodies[number] = body
        calls.append(dict(attempt=number, tool=request['params']['name'], arguments=request['params']['arguments'],
            is_error=response['result']['isError'], text=[strip(value) for value in values],
            response_path=str((folder/'RESPONSE.json').resolve()), response_sha256=INPUTS[str((folder/'RESPONSE.json').resolve())]))
        if number in (1, 6, 7):
            sources.append(dict(id='tool_'+str(number).zfill(2), kind='tool_result',
                path=str((folder/'RESPONSE.json').resolve()), sha256=INPUTS[str((folder/'RESPONSE.json').resolve())]))
    product = parsed[1]
    regions, pixels, images = table(product['regions']), table(product['pixels']), table(product['images'])
    native = json.loads(parsed[7]['stdout'])
    if len(regions) != len(native['rows']) or len(regions) != 138:
        raise ValueError('complete_actual_coverage_rows')
    def support(number, value):
        compact = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        if number != 1:
            compact = json.dumps(compact, ensure_ascii=False)[1:-1]
        if compact not in bodies[number]:
            raise ValueError('source_excerpt_missing')
        return dict(source_id='tool_'+str(number).zfill(2), excerpt=compact)
    panels, provenance = [], []
    for index in range(len(regions)):
        region, source_row = regions[index], native['rows'][index]
        if source_row[0] != index or source_row[2] != region['status']:
            raise ValueError('native_product_row_binding')
        identity = dict(roi_id=region['roi_id'], source_triangle_indices=[face
            for first, last in source_row[1] for face in range(first, last+1)])
        supports = [support(1, product['regions']['rows'][index]), support(7, source_row)]
        panel = dict(identity=identity, status=region['status'], views=[], support=supports)
        if region['status'] == 'covered':
            witness = pixels[region['complete_witness_pixel_index']]
            image = images[witness['image_index']]
            panel['views'] = [dict(view=image['view_name'], ref=image['image_ref'])]
            panel['support'].extend([support(1, product['pixels']['rows'][region['complete_witness_pixel_index']]),
                                     support(1, product['images']['rows'][witness['image_index']])])
        else:
            panel['reason_code'] = ('back_facing_all_views' if region['unobserved_reason'] == 'no_front_facing_candidate'
                                    else 'positive_area_occlusion_all_front_views')
            panel['original_reason'] = region['unobserved_reason']
        panels.append(panel)
        provenance.append(dict(region_index=index, roi_id=region['roi_id'],
            status_basis='product tool_01 v4 region/inspection',
            geometry_complete_witness_basis='product tool_01 complete_witness_pixel_index',
            source_face_mapping_basis='native tool_06 containment mapping against product world vectors, emitted tool_07',
            original_status=region['status'], source_triangle_count=len(identity['source_triangle_indices'])))
    click_line, origin_line, bottom_line = (line(final, marker) for marker in ('1.', '2.', '3.'))
    click_center = json.loads(re.search(r'center `(\[[^`]+\])` m', click_line).group(1))
    x_bounds = json.loads(re.search(r'X `(\[[^`]+\])`', click_line).group(1))
    y_bounds = json.loads(re.search(r'Y `(\[[^`]+\])`', click_line).group(1))
    click_ref = re.search(r'Current image: `([^`]+)`', click_line).group(1)
    origin_center = json.loads(re.findall(r'\[[^\]]+\]', origin_line)[0])
    origin_pixel = json.loads(re.findall(r'\[[^\]]+\]', origin_line)[1])
    origin_ref = re.search(r'BACK reference: `([^`]+)`', origin_line).group(1)
    bottom_center = json.loads(re.findall(r'\[[^\]]+\]', bottom_line)[0])
    questions = dict(
        click=dict(identity={'center_world_m': click_center, 'front_direction_world': [0,0,1]},
            center_world_m=click_center, front_direction_world=[0,0,1],
            bounds_world_m=[[x_bounds[0],y_bounds[0],click_center[2]],[x_bounds[1],y_bounds[1],click_center[2]]],
            view='SCENE', ref=click_ref,
            support=[dict(source_id='final', excerpt=click_line), dict(source_id='tool_06', excerpt=bodies[6])]),
        origin=dict(identity={'center_world_m':origin_center,'front_direction_world':[0,0,1]},
            SCENE_visible_pixels=0, SCENE_front_facing=True, SCENE_occluded=True,
            witness={'view':'BACK','ref':origin_ref,'pixel_xy':origin_pixel},
            support=dict(source_id='final',excerpt=origin_line)),
        bottom=dict(identity={'center_world_m':bottom_center,'front_direction_world':[0,0,-1]},
            finite_pool_no_front_readable=True,finite_pool_only=True,global_invisibility_claim=False,
            support=[dict(source_id='final',excerpt=bottom_line),dict(source_id='final',excerpt=line(final,'**Scope:**'))]))
    component = product['scope']['patch_support']['unsupported_components']['rows'][0]
    normalized = dict(schema='region-localization-normalized-v1',
        scoring_role='Current final, actual product v4 facts, and actual native supplementation before cost analysis.',
        slots=[dict(slot_id='P1',raw_answer_path=str(answer_path.resolve()),
            raw_answer_sha256=INPUTS[str(answer_path.resolve())], sources=sources,
            coverage_use_excerpt=line(final,'- **Evidence:**'), finite_pool_scope_correct=True,
            global_invisibility_overclaim=False,panels=panels,questions=questions,
            unsupported=[dict(component_count=1,source_triangle_indices=[48],status='unknown',
                shape='nonrectangular',domain='outside_supported_rectangle_domain',
                support=[dict(source_id='final',excerpt=line(final,'- **Coverage:**')),support(1,component)])])])
    save('NORMALIZED.json',normalized)
    save('TOOL_TEXT.json',dict(schema='consumable-observation-quality-tool-text-v1',tools=calls,cost_fields_removed=True))
    save('CLAIM_PROVENANCE.json',dict(schema='consumable-observation-claim-provenance-v1',slot_id='P1',
        final_sha256=INPUTS[str(answer_path.resolve())],complete_region_claims=provenance,
        main_claims=[
            dict(claim='complete_supported_set_and_coverage',basis='product with native source-face verification',
                 source='tool_01 regions/inspection/witness; tool_06/07 mapping assertions and source ranges; final coverage/evidence bullets'),
            dict(claim='finite_pool_remaining',basis='product',source='tool_01 inspection and unobserved reason groups; tool_03 read-only JSON queries; final coverage/scope'),
            dict(claim='unsupported_source_48',basis='mixed',source='tool_01 patch_support component range48; tool_06 source_to_region<0 and tool_07 record; final coverage'),
            dict(claim='SCENE_click',basis='mixed',source='product world vectors/SCENE pixels; native tool_04 current SCENE image-04; tool_06 winning triangle35; final position1'),
            dict(claim='origin_SCENE_occlusion_and_BACK_pixel',basis='product',source='tool_01 v4 complete witness; tool_03 query prints SCENE0/fronttrue and BACK468/84/anchor419224; final position2'),
            dict(claim='bottom_finite_pool_scope',basis='product and common camera metadata',source='tool_01 bottom unknown/no_front groups; tool_02/03 camera/JSON queries; final position3/scope')],
        actual_supplementation=[
            dict(attempt=2,operation='json.loads(last_observation_json), shared camera/geometry metadata query'),
            dict(attempt=3,operation='Read-only query of product JSON world/pixel/unknown facts'),
            dict(attempt=4,operation='New native SCENE raster for a view already produced by product'),
            dict(attempt=5,operation='Source-face mapping attempt failed Fraction-string conversion'),
            dict(attempt=6,operation='Mapped all source triangles onto existing product rectangles and queried actual click; no independent region discovery or whole-pool visibility solution'),
            dict(attempt=7,operation='Native SCENE pixel-count equality against product; emitted product-based coverage/source-face table')],
        efficiency_qualification='Independent call/string/efficiency audit by the root-assigned reviewer.',
        cost_analysis_performed=False,inputs_sha256=INPUTS))
    print(json.dumps(dict(normalized_slots=1,regions=len(panels),covered=sum(row['status']=='covered' for row in panels),
                         unobserved=sum(row['status']!='covered' for row in panels),new_models_products_rasters=0)))


if __name__=='__main__':
    main()
