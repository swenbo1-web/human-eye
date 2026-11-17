"""Close the independent quality module using only original saved evidence."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUNTIME = Path('D:/he_m4_cross_scale_001')


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def read(path):
    return json.loads(Path(path).read_bytes())


def main():
    input_pins = {}
    def verify(row):
        current = pin(row['path'])
        if current['sha256']!=row['sha256'] or ('bytes' in row and current['bytes']!=row['bytes']):
            raise ValueError('quality_input_changed/' + row['path'])
        prior = input_pins.setdefault(current['path'],current)
        if prior!=current:
            raise ValueError('quality_input_conflict')
    report_paths = [HERE/'qualification_R0.json'] + [HERE/('pair'+str(index)+'_'+version+'_QUALITY.json')
        for index in (1,2,3) for version in ('R0','R1')]
    reports = []
    for path in report_paths:
        record = read(path)
        if record['passed_checked_scope'] is not True:
            raise ValueError('quality_report_failed/' + str(path))
        reports.append(record)
        verify(pin(path))
        for row in record['input_pins']:
            verify(row)
    paired = read(HERE/'PAIRED_QUALITY.json')
    state = read(HERE/'STATE_QUALITY.json')
    if (paired['passed_checked_scope'] is not True or paired['pair_denominator']!=3
            or state['passed_checked_scope'] is not True or state['state_request_count']!=7
            or state['actual_rasters']!=17):
        raise ValueError('paired_or_state_quality_failed')
    for path,report in ((HERE/'PAIRED_QUALITY.json',paired),(HERE/'STATE_QUALITY.json',state)):
        verify(pin(path))
        for row in report['input_pins']:
            verify(row)
    for row in state['default_legacy']['input_pins']:
        verify(row)
    state_quality_checks = state['default_legacy']['checks']
    state_reports = []
    for row in state['records']:
        record = read(row['report'])
        verify(dict(path=row['report'],sha256=row['report_sha256']))
        if record['passed_checked_scope'] is not True:
            raise ValueError('state_request_quality_failed')
        state_reports.append(record)
        state_quality_checks += record['check_count']
        for item in record['input_pins']:
            verify(item)
    skip_paths = [HERE/('pair'+str(index)+'_R1_SKIPS.json') for index in (1,2,3)]
    skip_paths += [HERE/('state_'+label+'_SKIPS.json') for label in ('initial','conditions','moved','restored')]
    skip_reports = []
    for path in skip_paths:
        record = read(path)
        if record['passed_checked_scope'] is not True or len(record['proofs'])!=5:
            raise ValueError('independent_skip_certificate_failed')
        skip_reports.append(record)
        verify(pin(path))
        for row in record['input_pins']:
            verify(row)
    actual_files = {}
    native_images = 0
    constructed_occurrences = 0
    for label in ('qualification_R0','pair1_R0','pair1_R1','pair2_R1','pair2_R0','pair3_R0','pair3_R1','state'):
        session = RUNTIME/'sessions'/label
        calls = [json.loads(line) for line in (session/'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines() if line.strip()]
        for call in calls:
            full = read(call['producer_archive']['path'])
            response = read(call['response_path'])
            native_images += sum(block['type']=='image' for block in response['result']['content'])
            work = full['work']
            constructed_occurrences += work['raster_attempts']
            for frame in full.get('constructed_frames',full['frames']):
                image = pin(frame['image_path'])
                arrays = pin(frame['arrays_path'])
                identity = (image['path'],arrays['path'])
                current = dict(PNG=image,NPZ=arrays)
                if identity in actual_files and actual_files[identity]!=current:
                    raise ValueError('cached_original_image_mutated')
                actual_files[identity] = current
    if constructed_occurrences!=len(actual_files)!=58:
        raise ValueError('actual_unique_constructed_denominator')
    if constructed_occurrences!=58 or len(actual_files)!=58 or native_images!=44:
        raise ValueError('actual_construction_or_delivery_denominator')
    for path in (NS/'oracle/EXPECTATIONS.json',NS/'oracle/PURE_CHECKS.json',NS/'oracle/INTERFACE_CHECKS.json',
                 HERE/'STATE_SAVED_CORRECTION_01.json',HERE/'state_adapter.py',HERE/'state_adapter_r1.py',
                 HERE/'derive_state_r1.py',HERE/'state.stderr.txt',HERE/'state_r1.stdout.txt',HERE/'state_r1.stderr.txt'):
        verify(pin(path))
    all_check_count = sum(report['check_count'] for report in reports)+state_quality_checks+paired['check_count']+sum(report['check_count'] for report in skip_reports)
    region_pixels = []
    for report in reports:
        local = [frame for frame in report['frames'] if frame['scope_id']!='global']
        region_pixels.append(dict(session=Path(report['session']).name,
            witnesses=[dict(scope_id=frame['scope_id'],pixels=frame['pixels'],
                triangle_ownership_ambiguous=frame['independent_ray_review']['triangle_edge_or_depth_tie_ambiguous_pixels']) for frame in local]))
    result = dict(schema='cross-scale-independent-quality-module-v1',passed_checked_scope=True,
        first_version_qualification=True,formal_quality_denominator=6,formal_quality_passed=6,paired_quality_denominator=3,paired_quality_passed=3,
        state_requests=7,state_quality_passed=7,independent_check_count=all_check_count,
        actual_owned_sessions=8,actual_public_requests=14,actual_constructed_frames=58,actual_native_image_blocks=44,
        skipped_global_predictions=5*len(skip_reports),
        interval_excluded_triangle_samples=sum(row['outside_source_triangle_samples_excluded'] for report in skip_reports
            for view in report['proofs'] for row in view['regions']),
        region_pixels=region_pixels,
        source_and_geometry='One full current capture with 9 objects, 54 vertices and 56 triangles. Independent exact topology gives 22 rectangles/44 supported triangles and 12 unsupported triangles, preserved as occluders.',
        task_results='Obj_02 and Obj_09 have current geometrically complete readable local witnesses. Obj_06 retains positive_area_occlusion_all_front_views unknown.',
        paired_result='All three pairs retain exact ordered world source, task geometry/outcomes, selected cameras, PNG and RGB/depth/object-owner/source-triangle/patch arrays.',
        state_result='Established default brief v5 preserved. Same task full/repeat reuse real cached frames without new raster. z=1 excludes the inclined region. Owned-copy translation and restore refresh current bindings and retain task quality.',
        saved_checker_corrections='Original state checker pinned legacy brief v2 instead of established v5. Original stderr, original adapter, derived one-expression correction and AST equality to the prior default projection remain. Cache accounting uses preserved generation frames and current capture count through the explicitly recorded source adapter. A receipt preparation str/Path error is retained and separately completed.',
        unknowns=['Covered target remains genuine unknown.', 'Exact triangle ownership in recorded edge/near-depth numerical bands remains unclaimed. Every actual foreground pixel was checked for admissible source triangle and no nearer surface within 1e-8m.',
                  'Skipped global directions are predicted capability bounds and have no fabricated observed pixels.',
                  'Model task quality, model cost, arbitrary nonrectangular regions and deployment are outside this fixed qualification.'],
        current_source_limits='Evaluated per-object triangle rows on the fixed asset. Same-capture local source maps are verified against actual original host packets.',
        performance_ranking_performed=False,source_author_association='This reviewer authored the independent Fraction oracle and saved evidence checks, and did not implement the cross-scale product code.',
        new_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0),
        reports=[pin(path) for path in report_paths+skip_paths+[HERE/'PAIRED_QUALITY.json',HERE/'STATE_QUALITY.json']],
        input_pins=sorted(input_pins.values(),key=lambda row:row['path']))
    verify(pin(__file__))
    result['input_pins']=sorted(input_pins.values(),key=lambda row:row['path'])
    with (HERE/'QUALITY_REVIEW.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True,checks=all_check_count,current_inputs=len(input_pins),frames=len(actual_files),native_images=native_images)))


if __name__=='__main__':
    main()
