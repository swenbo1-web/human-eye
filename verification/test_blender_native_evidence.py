"""Read-only original-pose sidecars from one Blender host traversal.

Small bpy doubles validate protocol and rejection boundaries. They do not
replace actual Blender evaluation, external-writer isolation or a physical
motion meter. No Blender process or user file is opened here.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from types import SimpleNamespace as NS
import unittest

from human_eye_plugin.auto_router import _validated_scene
from verification.test_host_identity_contract import identity_host
from verification.test_blender_host_contracts import BlenderHostError, FakeObject, FakeMatrix


def fixture(scale=1.):
    host, focal, reference, graph = identity_host()
    host.execution_metadata = True
    host.scene.unit_settings.scale_length = scale
    for obj in (focal, reference):
        obj.data.polygons = [NS(vertices=list(triangle.vertices)) for triangle in obj.data.loop_triangles]
    return host, focal, reference, graph


def evaluated_copy(obj):
    evaluated = copy.copy(obj)
    evaluated.data = copy.deepcopy(obj.data)
    evaluated._matrix_world = FakeMatrix([row[:] for row in obj.matrix_world])
    obj.evaluated_get = lambda graph:evaluated
    return evaluated


class BlenderNativeEvidenceTests(unittest.TestCase):
    def test_one_traversal_keeps_default_capture_and_router_fingerprint(self):
        host, focal, reference, _ = fixture()
        before = host.capture_scene()
        updates = []
        host.view_layer.update = lambda:updates.append(True)
        packet = host.capture_evidence()
        self.assertEqual(len(updates), 1)
        self.assertEqual(packet['capture'], before)
        normalized, _, fingerprint = _validated_scene(packet['capture'])
        self.assertEqual(normalized, packet['capture'])
        self.assertEqual(fingerprint, packet['coherence']['capture_fingerprint'])
        self.assertEqual(host.capture_scene(), before)
        self.assertEqual(focal.assignments + reference.assignments, 0)
        self.assertNotIn('native_scene', before)
        self.assertNotIn('capture_confirmation', packet)

    def test_native_schema_and_ascii_revision_are_exact(self):
        host, focal, reference, _ = fixture()
        focal.name = focal.name_full = '蓝色零件'
        packet = host.capture_evidence()
        self.assertEqual(set(packet), {'protocol','capture','native_scene','coherence'})
        self.assertEqual(packet['protocol'], 'native-pose-evidence-v1-20261030')
        native = packet['native_scene']
        self.assertEqual(set(native), {'unit','coordinate_frame','revision','objects'})
        self.assertEqual(native['unit'], 'm')
        self.assertEqual(native['coordinate_frame'], 'world')
        encoded = json.dumps(native['objects'], sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('utf-8')
        self.assertEqual(native['revision'], 'native:' + hashlib.sha256(encoded).hexdigest())
        objects = {obj['object_id']:obj for obj in native['objects']}
        self.assertEqual(set(objects), set(packet['capture']['host_identity']['object_instances']))
        for obj in native['objects']:
            self.assertEqual(set(obj), {'object_id','name','local_vertices','world_vertices','faces','matrix','color'})
        self.assertEqual(objects[host.object_id(focal)]['name'], '蓝色零件')
        self.assertEqual(packet['coherence']['native_revision'], native['revision'])

    def test_scope_distinguishes_snapshot_from_independent_measurement_or_history(self):
        host, _, _, _ = fixture()
        info = host.capture_evidence()['coherence']
        self.assertTrue(info['same_traversal'])
        self.assertTrue(info['raw_original_mesh_verified'])
        self.assertTrue(info['snapshot_not_history'])
        self.assertEqual(info['execution_scope'], 'independent_static_rigid_meshes')
        self.assertEqual(info['sample_source'], 'single_synchronous_blender_main_thread_capture')
        self.assertEqual(info['world_coordinate_evaluation'], 'binary64_original_local_matrix_forward_map')
        self.assertFalse(info['independent_physical_measurement'])
        self.assertFalse(info['external_edit_history_proven'])
        self.assertFalse(info['execution_authority'])

    def test_local_vertices_and_matrix_translation_are_in_metres(self):
        host, focal, _, _ = fixture(.01)
        packet = host.capture_evidence()
        obj = next(item for item in packet['native_scene']['objects'] if item['object_id']==host.object_id(focal))
        self.assertEqual(obj['local_vertices'][1], [.01,0.,0.])
        self.assertEqual([obj['matrix'][k][3] for k in range(3)], [.02,.03,.04])
        self.assertEqual([obj['matrix'][k][k] for k in range(3)], [1.,1.,1.])
        for local, world in zip(obj['local_vertices'], obj['world_vertices']):
            for k in range(3):
                predicted = sum(obj['matrix'][k][j]*local[j] for j in range(3)) + obj['matrix'][k][3]
                self.assertAlmostEqual(predicted, world[k], places=15)

    def test_object_uniform_scale_stays_in_original_matrix(self):
        host, focal, _, _ = fixture(.01)
        for k in range(3):focal._matrix_world[k][k] = 2.
        native = host.capture_evidence()['native_scene']
        obj = next(item for item in native['objects'] if item['object_id']==host.object_id(focal))
        self.assertEqual(obj['local_vertices'][1], [.01,0.,0.])
        self.assertEqual([obj['matrix'][k][k] for k in range(3)], [2.,2.,2.])
        self.assertAlmostEqual(obj['world_vertices'][1][0], .04)

    def test_native_and_capture_geometry_are_detached_from_each_other_and_host(self):
        host, focal, reference, _ = fixture()
        packet = host.capture_evidence()
        capture_before = copy.deepcopy(packet['capture'])
        native = packet['native_scene']['objects'][0]
        original = next(obj for obj in (focal,reference) if host.object_id(obj)==native['object_id'])
        original_vertex = list(original.data.vertices[0].co)
        original_matrix = copy.deepcopy(original.matrix_world)
        native['world_vertices'][0][0] += 10
        native['faces'][0][0] = 99
        native['local_vertices'][0][0] += 11
        native['matrix'][0][3] += 12
        self.assertEqual(packet['capture'], capture_before)
        self.assertEqual(list(original.data.vertices[0].co), original_vertex)
        self.assertEqual(original.matrix_world, original_matrix)

    def test_original_vertex_disagreement_rejects_whole_new_method(self):
        host, focal, _, _ = fixture()
        evaluated = evaluated_copy(focal)
        evaluated.data.vertices[0].co = (.01,0.,0.)
        with self.assertRaisesRegex(BlenderHostError, 'original and evaluated local meshes disagree'):
            host.capture_evidence()
        self.assertGreater(evaluated.clears, 0)
        self.assertEqual(focal.assignments, 0)

    def test_original_polygon_disagreement_rejects_even_same_evaluated_triangles(self):
        host, focal, _, _ = fixture()
        evaluated = evaluated_copy(focal)
        evaluated.data.polygons[0].vertices = [0,1,2]
        with self.assertRaisesRegex(BlenderHostError, 'original and evaluated local meshes disagree'):
            host.capture_evidence()
        self.assertEqual(focal.assignments, 0)

    def test_original_world_matrix_disagreement_rejects(self):
        host, focal, _, _ = fixture()
        evaluated = evaluated_copy(focal)
        evaluated._matrix_world[0][3] += .01
        with self.assertRaisesRegex(BlenderHostError, 'original and evaluated world matrices disagree'):
            host.capture_evidence()
        self.assertEqual(focal.assignments, 0)

    def test_missing_raw_polygon_data_is_not_treated_as_verified_original(self):
        host, focal, _, _ = fixture()
        del focal.data.polygons
        with self.assertRaisesRegex(BlenderHostError, 'original mesh data is unavailable'):
            host.capture_evidence()

    def test_original_polygon_coverage_has_a_bound_before_allocating_topology(self):
        host, focal, _, _ = fixture()
        focal.data.polygons.append(NS(vertices=[0,1,2]))
        with self.assertRaisesRegex(BlenderHostError, 'polygon budget or coverage'):
            host.capture_evidence()

    def test_original_polygon_corner_count_is_bounded(self):
        host, focal, _, _ = fixture()
        focal.data.polygons[0].vertices = list(range(10000))
        with self.assertRaisesRegex(BlenderHostError, 'original and evaluated local meshes disagree'):
            host.capture_evidence()

    def test_missing_runtime_identity_fails_closed_but_old_capture_remains_readable(self):
        host, _, _, _ = fixture()
        del host.scene.session_uid
        with self.assertRaisesRegex(BlenderHostError, 'complete host identity'):
            host.capture_evidence()
        self.assertNotIn('host_identity', host.capture_scene())

    def test_explicit_metadata_options_required_without_mutating_old_shape(self):
        for execution, identity in ((False,False),(False,True),(True,False)):
            with self.subTest(execution=execution, identity=identity):
                host, focal, reference, _ = fixture()
                host.execution_metadata, host.identity_metadata = execution, identity
                before = host.capture_scene()
                with self.assertRaisesRegex(BlenderHostError, 'explicit execution and identity metadata'):
                    host.capture_evidence()
                self.assertEqual(host.capture_scene(), before)
                self.assertEqual((host.execution_metadata,host.identity_metadata), (execution,identity))
                self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_readable_unsupported_execution_scenes_do_not_get_native_original_proof(self):
        changes = [
            ('parent',NS(name='Parent')), ('children',[NS(name='Child')]),
            ('constraints',[NS()]), ('modifiers',[NS(name='Subdivision',type='SUBSURF')]),
            ('animation_data',NS()), ('rigid_body',NS()), ('mode','EDIT'),
            ('lock_location',(True,False,False)), ('library',NS(filepath='linked.blend')),
        ]
        for field, value in changes:
            with self.subTest(field=field):
                host, focal, reference, _ = fixture()
                setattr(focal,field,value)
                self.assertFalse(host.capture_scene()['host_execution']['supported'])
                with self.assertRaisesRegex(BlenderHostError, 'independent static rigid meshes'):
                    host.capture_evidence()
                self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_shape_keys_data_animation_and_nonuniform_frame_are_rejected(self):
        for condition in ('shape_keys','data_animation','nonuniform','mirrored','shear'):
            with self.subTest(condition=condition):
                host, focal, _, _ = fixture()
                if condition=='shape_keys':focal.data.shape_keys = NS()
                elif condition=='data_animation':focal.data.animation_data = NS()
                elif condition=='nonuniform':focal._matrix_world[0][0] = 2.
                elif condition=='mirrored':focal._matrix_world[0][0] = -1.
                else:focal._matrix_world[0][1] = .1
                with self.assertRaisesRegex(BlenderHostError, 'independent static rigid meshes'):
                    host.capture_evidence()
                self.assertEqual(focal.assignments, 0)

    def test_hidden_mesh_is_included_and_partial_coverage_rejected(self):
        host, focal, reference, _ = fixture()
        reference.hide_viewport = reference.hide_render = True
        packet = host.capture_evidence()
        self.assertEqual(len(packet['native_scene']['objects']), 2)
        host.object_names = frozenset([focal.name])
        with self.assertRaisesRegex(BlenderHostError, 'every scene mesh'):
            host.capture_evidence()

    def test_native_color_rejects_nonfinite_alpha_ignored_by_old_rgb_capture(self):
        for alpha in (float('nan'), float('inf'), True):
            with self.subTest(alpha=alpha):
                host, focal, _, _ = fixture()
                focal.color = (.2,.3,.4,alpha)
                self.assertTrue(host.capture_scene()['host_execution']['supported'])
                with self.assertRaisesRegex(BlenderHostError, 'four finite components'):
                    host.capture_evidence()

    def test_scene_membership_changed_during_traversal_rejects(self):
        host, focal, _, _ = fixture()
        def changed():
            fresh = FakeObject('Unexpected')
            fresh.session_uid = 1234
            host.scene.objects.append(fresh)
            return focal.data
        focal.to_mesh = changed
        with self.assertRaisesRegex(BlenderHostError, 'changed during capture'):
            host.capture_evidence()

    def test_execution_capability_changed_during_traversal_rejects(self):
        host, focal, _, _ = fixture()
        def changed():
            focal.constraints.append(NS())
            return focal.data
        focal.to_mesh = changed
        with self.assertRaisesRegex(BlenderHostError, 'changed during capture'):
            host.capture_evidence()

    def test_document_epoch_changes_without_reusing_old_evidence_binding(self):
        host, _, _, _ = fixture()
        first = host.capture_evidence()
        host.bpy.app.driver_namespace.clear()
        second = host.capture_evidence()
        self.assertNotEqual(first['capture']['host_identity']['document_epoch'],
                            second['capture']['host_identity']['document_epoch'])
        self.assertNotEqual(first['capture']['revision'],second['capture']['revision'])
        self.assertEqual(first['native_scene'],second['native_scene'])

    def test_main_thread_required_before_native_access(self):
        host, focal, reference, _ = fixture()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(host.capture_evidence)
            with self.assertRaisesRegex(BlenderHostError, 'main thread'):future.result()
        self.assertEqual(focal.assignments + reference.assignments, 0)


if __name__=='__main__':unittest.main()
