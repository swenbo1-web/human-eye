"""Selected host capture contracts using observed main-thread bpy doubles.

Actual Blender evaluation, wire transport and timing require the separately
frozen qualification. These tests exercise the host's normal public entry.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace as NS
import unittest

from verification.test_blender_host_contracts import (
    BlenderHostError, FakeMesh, FakeObject, host_fixture, matrix,
)


class ObservedMesh(FakeMesh):
    def __init__(self):
        super().__init__()
        self.triangulations = 0

    def calc_loop_triangles(self):
        self.triangulations += 1
        super().calc_loop_triangles()


class ObservedObject(FakeObject):
    def __init__(self, name, translation=(0, 0, 0), session_uid=101):
        super().__init__(name, translation)
        self.session_uid = session_uid
        self.evaluations = self.mesh_reads = self.world_reads = 0
        self.data = ObservedMesh()
        self.evaluated_override = None

    @property
    def matrix_world(self):
        self.world_reads += 1
        return self._matrix_world

    @matrix_world.setter
    def matrix_world(self, value):
        FakeObject.matrix_world.fset(self, value)

    def evaluated_get(self, graph):
        self.evaluations += 1
        return self if self.evaluated_override is None else self.evaluated_override

    def to_mesh(self):
        self.mesh_reads += 1
        return super().to_mesh()

    def reads(self):
        return (self.evaluations, self.mesh_reads, self.data.triangulations,
                self.world_reads, self.clears)


def selected_fixture(scale=1):
    host, _, _, graph = host_fixture(scale)
    focal = ObservedObject('Focal', (2, 3, 4), 101)
    reference = ObservedObject('Reference', (5, 0, 0), 102)
    host.scene.objects = [reference, focal]
    host.view_layer.objects.active = focal
    host.scene.session_uid = 100
    host.bpy.app = NS(driver_namespace={})
    host.bpy.data = NS(filepath='fixture.blend')
    return host, focal, reference, graph


class SelectedTaskHostTests(unittest.TestCase):
    def test_complete_evaluated_geometry_uses_world_transform_and_metre_scale(self):
        host, focal, reference, _ = selected_fixture(0.5)
        evaluated = ObservedObject('Evaluated')
        evaluated._matrix_world = matrix((8, 10, 12), (2, 3, 4))
        points = [(0, 0, 0), (2, 0, 0), (0, 4, 0), (0, 0, 6), (2, 4, 0), (2, 0, 6)]
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 4), (1, 5, 3), (1, 4, 5)]
        evaluated.data.vertices = [NS(co=point) for point in points]
        evaluated.data.loop_triangles = [NS(vertices=face) for face in faces]
        focal.evaluated_override = evaluated
        focal.parent = NS(name='Parent')
        focal.modifiers = [NS(type='ARRAY', name='TwoCopies')]

        value = host.capture_task_scene([{'name': 'Focal'}])

        self.assertEqual(focal.reads(), (1, 0, 0, 0, 0))
        self.assertEqual(evaluated.reads(), (0, 1, 1, 1, 1))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(focal.assignments + evaluated.assignments + reference.assignments, 0)
        self.assertEqual(len(value['meshes']), 1)
        mesh = value['meshes'][0]
        self.assertEqual(mesh['vertices'], [
            [4., 5., 6.], [6., 5., 6.], [4., 11., 6.],
            [4., 5., 18.], [6., 11., 6.], [6., 5., 18.],
        ])
        self.assertEqual(mesh['faces'], [list(face) for face in faces])
        self.assertEqual(mesh['edges'], [list(edge) for edge in sorted({
            tuple(sorted((face[a], face[b]))) for face in faces
            for a, b in ((0, 1), (1, 2), (2, 0))
        })])
        self.assertEqual(mesh['pivot_world'], [4., 5., 6.])
        self.assertEqual(mesh['object_id'], host.object_id(focal))
        self.assertEqual(json.loads(json.dumps(value, allow_nan=False)), value)

    def test_name_lookup_never_hashes_unselected_candidate_ids(self):
        host, focal, reference, _ = selected_fixture()
        original = host.object_id
        calls = []

        def observe_id(obj):
            calls.append(obj.name)
            return original(obj)

        host.object_id = observe_id
        value = host.capture_task_scene([{'name': 'Focal'}])
        self.assertTrue(calls)
        self.assertEqual(set(calls), {'Focal'})
        self.assertEqual(value['task_selection']['candidate_count'], 2)
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(focal.reads(), (1, 1, 1, 1, 1))

    def test_ordered_id_name_and_missing_bindings_preserve_unique_geometry(self):
        host, focal, reference, _ = selected_fixture()
        selectors = [{'id': host.object_id(reference)}, {'name': 'Missing'}, {'name': 'Focal'}]
        value = host.capture_task_scene(selectors)
        selection = value['task_selection']
        self.assertEqual(selection, {
            'selectors': selectors,
            'bindings': [
                {'object_id': host.object_id(reference), 'name': 'Reference'},
                {'status': 'unknown', 'selector': {'name': 'Missing'}, 'reason': 'object_not_found'},
                {'object_id': host.object_id(focal), 'name': 'Focal'},
            ],
            'pair_reason': None,
            'candidate_count': 2,
        })
        self.assertEqual([mesh['object_id'] for mesh in value['meshes']],
                         sorted([host.object_id(focal), host.object_id(reference)]))
        self.assertEqual(focal.reads(), (1, 1, 1, 1, 1))
        self.assertEqual(reference.reads(), (1, 1, 1, 1, 1))
        selectors[1]['name'] = 'ChangedAfterReturn'
        self.assertEqual(selection['selectors'][1], {'name': 'Missing'})
        self.assertEqual(selection['bindings'][1]['selector'], {'name': 'Missing'})

    def test_same_target_pair_is_collected_once_with_original_pair_reason(self):
        host, focal, reference, _ = selected_fixture()
        value = host.capture_task_scene([{'id': host.object_id(focal)}, {'name': 'Focal'}])
        self.assertEqual(len(value['meshes']), 1)
        self.assertEqual(value['task_selection']['bindings'], [
            {'object_id': host.object_id(focal), 'name': 'Focal'},
            {'object_id': host.object_id(focal), 'name': 'Focal'},
        ])
        self.assertEqual(value['task_selection']['pair_reason'], 'pair_selectors_resolve_to_same_object')
        self.assertEqual(focal.reads(), (1, 1, 1, 1, 1))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))

    def test_ambiguous_name_stays_unknown_and_does_not_choose_a_mesh(self):
        host, focal, reference, _ = selected_fixture()
        other = ObservedObject('Focal', session_uid=103)
        other.name_full = 'DistinctLinkedFocal'
        host.scene.objects.append(other)
        value = host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(value['meshes'], [])
        self.assertEqual(value['task_selection']['bindings'], [{
            'status': 'unknown', 'selector': {'name': 'Focal'}, 'reason': 'object_name_ambiguous',
        }])
        self.assertEqual(value['task_selection']['candidate_count'], 3)
        self.assertEqual(value['host_identity']['object_instances'], {})
        self.assertEqual([obj.reads() for obj in (focal, reference, other)], [(0, 0, 0, 0, 0)] * 3)

    def test_zero_resolved_and_zero_mesh_candidates_keep_document_identity(self):
        host, focal, reference, graph = selected_fixture()
        focal.type = reference.type = 'CURVE'
        graph.object_instances = [NS(is_instance=True)]
        value = host.capture_task_scene([{'name': 'MissingA'}, {'name': 'MissingB'}])
        self.assertEqual(value['meshes'], [])
        self.assertEqual(value['capture_scope'], 'selected_objects')
        self.assertEqual(value['task_selection']['candidate_count'], 0)
        self.assertEqual(value['host_identity']['capture_scope'], 'selected_objects')
        self.assertEqual(value['host_identity']['object_instances'], {})
        self.assertEqual(len(value['host_identity']['document_epoch']), 64)
        self.assertEqual([obj.reads() for obj in (focal, reference)], [(0, 0, 0, 0, 0)] * 2)
        self.assertEqual(host.capture_task_scene([{'name': 'MissingA'}, {'name': 'MissingB'}]), value)

    def test_complete_candidate_binding_has_no_full_geometry_object_cap(self):
        host, focal, reference, _ = selected_fixture()
        backgrounds = [ObservedObject('Background_%03d' % i, session_uid=1000 + i) for i in range(257)]
        host.scene.objects.extend(backgrounds)
        value = host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(value['task_selection']['candidate_count'], 259)
        self.assertEqual(len(value['meshes']), 1)
        self.assertEqual(focal.reads(), (1, 1, 1, 1, 1))
        self.assertTrue(all(obj.reads() == (0, 0, 0, 0, 0) for obj in [reference] + backgrounds))
        with self.assertRaisesRegex(BlenderHostError, '1..256'):
            host.capture_scene()

    def test_unrelated_geometry_and_execution_guards_are_outside_selected_scope(self):
        host, focal, reference, graph = selected_fixture()
        reference.modifiers = [NS(type='NODES', name='BackgroundNodes')]
        reference.instance_type = 'COLLECTION'
        reference.lock_location = (True, True, True)
        curve = NS(type='CURVE', name='Curve')
        host.scene.objects.append(curve)
        graph.object_instances = [NS(is_instance=True)]
        host.execution_metadata = True

        def forbidden_guard(*args):
            raise AssertionError('Selected read entered full-scene writable audit')

        host._execution_status = forbidden_guard
        host._guard_description = forbidden_guard
        value = host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(value['task_selection']['candidate_count'], 2)
        self.assertNotIn('host_execution', value)
        self.assertEqual(focal.reads(), (1, 1, 1, 1, 1))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        with self.assertRaisesRegex(BlenderHostError, 'Instanced scene geometry is unsupported: Reference'):
            host.capture_scene()

    def test_selected_instances_and_geometry_nodes_keep_explicit_refusal(self):
        for kind in ('instance_type', 'is_instancer', 'geometry_nodes'):
            with self.subTest(kind=kind):
                host, focal, reference, _ = selected_fixture()
                if kind == 'instance_type':
                    focal.instance_type = 'COLLECTION'
                elif kind == 'is_instancer':
                    focal.is_instancer = True
                else:
                    focal.modifiers = [NS(type='NODES', name='SelectedNodes')]
                with self.assertRaisesRegex(BlenderHostError, 'selected geometry|Selected geometry-node'):
                    host.capture_task_scene([{'name': 'Focal'}])
                self.assertEqual(focal.reads(), (0, 0, 0, 0, 0))
                self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))

    def test_background_geometry_frame_and_write_guard_changes_keep_revision(self):
        host, focal, reference, _ = selected_fixture()
        selectors = [{'name': 'Focal'}]
        first = host.capture_task_scene(selectors)
        reference.data.vertices[0].co = (100, 200, 300)
        reference._matrix_world = matrix((200, -20, 300))
        reference.lock_rotation = (True, False, False)
        reference.constraints = [NS(type='COPY_LOCATION')]
        reference.name = reference.name_full = 'RenamedBackground'
        host.scene.frame_current = 123
        self.assertEqual(host.capture_task_scene(selectors), first)
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_target_geometry_transform_and_scale_each_change_revision(self):
        host, focal, _, _ = selected_fixture()
        selectors = [{'name': 'Focal'}]
        first = host.capture_task_scene(selectors)
        focal.data.vertices[0].co = (0.25, 0, 0)
        geometry_changed = host.capture_task_scene(selectors)
        self.assertNotEqual(geometry_changed['revision'], first['revision'])
        self.assertEqual(geometry_changed['meshes'][0]['vertices'][0], [2.25, 3., 4.])
        focal._matrix_world = matrix((3, 3, 4))
        pose_changed = host.capture_task_scene(selectors)
        self.assertNotEqual(pose_changed['revision'], geometry_changed['revision'])
        self.assertEqual(pose_changed['meshes'][0]['vertices'][0], [3.25, 3., 4.])
        host.scene.unit_settings.scale_length = 2
        scale_changed = host.capture_task_scene(selectors)
        self.assertNotEqual(scale_changed['revision'], pose_changed['revision'])
        self.assertEqual(scale_changed['meshes'][0]['vertices'][0], [6.5, 6., 8.])
        self.assertEqual(focal.assignments, 0)

    def test_selector_syntax_order_and_candidate_coverage_bind_revision(self):
        host, focal, reference, _ = selected_fixture()
        names = [{'name': 'Focal'}, {'name': 'Reference'}]
        first = host.capture_task_scene(names)
        changed_order = host.capture_task_scene(list(reversed(names)))
        changed_syntax = host.capture_task_scene([{'id': host.object_id(focal)}, {'name': 'Reference'}])
        self.assertEqual(first['meshes'], changed_order['meshes'])
        self.assertEqual(first['meshes'], changed_syntax['meshes'])
        self.assertNotEqual(first['revision'], changed_order['revision'])
        self.assertNotEqual(first['revision'], changed_syntax['revision'])
        host.scene.objects.append(ObservedObject('Background', session_uid=103))
        changed_coverage = host.capture_task_scene(names)
        self.assertEqual(first['meshes'], changed_coverage['meshes'])
        self.assertNotEqual(first['revision'], changed_coverage['revision'])
        self.assertEqual(reference.assignments, 0)

    def test_identical_geometry_replacement_has_new_instance_and_revision(self):
        host, focal, _, _ = selected_fixture()
        first = host.capture_task_scene([{'name': 'Focal'}])
        replacement = ObservedObject('Focal', (2, 3, 4), session_uid=201)
        host.scene.objects = [replacement if obj is focal else obj for obj in host.scene.objects]
        host.view_layer.objects.active = replacement
        changed = host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(first['meshes'], changed['meshes'])
        self.assertEqual(first['host_identity']['document_epoch'], changed['host_identity']['document_epoch'])
        self.assertEqual(first['host_identity']['object_instances'], {host.object_id(focal): '101'})
        self.assertEqual(changed['host_identity']['object_instances'], {host.object_id(replacement): '201'})
        self.assertNotEqual(first['revision'], changed['revision'])

    def test_document_change_invalidates_zero_resolution_snapshot(self):
        host, _, _, _ = selected_fixture()
        first = host.capture_task_scene([{'name': 'Missing'}])
        host.bpy.data.filepath = 'AnotherDocument.blend'
        changed = host.capture_task_scene([{'name': 'Missing'}])
        self.assertEqual(first['meshes'], changed['meshes'])
        self.assertNotEqual(first['host_identity']['document_epoch'], changed['host_identity']['document_epoch'])
        self.assertNotEqual(first['revision'], changed['revision'])

    def test_selected_identity_is_required_even_with_optional_metadata_disabled(self):
        host, focal, reference, _ = selected_fixture()
        self.assertFalse(host.identity_metadata)
        del focal.session_uid
        with self.assertRaisesRegex(BlenderHostError, 'requires document and object instance identity'):
            host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(focal.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        del host.bpy.app
        with self.assertRaisesRegex(BlenderHostError, 'requires document and object instance identity'):
            host.capture_task_scene([{'name': 'Missing'}])

    def test_selector_validation_never_falls_back_to_full_capture(self):
        host, focal, reference, _ = selected_fixture()
        invalid = [None, False, {}, (), [], [{'name': 'Focal'}] * 5,
                   [None], [{}], [{'name': 'Focal', 'id': 'id'}], [{'other': 'Focal'}],
                   [{'name': ''}], [{'name': '  '}], [{'name': 12}], [{'name': 'x' * 257}],
                   [{'name': '\u754c' * 86}]]
        for selectors in invalid:
            with self.subTest(selectors=selectors), self.assertRaises(BlenderHostError):
                host.capture_task_scene(selectors)
        self.assertEqual(focal.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(host.bpy.app.driver_namespace, {})
        bound = '\u754c' * 85 + 'x'
        value = host.capture_task_scene([{'name': bound}])
        self.assertEqual(value['task_selection']['selectors'], [{'name': bound}])
        self.assertEqual(value['meshes'], [])
        value = host.capture_task_scene([{'name': 'Focal'}] * 4)
        self.assertEqual(len(value['task_selection']['bindings']), 4)
        self.assertEqual(len(value['meshes']), 1)

    def test_original_full_capture_and_object_names_contract_stay_intact(self):
        host, focal, reference, _ = selected_fixture()
        full = host.capture_scene()
        self.assertNotIn('capture_scope', full)
        self.assertNotIn('task_selection', full)
        self.assertNotIn('host_identity', full)
        self.assertEqual(host.bpy.app.driver_namespace, {})
        selected = host.capture_task_scene([{'name': 'Focal'}, {'name': 'Reference'}])
        self.assertEqual(full['meshes'], selected['meshes'])
        host.object_names = frozenset(['Focal'])
        with self.assertRaisesRegex(BlenderHostError, 'every scene mesh'):
            host.capture_scene()
        self.assertEqual(len(host.capture_task_scene([{'name': 'Reference'}])['meshes']), 1)
        self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_selected_geometry_keeps_original_index_budget_and_cleanup_checks(self):
        host, focal, reference, _ = selected_fixture()
        focal.data.loop_triangles[0].vertices = (0, 2, 99)
        with self.assertRaisesRegex(BlenderHostError, 'valid evaluated triangles'):
            host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(focal.clears, 1)
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))

        class OverBudgetVertices:
            def __len__(self):
                return 500001

            def __iter__(self):
                raise AssertionError('Over-budget vertices were expanded')

        focal.data.vertices = OverBudgetVertices()
        with self.assertRaisesRegex(BlenderHostError, 'geometry budget exceeded'):
            host.capture_task_scene([{'name': 'Focal'}])
        self.assertEqual(focal.clears, 2)
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))

    def test_selected_capture_keeps_main_thread_requirement(self):
        host, focal, reference, _ = selected_fixture()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(host.capture_task_scene, [{'name': 'Focal'}])
            with self.assertRaisesRegex(BlenderHostError, 'main thread'):
                future.result()
        self.assertEqual(focal.reads(), (0, 0, 0, 0, 0))
        self.assertEqual(reference.reads(), (0, 0, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
