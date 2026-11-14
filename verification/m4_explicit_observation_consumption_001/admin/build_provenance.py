"""Bind the explicit slot's returned product facts and observed partial use."""
import base64
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OWNER = Path('D:/he_explicit_001/formal/P1/o')
CONSUMER = OWNER.parent/'c'
INPUTS = {}


def read(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def tabulate(table):
    columns = table['columns']
    if any(len(row) != len(columns) for row in table['rows']):
        raise ValueError('no_table_tail_or_column_ignored')
    return [dict(zip(columns, row)) for row in table['rows']]


def tool(number):
    folder = OWNER/('tool_'+str(number).zfill(2))
    request, response = read(folder/'REQUEST.json'), read(folder/'RESPONSE.json')
    texts = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
    parsed = json.loads(texts[0]) if texts and texts[0].startswith('{') else {}
    return request, response, parsed


def main():
    request, response, brief = tool(1)
    producer_path = OWNER/'product_call_01/SERVICE_RESULT.json'
    producer = read(producer_path)
    record = read(CONSUMER/'CONSUMER.json')
    evidence = read(HERE/'TOOL_TEXT.json')
    messages = read(HERE/'MODEL_MESSAGES.json')
    regions = tabulate(brief['regions'])
    pixels = tabulate(brief['pixels'])
    images = tabulate(brief['images'])
    source_regions = {row['roi_id']: row for row in producer['facts']['regions']}
    region_checks = 0
    for row in regions:
        source = source_regions[row['roi_id']]
        for field, value in row.items():
            if field in source:
                region_checks += 1
                if source[field] != value:
                    raise ValueError('actual_brief_region_source_mismatch')
    pixel_checks = 0
    for row in pixels:
        source = producer['facts']['observations'][row['image_index']]
        roi = regions[row['region_index']]['roi_id']
        matched = [item for item in source['pixel_rows'] if item['roi_id'] == roi]
        if len(matched) != 1:
            raise ValueError('actual_brief_pixel_source_identity')
        for field, value in row.items():
            if field in matched[0]:
                pixel_checks += 1
                if value != matched[0][field]:
                    raise ValueError('actual_brief_pixel_source_mismatch')
    image_checks = []
    for image in images:
        frame = next(frame for frame in producer['frames'] if frame['image_ref'] == image['image_ref'])
        content = response['result']['content'][image['native_content_block_index']]
        data = base64.b64decode(content['data'], validate=True)
        path = Path(frame['image_path'])
        digest = hashlib.sha256(data).hexdigest()
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        INPUTS[str(path.resolve())] = file_digest
        if digest != image['image_sha256'] or digest != frame['image_sha256'] or digest != file_digest:
            raise ValueError('actual_product_image_delivery_mismatch')
        image_checks.append(dict(view=image['view_name'], ref=image['image_ref'], sha256=digest,
                                 delivered_to_CLI=True, matches_producer_file=True))
    full_coverage = producer['facts']['coverage']
    covered = [regions[index]['roi_id'] for index in brief['coverage']['covered_region_indices']]
    unresolved = [regions[index]['roi_id'] for index in brief['coverage']['unresolved_region_indices']]
    if covered != full_coverage['covered_roi_ids'] or unresolved != full_coverage['unresolved_roi_ids']:
        raise ValueError('actual_product_coverage_projection_mismatch')
    def locate(center, normal):
        selected = [row for row in regions if row['center_world_m'] == center and row['front_direction_world'] == normal]
        if len(selected) != 1:
            raise ValueError('actual_product_location_not_unique')
        row = selected[0]
        index = regions.index(row)
        return dict(region_index=index, region=row,
                    pixels=[dict(view=images[pixel['image_index']]['view_name'], **pixel)
                            for pixel in pixels if pixel['region_index'] == index])
    _, _, native_table = tool(12)
    table = json.loads(native_table['stdout'])
    wrong_row = next(row for row in table['rows'] if row[0] == 56)
    missed = locate([0.3515625, 0, 0], [0, 0, 1])
    tool13_request, tool13_response, _ = tool(13)
    claims = [
        dict(claim='complete_supported_set_and_coverage', final_basis='missing',
             received_product_basis='product', product_supported_count=len(regions), product_covered_count=len(covered),
             intermediate_basis='mixed', actual_native_table_count=table['observed_count'],
             native_source='tool_04 raw mesh component discovery; tool_07 whole-pool rational geometry; tool_10 product BACK image-derived pixels; tool_12 assembled table',
             failure='No final. Native table omits a readable region already covered in the product facts.'),
        dict(claim='finite_pool_remainder_and_reasons', final_basis='missing',
             received_product_basis='product', product_unresolved_count=len(unresolved),
             intermediate_basis='native', actual_native_table_count=table['remaining_count'],
             failure='Native table falsely labels source triangles 1133..1644 as all-view occluded.'),
        dict(claim='unsupported_remainder', final_basis='missing', received_product_basis='product',
             intermediate_basis='native', source='Product scope.patch_support; native tool_04 unsupported [[48]] and tool_12 unsupported record.'),
        dict(claim='SCENE_click_location', final_basis='missing', received_product_basis='product',
             intermediate_basis='native', source='Native tool_07 winning source triangle 35; tool_08 center, corners, normal and pixel counts.'),
        dict(claim='origin_occlusion_and_actual_alternative_pixel', final_basis='missing',
             received_product_basis='product', intermediate_basis='native',
             source='Native tool_07 full geometry and SCENE/LEFT actual buffers. Product v3 also supplies corresponding world and pixel facts.'),
        dict(claim='bottom_finite_pool_scope', final_basis='missing', received_product_basis='product',
             intermediate_basis='native', source='Native tool_07/08 compute registered six-camera front/occlusion facts. Product v3 preserves finite-pool unresolved region.'),
    ]
    result = dict(schema='explicit-observation-consumption-provenance-v1', slot_id='P1', denominator=1,
        layers={
            'real_call': dict(status='pass', first_tool='active_observation', include_images=True,
                first_step_instruction_followed=True, model_CLI_event=True, server_request_received=True,
                actual_installed_producer=True, producer_status=producer['status'],
                runtime_source_sha256=producer['binding']['runtime_source_sha256']),
            'real_delivery': dict(status='pass', schema=brief['schema'],
                actual_first_result_binding=evidence['tools'][0]['result_binding'],
                actual_region_rows=len(regions), actual_pixel_rows=len(pixels),
                common_region_scalar_checks=region_checks, common_pixel_scalar_checks=pixel_checks,
                images=image_checks, coverage_projection_equal=True,
                provider_internal_inputs='unmeasured', provider_internal_definition_delivery='unmeasured'),
            'correct_consumption': dict(status='fail', original_task_quality_passed=False,
                complete_final_artifact=False, terminal_turn_event=False,
                actual_partial_product_use=True, complete_product_fact_consumer_qualification=False)},
        actual_use_sequence=[
            dict(attempt=1, basis='product', action='Explicit observation returned actual v3 and three PNGs.'),
            dict(attempts=[2,3], basis='native', action='Read raw geometry/cameras and ordinary namespace; common native buffers initially empty despite product image files being available.'),
            dict(attempt=4, basis='native', action='Rediscovered all components from raw mesh and requested all six cameras. Constructed native SCENE/TOP/LEFT before the existing six-raster limit blocked further construction.'),
            dict(attempts=[7,8], basis='native', action='Recomputed whole-scene six-view geometric completeness and native buffer pixel facts.'),
            dict(attempts=[9,10], basis='mixed', action='Read actual product PNGs. Compared SCENE/LEFT RGB to native buffers, then derived BACK pixels for 22 thin +Y faces using native projected geometry.'),
            dict(attempts=[11,12], basis='mixed', action='Assembled a table using product image references with native/mixed calculations. Attempt 11 failed KeyError. Attempt 12 produced 114 observed and 24 remaining.'),
            dict(attempt=13, basis='native', action='Requested a TOP-buffer correction, rejected before execution by the tool-attempt guard.')],
        per_claim_provenance=claims,
        received_product_facts=dict(
            coverage=dict(supported_count=len(regions), covered_count=len(covered), unresolved_count=len(unresolved)),
            unsupported=brief['scope']['patch_support'],
            click=locate([0.15625,-0.15625,0.11865234375],[0,0,1]),
            origin=locate([0,0,0],[0,0,1]),
            bottom=locate([0.15625,-0.15625,0.11572265625],[0,0,-1])),
        concrete_native_error=dict(source_triangle_range=[1133,1644], native_surface_index=56,
            actual_table_row=wrong_row, original_product_region=missed,
            correction_request=tool13_request['params']['arguments'],
            correction_response=tool13_response['result'], correction_executed=False),
        final_state=dict(public_final_exists=False, turn_terminal_event_types=messages['terminal_event_types'],
            last_saved_progress=messages['last_saved_agent_message'], consumer_errors=record['errors']),
        cost_analysis_performed=False, inputs_sha256=INPUTS,
        limitation='Initial cleanup-status inspection exposed embedded single-slot timestamps. No FINAL_TIMING/usage or cost ranking was inspected. All later quality review material removes timing fields.')
    with (HERE/'CONSUMPTION_PROVENANCE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(layers={key:value['status'] for key,value in result['layers'].items()},
                         actual_product_regions=len(regions), covered=len(covered), unresolved=len(unresolved),
                         native_table_observed=table['observed_count'], native_table_remaining=table['remaining_count'],
                         new_models_products_rasters=0)))


if __name__ == '__main__':
    main()
