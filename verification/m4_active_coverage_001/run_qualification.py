"""Exercise finite-view coverage using the six actual frozen raster images."""

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2) + '\n', encoding='utf8', newline='\n')


def smallest_subsets(order, masks):
    possible = 0
    for mask in masks.values():
        possible |= mask
    for size in range(len(order) + 1):
        subsets = []
        for subset in itertools.combinations(order, size):
            covered = 0
            for name in subset:
                covered |= masks[name]
            if covered == possible:
                subsets.append(list(subset))
        if subsets:
            return {'maximum_covered_mask': possible, 'minimum_images': size, 'subsets': subsets}


def main():
    started = time.perf_counter_ns()
    candidate = load('_active_qualification_candidate', HERE / 'coverage.py')
    delivery = load('_active_qualification_delivery', HERE / 'render/assess_readability.py')
    scene = read(HERE / 'inputs/SCENE_GEOMETRY_RATIONAL.json')
    cameras = read(HERE / 'inputs/CAMERAS.json')
    pixels = read(HERE / 'render/READABILITY.json')
    results = []
    for variant in ('reference', 'optimized'):
        before = time.perf_counter_ns()
        index = candidate.build_index(scene, cameras, variant)
        state = candidate.CoverageState(index)
        trace = []
        while state.next_view() is not None:
            name = state.next_view()
            receipt = delivery.receipt_for_view(index, name, pixels)
            trace.append({'actual_image_receipt': receipt, 'update': state.observe(receipt)})
        original_summary = state.summary()
        repeated = state.observe(delivery.receipt_for_view(index, 'SCENE', pixels))
        assert repeated['reused'] and not repeated['new_roi_ids'] and state.summary() == original_summary
        fixed = candidate.CoverageState(index)
        fixed_trace = [fixed.observe(delivery.receipt_for_view(index, name, pixels)) for name in index.view_order]
        assert fixed.covered_mask == state.covered_mask
        readable_masks = {}
        per_view = []
        for name in index.view_order:
            receipt = delivery.receipt_for_view(index, name, pixels)
            readable_mask = sum(1 << i for i, identity in enumerate(index.region_ids) if identity in receipt['readable_roi_ids'])
            readable_masks[name] = readable_mask & index.view_masks[name]
            per_view.append({'view_name': name, 'geometric_complete_roi_ids': index.ids(index.view_masks[name]),
                             'pixel_readable_roi_ids': list(receipt['readable_roi_ids']),
                             'deliverable_complete_readable_roi_ids': index.ids(readable_masks[name]),
                             'image_path': receipt['image_path'], 'image_sha256': receipt['image_sha256']})
        result = {'variant': variant, 'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
                  'regions': [{'roi_id': region.roi_id, 'object_index': region.object_index,
                               'display_name': region.object_name, 'vertices': region.vertices, 'front_normal': region.normal}
                              for region in index.regions],
                  'roi_ids': list(index.region_ids), 'view_masks': index.view_masks, 'classifications': index.classifications,
                  'per_view': per_view, 'actual_observation_trace': trace, 'coverage': original_summary,
                  'same_version_reuse': repeated, 'fixed_six_engineering_trace': fixed_trace,
                  'geometric_candidate_pool_optimum': smallest_subsets(index.view_order, index.view_masks),
                  'readable_candidate_pool_optimum': smallest_subsets(index.view_order, readable_masks),
                  'stats': index.stats, 'qualification_elapsed_ns': time.perf_counter_ns()-before,
                  'new_raster_calls': 0, 'planning_frame_deliveries': len(trace),
                  'scope': 'Existing full-scene frozen PNGs and independently measured common-depth/owner readability.'}
        save(HERE / 'results' / (variant + '.json'), result)
        results.append(result)
    for field in ('scene_identity', 'candidate_identity', 'roi_ids', 'view_masks', 'classifications', 'coverage',
                  'geometric_candidate_pool_optimum', 'readable_candidate_pool_optimum'):
        assert results[0][field] == results[1][field], field
    for result in results:
        optimum = result['readable_candidate_pool_optimum']
        assert len(result['actual_observation_trace']) == optimum['minimum_images']
        assert len(result['coverage']['covered_roi_ids']) == optimum['maximum_covered_mask'].bit_count()
    summary = {'passed': True, 'variants_identical': True,
               'scene_sha256': sha(HERE / 'inputs/SCENE_GEOMETRY_RATIONAL.json'),
               'camera_sha256': sha(HERE / 'inputs/CAMERAS.json'), 'source_sha256': sha(HERE / 'coverage.py'),
               'pixel_evidence_sha256': sha(HERE / 'render/READABILITY.json'),
               'discovered_regions': len(results[0]['roi_ids']), 'visibility_cells': sum(len(row) for row in results[0]['classifications'].values()),
               'selected_full_images': results[0]['coverage']['observed_views'],
               'delivered_covered': len(results[0]['coverage']['covered_roi_ids']),
               'candidate_pool_uncovered': len(results[0]['coverage']['candidate_pool_uncovered_roi_ids']),
               'all_qualification_full_scene_raster_calls': 6,
               'new_raster_calls_in_this_reuse_stage': 0,
               'interpretation': 'All six qualification renders remain charged. Selected-frame delivery reuses that prepared image pool.',
               'elapsed_ns': time.perf_counter_ns()-started, 'new_model_Blender_API_runs': 0}
    save(HERE / 'results/QUALIFICATION.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
