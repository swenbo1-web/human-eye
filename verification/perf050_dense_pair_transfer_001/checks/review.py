"""Bind each live dense result to current geometry, wire evidence, and final media."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace


NS = Path(__file__).resolve().parents[1]
V = NS.parent
ROOT = V.parent
RUN = Path('D:/he_perf050_dense_pair_transfer_001')
INSTALL = V / 'm1_pair_distance_entry_001/install/PRODUCT_RUN_BINDING.json'
ASSET = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
SOURCE = '0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147'
TARGET, OTHER = 'M4_Far_00', 'M4_Focal'
SOURCE_TRIANGLES = [512, 513]


retained = run_path(str(V / 'perf050_target_observation_first_image_p2/checks/review.py'))
BaseReview = retained['Review']
BaseReview.check_source.__globals__.update(ASSET=ASSET, SOURCE=SOURCE, TARGET=TARGET, OTHER=OTHER,
                                           PAIR={TARGET, OTHER})
require, packed_rows = retained['require'], retained['packed_rows']


class DenseReview(BaseReview):
    def __init__(self, slot):
        super().__init__(ROOT, slot, INSTALL)
        self.dense = run_path(str(NS / 'truth/verify.py'))
        self.truth = self.json(NS / 'truth/TRUTH.json')
        original_evidence = self.evidence
        self.evidence = SimpleNamespace(**vars(original_evidence))
        self.evidence.same_geometry = self.same_geometry
        self.evidence.measure_body = self.measure_body
        self.region = {'object_name': TARGET, 'source_triangle_indices': SOURCE_TRIANGLES}
        self.source_cache = {}

    def same_geometry(self, capture, terminal):
        fingerprint = self.slot / 'TERMINAL_SOURCE.json'
        if fingerprint not in self.source_cache:
            self.dense['verify_scene'](terminal, ROOT)
            self.source_cache[fingerprint] = {obj['name']: obj for obj in self.oracle['coordinates'](terminal['objects'])}
        expected = self.source_cache[fingerprint]
        if capture is not None:
            actual = {mesh['name']: {'name': mesh['name'], 'triangles': mesh['faces'],
                      'vertices': [tuple(map(self.oracle['F'], point)) for point in mesh['vertices']]}
                      for mesh in capture['meshes']}
            require(actual and actual.keys() <= expected.keys()
                    and all(expected[name] == mesh for name, mesh in actual.items()), 'captured_evaluated_geometry_changed')
        return expected

    def frame_proof(self, log, raw, arrays):
        return self.dense['qualify_frame'](log, self.terminal, raw, arrays, ROOT)

    def measure_body(self, value, _meshes):
        binding = value['binding']
        names = [row['name'] for row in binding['objects']]
        require(names == [TARGET, OTHER] and value['execution_authority'] is False
                and value['coordinate_frame'] == 'world' and value['unit'] == 'm', 'whole_pair_scope_or_units_changed')
        schema = value['schema_version']
        if schema in ('task-query-set-v1', 'task-query-set-v2'):
            pair, = value['pairs']
            require(value['scope'] == 'explicit_target_candidates'
                    and value['pair_order'] == 'target_to_candidate' and pair['candidate_index'] == 0
                    and pair['object_id'] == binding['objects'][1]['object_id'], 'whole_pair_set_order_mismatch')
            facts = pair['facts']
        else:
            require(schema == 'task-query-v3' and value['pair_order'] == 'A_to_B', 'unexpected_ordered_pair_schema')
            facts = value['facts']
        fact = facts['surface_proximity']
        require(fact['status'] == 'measured', 'expected_measured_whole_surface_proximity')
        result = fact['value']
        witness = result['nearest_witness']
        proof = self.dense['verify_pair'](self.terminal, result['distance_m'], witness['direction_a_to_b'],
                                         [witness['a'], witness['b']], ROOT)
        require(all(proof[field] for field in ('distance_correct', 'points_on_current_surfaces',
                'world_direction_correct', 'points_attain_whole_minimum')), 'whole_pair_failed_independent_truth')
        return {'schema': schema, 'binding_scope': binding.get('capture_scope'), 'bound': binding['objects'],
                'fact': fact, 'witness_membership': proof}

    def target_witness(self, doc, image):
        block = image['native_content_block_index']
        images = packed_rows(doc['images'])
        if type(block) is not int or not 1 <= block <= len(images) or images[block - 1] != image:
            return None
        regions, pixels, objects = (packed_rows(doc[key]) for key in ('regions', 'pixels', 'objects'))
        for index, region in enumerate(regions):
            witness = region['complete_witness_pixel_index']
            if type(witness) is not int or not 0 <= witness < len(pixels):
                continue
            pixel = pixels[witness]
            if (objects[region['object_index']]['object_name'] == TARGET
                    and region['source_triangle_index_ranges'] == [[512, 513]] and region['status'] == 'covered'
                    and pixel['image_index'] == block - 1 and pixel['region_index'] == index
                    and pixel['readable'] is True and pixel['front_facing'] is True):
                return pixel
        return None

    def run(self):
        result = super().run()
        result['schema'] = 'perf050-dense-pair-transfer-structural-review-v1'
        result['geometric_truth'] = {'region_source_triangles': SOURCE_TRIANGLES, 'minimum_distance_m': 1,
                                     'direction_world': [-1, 0, 0], 'top_board_only_distance_m': 'sqrt(2)'}
        routes = []
        for call in self.calls:
            query = call['args'].get('query', {})
            task = query.get('task_query', query)
            if task.get('mode') == 'task':
                requested = task.get('requested_facts', [])
                if not set(requested) & {'surface_proximity', 'nearest_witness', 'closed_solid_relation', 'spatial_relation'}:
                    continue
                form = 'ordered_whole_objects' if 'objects' in task else 'candidate_pair_set'
            elif query.get('mode') == 'source_region':
                form = 'source_region'
            else:
                continue
            routes.append({'attempt': call['attempt'], 'form': form, 'query': query,
                           'result_error': call['error'], 'wire': call['rx']})
        result['structured_distance_requests'] = routes
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label', choices=('N1', 'P1'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'registered_interpreter_required')
    slot = RUN / 'slots' / args.label
    publication = retained['read'](slot / 'SLOT_PUBLICATION.json') if (slot / 'SLOT_PUBLICATION.json').is_file() else None
    result = (DenseReview(slot).run() if publication and publication['status'] == 'completed'
              else {'slot': args.label, 'publication': publication, 'status': 'failed' if publication else 'unrun'})
    with args.output.open('x', encoding='utf8', newline='\n') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')


if __name__ == '__main__':
    main()
