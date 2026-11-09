"""Independent arm-source boundary checks using indexed bpy doubles only.

The saved 402-vertex fixture is not regenerated or trained here. Large meshes
refuse iteration of their vertices, exposing accidental whole-asset expansion.
These doubles do not establish real Blender modifier or dependency behavior.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from human_eye_plugin import arm_twist_expert as expert


@lru_cache(maxsize=1)
def saved_cases():
    raw = gzip.decompress((ROOT / 'verification/m6_arm_expert_001/run_01/dataset.json.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest() != '6ccec485cc9fedb832324e3802e1ca4bc8529e55b2171afe4278803c62be1f4d':
        raise AssertionError('Frozen expert fixture changed')
    return json.loads(raw)


def fixture_packet():
    return copy.deepcopy(next(c['packet'] for c in saved_cases()
        if c['metadata']['split'] == 'test' and c['metadata']['pose_family'] == 'anomalous_twist'))


def transform(points, matrix):
    p = np.asarray(points, dtype=float)
    matrix = np.asarray(matrix, dtype=float)
    return (p @ matrix[:3, :3].T + matrix[:3, 3]).tolist()


def rigid(angle=0., translation=(0., 0., 0.)):
    c, s = np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))
    return [[c, -s, 0., translation[0]], [s, c, 0., translation[1]],
            [0., 0., 1., translation[2]], [0., 0., 0., 1.]]


def directed_triangle(face):
    value = tuple(face)
    return min(value[i:] + value[:i] for i in range(3))


class Named(list):
    def get(self, key, default=None):
        return next((value for value in self if value.name == key), default)

    def __getitem__(self, key):
        if isinstance(key, str):
            value = self.get(key)
            if value is None:
                raise KeyError(key)
            return value
        return super().__getitem__(key)


class IndexedVertices:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total
        self.reads = []
        self.iterations = 0

    def __len__(self):
        return self.total

    def __getitem__(self, index):
        if type(index) is not int:
            raise AssertionError('Vertices must be read by explicit native index')
        self.reads.append(index)
        if index not in self.rows:
            raise AssertionError('Read an unselected native vertex: ' + str(index))
        return self.rows[index]

    def __iter__(self):
        self.iterations += 1
        raise AssertionError('Whole asset vertices were expanded or iterated')


class Object:
    def __init__(self, name, kind, data, uid):
        self.name = self.name_full = name
        self.type, self.data, self.session_uid = kind, data, uid
        self.mode, self.instance_type = 'OBJECT', 'NONE'
        self.is_instancer = False
        self.is_evaluated = True
        self.library = self.parent = self.animation_data = None
        self.children, self.constraints, self.modifiers = [], [], []
        self.matrix_world = rigid()
        self.color = (0.2, 0.4, 0.8, 1.)
        self.hide_viewport = self.hide_render = False
        self.evaluated = self
        self.to_mesh_calls = self.clear_calls = 0

    def evaluated_get(self, graph):
        return self.evaluated

    def to_mesh(self):
        self.to_mesh_calls += 1
        raise AssertionError('Arm source must not expand whole evaluated geometry')

    def to_mesh_clear(self):
        self.clear_calls += 1


def make_host(*, total=200000, native_indices=None, scale=1., mesh_world=None, rig_world=None):
    packet = fixture_packet()
    n = len(packet['rest_vertices'])
    native_indices = list(native_indices) if native_indices is not None else [137 + 3 * i for i in range(n)]
    if len(native_indices) != n or len(set(native_indices)) != n:
        raise AssertionError('Fixture must have one distinct native index per saved vertex')
    mesh_world = mesh_world if mesh_world is not None else rigid()
    rig_world = rig_world if rig_world is not None else rigid()
    # Saved coordinates and matrices already share armature space. Native mesh
    # coordinates are independently pulled back through the relative transform.
    mesh_from_rig = np.linalg.inv(np.asarray(mesh_world)) @ np.asarray(rig_world)
    rest = transform(packet['rest_vertices'], mesh_from_rig)
    current = transform(packet['current_vertices'], mesh_from_rig)
    groups = Named(NS(index=i, name=b['name']) for i, b in enumerate(packet['bone_chain']))
    rows = {native: NS(index=native, co=point[:], groups=[NS(group=i, weight=w)
            for i, w in enumerate(packet['weights'][local]) if w > 0.])
            for local, (native, point) in enumerate(zip(native_indices, rest))}
    dynamic = {native: NS(index=native, co=point[:]) for native, point in zip(native_indices, current)}
    triangles = [[native_indices[i] for i in face] for face in packet['triangles']]
    polygons = [NS(index=i, vertices=tuple(face), loop_total=3, loop_start=3*i,
                   loop_indices=tuple(range(3*i, 3*i+3))) for i, face in enumerate(triangles)]
    mesh_data = NS(name='ArmMeshData', vertices=IndexedVertices(rows, total), polygons=polygons,
        loop_triangles=[NS(vertices=tuple(f), polygon_index=i) for i, f in enumerate(triangles)],
        loops=[NS(vertex_index=v) for f in triangles for v in f],
        session_uid=3101, shape_keys=None, animation_data=None, is_editmode=False)
    eval_data = NS(vertices=IndexedVertices(dynamic, total), polygons=polygons,
        loop_triangles=mesh_data.loop_triangles, session_uid=3102)
    mesh = Object('ArmMesh', 'MESH', mesh_data, 301)
    mesh.vertex_groups = groups
    mesh.matrix_world = copy.deepcopy(mesh_world)
    mesh.evaluated = Object('ArmMesh', 'MESH', eval_data, 302)
    mesh.evaluated.matrix_world = copy.deepcopy(mesh_world)
    mesh.evaluated.original = mesh
    bones = Named()
    pose_bones = Named()
    for i, row in enumerate(packet['bone_chain']):
        bone = NS(name=row['name'], parent=bones[-1] if i else None,
            matrix_local=copy.deepcopy(row['rest_matrix']), use_deform=True, use_envelope_multiply=False,
            inherit_scale='FULL', use_inherit_rotation=True, use_local_location=True,
            bbone_segments=1)
        bones.append(bone)
        pose_bones.append(NS(name=row['name'], bone=bone,
            parent=pose_bones[-1] if i else None, matrix=copy.deepcopy(row['pose_matrix']),
            constraints=[], matrix_basis=rigid(), rotation_mode='QUATERNION'))
    rig_data = NS(name='ArmRigData', bones=bones, session_uid=3201, pose_position='POSE', animation_data=None)
    rig = Object('ArmRig', 'ARMATURE', rig_data, 401)
    rig.pose = NS(bones=pose_bones)
    rig.matrix_world = copy.deepcopy(rig_world)
    modifier = NS(name='Armature', type='ARMATURE', object=rig, show_viewport=True,
        show_render=True, use_vertex_groups=True, use_bone_envelopes=False,
        use_deform_preserve_volume=False, use_multi_modifier=False, vertex_group='', invert_vertex_group=False)
    mesh.modifiers = [modifier]
    layer = NS(update=lambda: None, objects=NS(active=mesh))
    scene = NS(name='ArmSourceQA', session_uid=11, objects=Named([mesh, rig]),
        unit_settings=NS(scale_length=scale, system='METRIC', length_unit='METERS'),
        frame_current=1, frame_subframe=0., view_layers=[layer])
    graph = NS(updates=[], object_instances=[], scene_eval=NS(original=scene))
    layer.depsgraph = graph
    bpy = NS(context=NS(scene=scene, view_layer=layer, evaluated_depsgraph_get=lambda: graph),
        data=NS(filepath='arm-source-qa.blend', objects=scene.objects),
        app=NS(driver_namespace={}, handlers=NS(depsgraph_update_post=[], undo_post=[],
            redo_post=[], load_post=[], persistent=lambda callback: callback)))
    from human_eye_plugin.blender_host import BlenderSceneHost
    host = BlenderSceneHost(bpy)
    selection = dict(mesh_name=mesh.name, bone_names=[b['name'] for b in packet['bone_chain']],
        vertex_indices=native_indices[:], sections=[[native_indices[i] for i in s] for s in packet['sections']])
    return NS(host=host, mesh=mesh, rig=rig, graph=graph, packet=packet,
        selection=selection, indices=native_indices, global_triangles=triangles, bpy=bpy)


def notify(fixture, obj, *, geometry=True):
    fixture.graph.updates = [NS(id=obj, is_updated_geometry=geometry, is_updated_transform=not geometry)]
    for callback in tuple(fixture.bpy.app.handlers.depsgraph_update_post):
        callback(fixture.host.scene, fixture.graph)
    fixture.graph.updates = []


def bind(fixture):
    from human_eye_plugin import arm_twist_source
    fixture.topology_reads = []
    def topology_reader(obj, vertices):
        fixture.topology_reads.append((obj, tuple(vertices)))
        allowed = set(vertices)
        return [face[:] for face in fixture.global_triangles if all(i in allowed for i in face)]
    source = arm_twist_source.ArmTwistSource(fixture.host, topology_reader=topology_reader)
    return source.bind(fixture.selection)


def set_pose(fixture, packet):
    mesh_from_rig = np.linalg.inv(np.asarray(fixture.mesh.matrix_world)) @ np.asarray(fixture.rig.matrix_world)
    points = transform(packet['current_vertices'], mesh_from_rig)
    for native, point in zip(fixture.indices, points):
        fixture.mesh.evaluated.data.vertices.rows[native].co = point
    for bone, source in zip(fixture.rig.pose.bones, packet['bone_chain']):
        bone.matrix = copy.deepcopy(source['pose_matrix'])
    fixture.active_packet = packet


def replay_selected(fixture):
    """Independent NumPy homogeneous LBS for changed static fake data."""
    rig_from_mesh = np.linalg.inv(np.asarray(fixture.rig.matrix_world)) @ np.asarray(fixture.mesh.matrix_world)
    mesh_from_rig = np.linalg.inv(rig_from_mesh)
    deform = {i: np.asarray(p.matrix) @ np.linalg.inv(np.asarray(b.matrix_local))
              for i, (b, p) in enumerate(zip(fixture.rig.data.bones, fixture.rig.pose.bones))}
    for native in fixture.indices:
        vertex = fixture.mesh.data.vertices.rows[native]
        point = rig_from_mesh @ np.r_[vertex.co, 1.]
        influences = [(group.group, group.weight) for group in vertex.groups
                      if group.group in deform and fixture.rig.data.bones[group.group].use_deform]
        total = sum(weight for _, weight in influences)
        current = sum(weight * (deform[index] @ point) for index, weight in influences) / total
        fixture.mesh.evaluated.data.vertices.rows[native].co = (mesh_from_rig @ current)[:3].tolist()


class ArmSourceTests(unittest.TestCase):
    def assert_capture(self, fixture, capture, *, static_patch=None):
        self.assertEqual(capture['schema'], 'arm-twist-source-capture-v1')
        source = capture['source']
        self.assertEqual(source['unit'], 'm')
        self.assertEqual(source['coordinate_frame'], 'armature_local')
        for field in ('instance_id', 'epoch', 'revision', 'static_revision', 'selection_key', 'frame'):
            self.assertIn(field, source)
        patch = capture['static_patch'] if static_patch is None else static_patch
        self.assertIsInstance(patch, dict)
        self.assertNotIn('current_vertices', patch)
        for bone in patch['bone_chain']:
            self.assertNotIn('pose_matrix', bone)
        self.assertEqual(set(patch['vertex_ids']), set(fixture.indices))
        order = [fixture.indices.index(native) for native in patch['vertex_ids']]
        remap = {native: i for i, native in enumerate(patch['vertex_ids'])}
        expected_sections = [[remap[i] for i in section] for section in fixture.selection['sections']]
        self.assertEqual(patch['sections'], expected_sections)
        expected_faces = [[remap[i] for i in face] for face in fixture.global_triangles]
        self.assertEqual({directed_triangle(face) for face in patch['triangles']},
                         {directed_triangle(face) for face in expected_faces})
        packet = getattr(fixture, 'active_packet', fixture.packet)
        scale = fixture.host._scale()
        np.testing.assert_allclose(patch['rest_vertices'], np.asarray(fixture.packet['rest_vertices'])[order] * scale,
                                   rtol=1e-12, atol=1e-13)
        np.testing.assert_allclose(patch['weights'], np.asarray(fixture.packet['weights'])[order], rtol=0, atol=1e-14)
        np.testing.assert_allclose(capture['current_vertices'], np.asarray(packet['current_vertices'])[order] * scale,
                                   rtol=1e-12, atol=1e-13)
        for i, bone in enumerate(patch['bone_chain']):
            self.assertEqual(bone['name'], fixture.selection['bone_names'][i])
            expected_rest = np.array(fixture.packet['bone_chain'][i]['rest_matrix'])
            expected_rest[:3, 3] *= scale
            expected_pose = np.array(packet['bone_chain'][i]['pose_matrix'])
            expected_pose[:3, 3] *= scale
            np.testing.assert_allclose(bone['rest_matrix'], expected_rest, rtol=1e-12, atol=1e-13)
            np.testing.assert_allclose(capture['pose_matrices'][i], expected_pose, rtol=1e-12, atol=1e-13)
        for collection in (fixture.mesh.data.vertices, fixture.mesh.evaluated.data.vertices):
            self.assertEqual(collection.iterations, 0)
            self.assertEqual(set(collection.reads), set(fixture.indices))
        self.assertEqual(fixture.mesh.to_mesh_calls + fixture.mesh.evaluated.to_mesh_calls, 0)
        return patch

    def test_selected_402_vertices_and_800_faces_do_not_expand_200000_vertex_asset(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        capture = bound.capture()
        patch = self.assert_capture(f, capture)
        self.assertTrue(capture['static_changed'])
        self.assertEqual(len(patch['rest_vertices']), 402)
        self.assertEqual(len(patch['triangles']), 800)
        expected = expert.prepare_patch(patch).analyze(capture['current_vertices'], capture['pose_matrices'])
        report = bound.analyze()
        for key, value in expected.items():
            if key != 'source_binding':
                self.assertEqual(report[key], value)
        self.assertEqual(report['source_binding'], 'local_armature_source_adapter')
        self.assertIn('source', report)

    def test_native_global_indices_and_sections_remain_correct_after_permuted_selection(self):
        native = [137 + 3 * ((i * 137) % 402) for i in range(402)]
        f = make_host(native_indices=native)
        self.addCleanup(f.host.close_residency)
        f.selection['vertex_indices'].reverse()
        bound = bind(f)
        first = bound.capture()
        patch = self.assert_capture(f, first)
        report = bound.analyze()
        for region, section in zip(report['regions'], f.selection['sections']):
            self.assertEqual(region['vertex_ids'], section)
        self.assertEqual(len(set(patch['vertex_ids'])), 402)

    def test_mesh_rig_relative_rigid_transforms_and_unit_are_applied_consistently(self):
        f = make_host(scale=.01, mesh_world=rigid(37., (1., -2., 3.)),
                      rig_world=rigid(-23., (-.7, 1.1, 2.3)))
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        first = bound.capture()
        self.assert_capture(f, first)
        prepared = bound.prepared
        f.host.scene.unit_settings.scale_length = .001
        second = bound.capture()
        self.assert_capture(f, second)
        self.assertTrue(second['static_changed'])
        self.assertIsNot(bound.prepared, prepared)
        self.assertNotEqual(first['source'], second['source'])

    def test_pose_and_frame_update_reuse_prepared_static_and_return_current_source(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        first = bound.capture()
        prepared = bound.prepared
        selected = next(c['packet'] for c in saved_cases()
            if c['metadata']['asset_id'] == next(c['metadata']['asset_id'] for c in saved_cases()
                if c['packet'] == f.packet)
            and c['metadata']['pose_family'] == 'normal_bend')
        set_pose(f, selected)
        f.host.scene.frame_current += 1
        notify(f, f.rig, geometry=False)
        notify(f, f.mesh, geometry=True)
        second = bound.capture()
        self.assertIs(bound.prepared, prepared)
        self.assertFalse(second['static_changed'])
        self.assertIsNone(second['static_patch'])
        self.assertNotEqual(first['source'], second['source'])
        self.assertEqual(first['source']['static_revision'], second['source']['static_revision'])
        self.assert_capture(f, second, static_patch=first['static_patch'])
        self.assertNotEqual(first['current_vertices'], second['current_vertices'])

    def test_dirty_notification_without_static_change_does_not_reprepare(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        first = bound.capture()
        prepared = bound.prepared
        f.global_triangles = [face[1:] + face[:1] for face in reversed(f.global_triangles)]
        f.global_triangles.append(f.global_triangles[0][:])
        notify(f, f.mesh.data)
        again = bound.capture()
        self.assertIs(bound.prepared, prepared)
        self.assertFalse(again['static_changed'])
        self.assertIsNone(again['static_patch'])
        self.assertEqual(again['source']['static_revision'], first['source']['static_revision'])

    def test_rest_weights_and_topology_changes_each_rebuild_preparation(self):
        for change in ('rest', 'weights', 'topology'):
            with self.subTest(change=change):
                f = make_host()
                self.addCleanup(f.host.close_residency)
                bound = bind(f)
                first = bound.capture()
                prepared = bound.prepared
                if change == 'rest':
                    for native in f.selection['sections'][0]:
                        f.mesh.data.vertices.rows[native].co[0] += 1e-4
                    replay_selected(f)
                elif change == 'weights':
                    local = next(i for i, row in enumerate(f.packet['weights']) if 0. < row[0] < 1.)
                    row = f.mesh.data.vertices.rows[f.indices[local]]
                    values = [.9 * value for value in f.packet['weights'][local]]
                    values[0] += .1
                    row.groups = [NS(group=i, weight=w) for i, w in enumerate(values) if w > 0.]
                    replay_selected(f)
                else:
                    section = f.selection['sections'][0]
                    added = [section[0], section[2], section[5]]
                    f.global_triangles.append(added)
                    f.mesh.data.polygons.append(NS(index=len(f.mesh.data.polygons), vertices=tuple(added), loop_total=3))
                notify(f, f.mesh.data)
                second = bound.capture()
                self.assertTrue(second['static_changed'])
                self.assertIsNotNone(second['static_patch'])
                self.assertIsNot(bound.prepared, prepared)
                self.assertNotEqual(first['source']['static_revision'], second['source']['static_revision'])

    def test_undo_and_load_reset_source_and_static_even_for_identical_geometry(self):
        for event in ('undo_post', 'load_post'):
            with self.subTest(event=event):
                f = make_host()
                self.addCleanup(f.host.close_residency)
                bound = bind(f)
                first = bound.capture()
                prepared = bound.prepared
                for callback in tuple(getattr(f.bpy.app.handlers, event)):
                    callback(f.host.scene)
                second = bound.capture()
                self.assertNotEqual(first['source']['epoch'], second['source']['epoch'])
                self.assertTrue(second['static_changed'])
                self.assertIsNot(bound.prepared, prepared)

    def test_same_name_mesh_or_rig_replacement_never_reuses_old_identity(self):
        for role in ('mesh', 'rig'):
            with self.subTest(role=role):
                f = make_host()
                self.addCleanup(f.host.close_residency)
                bound = bind(f)
                first = bound.capture()
                prepared = bound.prepared
                old = getattr(f, role)
                replacement = copy.copy(old)
                replacement.session_uid += 10000
                setattr(f, role, replacement)
                f.host.scene.objects[f.host.scene.objects.index(old)] = replacement
                if role == 'rig':
                    replacement.evaluated = replacement
                    f.mesh.modifiers[0].object = replacement
                else:
                    replacement.evaluated = copy.copy(old.evaluated)
                    replacement.evaluated.original = replacement
                second = bound.capture()
                self.assertNotEqual(first['source'], second['source'])
                self.assertTrue(second['static_changed'])
                self.assertIsNot(bound.prepared, prepared)

    def test_evaluated_original_allows_same_rna_alias_and_rejects_foreign_incarnation(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        alias = copy.copy(f.mesh)
        self.assertIsNot(alias, f.mesh)
        f.mesh.evaluated.original = alias
        self.assert_capture(f, bound.capture())
        foreign = copy.copy(f.mesh)
        foreign.session_uid += 10000
        f.mesh.evaluated.original = foreign
        with self.assertRaisesRegex(ValueError, '^evaluated_object_binding$'):
            bound.capture()

    def test_inflight_source_change_does_not_publish_partial_preparation(self):
        from human_eye_plugin import arm_twist_source
        f = make_host()
        self.addCleanup(f.host.close_residency)
        armed = [True]
        def reader(obj, indices):
            if armed[0]:
                armed[0] = False
                notify(f, f.mesh.data)
            return copy.deepcopy(f.global_triangles)
        bound = arm_twist_source.ArmTwistSource(f.host, topology_reader=reader).bind(f.selection)
        with self.assertRaisesRegex(ValueError, '^source_changed_during_capture$'):
            bound.capture()
        self.assertIsNone(bound.prepared)
        self.assertEqual(bound.work_totals()['captures'], 0)
        self.assertEqual(bound.work_totals()['preparations'], 0)
        self.assert_capture(f, bound.capture())

    def test_deleted_mesh_does_not_return_old_success(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        bound.capture()
        f.host.scene.objects.remove(f.mesh)
        with self.assertRaisesRegex(ValueError, '^mesh_not_found$'):
            bound.capture()

    def test_scene_switch_rebinds_identical_objects_to_new_epoch(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        bound = bind(f)
        first = bound.capture()
        prepared = bound.prepared
        scene = copy.copy(f.host.scene)
        scene.session_uid += 1000
        scene.name = 'OtherArmSourceQA'
        f.bpy.context.scene = scene
        f.graph.scene_eval = NS(original=scene)
        second = bound.capture()
        self.assertNotEqual(first['source']['epoch'], second['source']['epoch'])
        self.assertTrue(second['static_changed'])
        self.assertIsNot(bound.prepared, prepared)

    def test_chain_external_effective_bone_weight_is_not_silently_dropped(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        extra = NS(name='OutsideBone', parent=f.rig.data.bones[-1], matrix_local=rigid(), use_deform=True,
                   use_envelope_multiply=False, inherit_scale='FULL', use_inherit_rotation=True,
                   use_local_location=True, bbone_segments=1)
        f.rig.data.bones.append(extra)
        f.rig.pose.bones.append(NS(name=extra.name, bone=extra, parent=f.rig.pose.bones[-1],
                                  matrix=rigid(), constraints=[]))
        index = len(f.mesh.vertex_groups)
        f.mesh.vertex_groups.append(NS(name=extra.name, index=index))
        row = f.mesh.data.vertices.rows[f.indices[0]]
        for group in row.groups:
            group.weight *= .9
        row.groups.append(NS(group=index, weight=.1))
        with self.assertRaisesRegex(ValueError, '^unselected_deform_bone_weight$'):
            bind(f).capture()

    def test_nonbone_vertex_group_does_not_change_actual_deform_weights(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        index = len(f.mesh.vertex_groups)
        f.mesh.vertex_groups.append(NS(name='SelectionMask', index=index))
        f.mesh.data.vertices.rows[f.indices[0]].groups.append(NS(group=index, weight=.7))
        self.assert_capture(f, bind(f).capture())

    def test_missing_weights_or_corrupt_evaluated_same_index_are_rejected(self):
        for bad in ('unweighted', 'wrong_current'):
            with self.subTest(bad=bad):
                f = make_host()
                self.addCleanup(f.host.close_residency)
                if bad == 'unweighted':
                    f.mesh.data.vertices.rows[f.indices[0]].groups = []
                else:
                    f.mesh.evaluated.data.vertices.rows[f.indices[0]].co[0] += .01
                reason = 'unweighted_selected_vertex' if bad == 'unweighted' else 'same_index_lbs_readback_mismatch'
                with self.assertRaisesRegex(ValueError, '^' + reason + '$'):
                    bind(f).capture()

    def test_unsupported_deformation_semantics_are_rejected(self):
        for bad in ('DQ', 'envelopes', 'mask', 'shape_keys', 'editmode', 'other_modifier'):
            with self.subTest(bad=bad):
                f = make_host()
                self.addCleanup(f.host.close_residency)
                modifier = f.mesh.modifiers[0]
                if bad == 'DQ': modifier.use_deform_preserve_volume = True
                elif bad == 'envelopes': modifier.use_bone_envelopes = True
                elif bad == 'mask': modifier.vertex_group = 'Mask'
                elif bad == 'shape_keys': f.mesh.data.shape_keys = NS()
                elif bad == 'editmode': f.mesh.mode = 'EDIT'
                else: f.mesh.modifiers.append(NS(type='SUBSURF', name='Subsurf', show_viewport=True))
                reasons = {'DQ': 'unsupported_modifier_use_deform_preserve_volume',
                    'envelopes': 'unsupported_modifier_use_bone_envelopes',
                    'mask': 'unsupported_modifier_vertex_group',
                    'shape_keys': 'shape_keys_unsupported', 'editmode': 'mesh_edit_mode',
                    'other_modifier': 'single_armature_required'}
                with self.assertRaisesRegex(ValueError, '^' + reasons[bad] + '$'):
                    bind(f).capture()

    def test_selected_budget_is_checked_before_any_vertex_reads(self):
        f = make_host()
        self.addCleanup(f.host.close_residency)
        f.selection['vertex_indices'] = list(range(8193))
        with self.assertRaisesRegex(ValueError, '^selection_vertex_indices$'):
            bind(f).capture()
        self.assertEqual(f.mesh.data.vertices.reads, [])
        self.assertEqual(f.mesh.evaluated.data.vertices.reads, [])


if __name__ == '__main__':
    unittest.main()
