"""Behavior and hostile-boundary contracts for current-scene prompt binding."""
import copy
import unittest

from human_eye_plugin.prompt_pairing import resolve_prompt_pair


def scene():
    return {'revision': 'frame-1', 'meshes': [
        {'object_id': 'id-blue', 'name': 'BluePart', 'mark_label': '#B0002', 'color_rgb': [20, 76, 230]},
        {'object_id': 'id-gray', 'name': 'GreyBase', 'mark_label': '#B0001', 'color_rgb': [107, 115, 128]},
    ]}


class PromptPairingTests(unittest.TestCase):
    def resolve(self, text, value=None):
        return resolve_prompt_pair(scene() if value is None else value, text, scene_fingerprint='snapshot-hash')

    def assert_pair(self, text, value=None, pair=('id-blue', 'id-gray')):
        result = self.resolve(text, value)
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual((result['focal_id'], result['reference_id']), pair)
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['uses_external_model'])
        self.assertEqual(result['scene_revision'], 'frame-1')
        self.assertEqual(result['scene_fingerprint'], 'snapshot-hash')
        return result

    def assert_unresolved(self, text, value=None):
        result = self.resolve(text, value)
        self.assertNotEqual(result['status'], 'resolved', result)
        self.assertIsNone(result['focal_id'])
        self.assertIsNone(result['reference_id'])
        self.assertEqual(result['evidence'], [])
        self.assertFalse(result['execution_authority'])
        return result

    def test_exact_names_current_scene(self):
        self.assert_pair('检查 BluePart 与 GreyBase 的间隙')

    def test_quoted_entity_names_preserve_spaces_and_connectors(self):
        value = scene()
        value['meshes'][0]['name'] = 'Blue 和 Grey, part'
        value['meshes'][1]['name'] = '底座.001'
        self.assert_pair('检查 “Blue 和 Grey, part” 与 「底座.001」 的间隙。', value)

    def test_english_measurement(self):
        self.assert_pair('Please measure the gap between BluePart and GreyBase.')

    def test_explicit_read_only_suffixes(self):
        self.assert_pair('再次检查 Blender 测试场景中 BluePart 与 GreyBase 的间隙，只观察，不移动。')
        self.assert_pair("check distance between BluePart and GreyBase, observe only, don't move.")

    def test_current_scene_context(self):
        self.assert_pair('请检查当前场景中的 BluePart 和 GreyBase 之间的距离。')

    def test_ids_and_current_host_mark_labels(self):
        self.assert_pair('检查 id-blue 与 id-gray 的间隙')
        self.assert_pair('检查 #B0002 与 #B0001 的间隙')

    def test_reverse_role_is_textual_not_motion(self):
        self.assert_pair('测量 GreyBase 与 BluePart 的距离', pair=('id-gray', 'id-blue'))

    def test_quoted_short_real_names_not_old_aliases(self):
        value = scene()
        value['meshes'][0]['name'], value['meshes'][1]['name'] = 'A', 'B'
        self.assert_pair('检查 "A" 与 "B" 的间隙', value)
        self.assert_unresolved('检查 A 与 B 的间隙', value)
        self.assert_unresolved('检查 A 与 B 的间隙')

    def test_unique_actual_blue_gray(self):
        result = self.assert_pair('检查 蓝色对象 与 灰色物体 的间隙')
        self.assertEqual(result['evidence'][0]['actual_rgb'], [20, 76, 230])
        self.assertEqual(result['evidence'][1]['actual_rgb'], [107, 115, 128])
        self.assertEqual(result['evidence'][0]['match_kind'], 'host_color_rgb')
        self.assertFalse(result['evidence'][0]['semantic_object_class_certified'])

    def test_pure_color_and_english_object(self):
        self.assert_pair('检查 蓝色 与 灰色 的间隙')
        self.assert_pair('inspect clearance between blue object and grey mesh')

    def test_typed_color_nouns_not_ignored(self):
        for instruction in ('检查蓝色零件与灰色底座的间隙',
                            'check gap between blue part and grey base',
                            '检查蓝色模型与灰色物体的距离'):
            with self.subTest(instruction=instruction):
                self.assert_unresolved(instruction)

    def test_color_name_does_not_supply_actual_color(self):
        value = scene(); value['meshes'][0]['color_rgb'] = [230, 20, 20]
        self.assert_unresolved('检查蓝色对象与灰色对象的距离', value)
        self.assert_pair('检查BluePart与GreyBase的距离', value)

    def test_color_name_conflict(self):
        value = scene()
        value['meshes'][1]['name'] = '蓝色对象'
        self.assert_unresolved('检查蓝色对象与#B0001的距离', value)
        self.assert_pair('检查"蓝色对象"与"BluePart"的距离', value, pair=('id-gray', 'id-blue'))

    def test_duplicate_blue_objects(self):
        value = scene()
        value['meshes'].append({'object_id': 'other', 'name': 'Another', 'color_rgb': [0, 0, 255]})
        self.assert_unresolved('检查蓝色对象与灰色对象的距离', value)

    def test_boundary_blue_is_not_unique_certification(self):
        value = scene()
        value['meshes'].append({'object_id': 'other', 'name': 'Boundary', 'color_rgb': [90, 130, 190]})
        self.assert_unresolved('检查蓝色对象与灰色对象的距离', value)

    def test_boundary_gray_is_not_unique_certification(self):
        value = scene()
        value['meshes'].append({'object_id': 'other', 'name': 'Boundary', 'color_rgb': [90, 115, 130]})
        self.assert_unresolved('检查蓝色对象与灰色对象的距离', value)

    def test_color_inventory_missing_or_invalid(self):
        for color in (None, [20, 40], [20, 40, True], [20., 40, 200], [0, 0, 256]):
            value = scene()
            value['meshes'].append({'object_id': 'other', 'name': 'Unknown', 'color_rgb': color})
            self.assert_unresolved('检查蓝色对象与灰色对象的距离', value)

    def test_quoted_descriptors_are_literal(self):
        self.assert_unresolved('检查"蓝色对象"与"灰色对象"的距离')

    def test_unrecognized_attributes_not_dropped(self):
        for text in ('检查左边蓝色对象与灰色对象的距离',
                     '检查较大的BluePart与GreyBase的间隙',
                     '检查红色BluePart与GreyBase的间隙',
                     '检查左边的"BluePart"与"GreyBase"的间隙',
                     'measure gap between the left blue object and grey object'):
            with self.subTest(text=text): self.assert_unresolved(text)

    def test_duplicate_names_and_namespace_collision(self):
        value = scene(); value['meshes'][1]['name'] = 'BluePart'
        self.assert_unresolved('检查BluePart与#B0001的间隙', value)
        value = scene(); value['meshes'][1]['name'] = 'id-blue'
        self.assert_unresolved('检查id-blue与id-gray的间隙', value)

    def test_substring_does_not_match(self):
        self.assert_unresolved('检查"Blue"与"Grey"的间隙')
        value = scene(); value['meshes'][0]['name'] = 'BluePart.001'
        self.assert_unresolved('检查BluePart与GreyBase的间隙', value)

    def test_no_pair_count_active_or_previous_guess(self):
        value = scene(); value['meshes'][0]['is_focal_target'] = True
        for text in ('检查当前场景的间隙', '检查BluePart的间隙', '继续观察', '检查它与底座的间隙'):
            self.assert_unresolved(text, value)

    def test_same_object_twice_not_pair(self):
        self.assert_unresolved('检查BluePart与id-blue的间隙')

    def test_third_selector_or_second_task_rejected(self):
        for text in ('检查BluePart与GreyBase与Other的间隙',
                     '检查BluePart与GreyBase的间隙；检查BluePart与Other的距离',
                     'check gap between BluePart and GreyBase and Other',
                     '检查BluePart与GreyBase的间隙，然后移动BluePart'):
            self.assert_unresolved(text)

    def test_negation(self):
        for text in ('不要检查BluePart与GreyBase的间隙',
                     '不必检查BluePart与GreyBase的间隙',
                     "don't check gap between BluePart and GreyBase",
                     'check no gap between BluePart and GreyBase'):
            self.assert_unresolved(text)

    def test_conditions_plans_examples_are_not_requests(self):
        for text in ('如果方便，检查BluePart与GreyBase的间隙',
                     '明天检查BluePart与GreyBase的间隙',
                     '例如：检查BluePart与GreyBase的间隙',
                     '计划检查BluePart与GreyBase的间隙',
                     'if ready check gap between BluePart and GreyBase',
                     'check gap between BluePart and GreyBase if ready'):
            self.assert_unresolved(text)

    def test_quoted_and_code_commands_not_executed(self):
        for text in ('"检查BluePart与GreyBase的间隙"',
                     '> 检查BluePart与GreyBase的间隙',
                     '```检查BluePart与GreyBase的间隙```',
                     '示例："检查BluePart与GreyBase的间隙"',
                     '`check gap between BluePart and GreyBase`'):
            self.assert_unresolved(text)

    def test_movement_not_inferred_as_measurement(self):
        for text in ('将BluePart移到底座GreyBase上', 'move BluePart to GreyBase',
                     '检查BluePart与GreyBase的间隙并调整到1毫米'):
            self.assert_unresolved(text)

    def test_literal_object_named_command_remains_data(self):
        value = scene(); value['meshes'][0]['name'] = 'if ready check'
        self.assert_pair('check gap between "if ready check" and GreyBase', value)

    def test_empty_and_malformed_input(self):
        self.assertEqual(self.resolve('')['status'], 'not_applicable')
        for text in (None, 1, False, {}, '检查"BluePart与GreyBase的间隙',
                     '检查""与GreyBase的间隙', '检查BluePart与GreyBase的间隙\x00'):
            self.assert_unresolved(text)

    def test_text_and_inventory_budgets(self):
        self.assert_unresolved('检查' + 'x' * 4096)
        for inventory in (None, [], {}, [{'object_id': 'x', 'name': 'a'}] * 2,
                          [{'object_id': str(i), 'name': 'a'} for i in range(2049)]):
            value = scene(); value['meshes'] = inventory
            self.assert_unresolved('检查BluePart与GreyBase的距离', value)

    def test_input_not_mutated(self):
        value = scene(); before = copy.deepcopy(value)
        self.assert_pair('检查BluePart与GreyBase的距离', value)
        self.assertEqual(value, before)

    def test_revision_and_ids_change_with_current_snapshot(self):
        first = self.resolve('检查BluePart与GreyBase的距离')
        value = scene(); value['revision'] = 'frame-2';value['meshes'][0]['object_id']='new-id'
        second = self.resolve('检查BluePart与GreyBase的距离', value)
        self.assertEqual(second['scene_revision'], 'frame-2')
        self.assertEqual(second['focal_id'], 'new-id')
        self.assertNotEqual(first['focal_id'], second['focal_id'])

    def test_original_long_whitespace_suffix_failures(self):
        for prefix, suffix in (('检查', '未支持结尾'), ('检查BluePart与GreyBase', '间隙z')):
            instruction = prefix + ' ' * (4096 - len(prefix) - len(suffix)) + suffix
            self.assert_unresolved(instruction)

    def test_growing_whitespace_runs_keep_meaning(self):
        for width in (0, 1, 8, 64, 512, 2048):
            gap = ' ' * width
            self.assert_pair('请' + gap + '检查BluePart与GreyBase的间隙')
            self.assert_unresolved('检查BluePart与GreyBase' + gap + '间隙z')

    def test_unquoted_internal_spaces_are_not_identity_normalized(self):
        value = scene(); value['meshes'][0]['name'] = 'Blue  Part'
        self.assert_pair('检查Blue  Part与GreyBase的间隙', value)
        self.assert_unresolved('检查Blue Part与GreyBase的间隙', value)
        value['meshes'].append({'object_id':'single-space', 'name':'Blue Part','color_rgb':[230,20,20]})
        self.assert_pair('检查Blue  Part与GreyBase的间隙', value)
        self.assert_pair('检查Blue Part与GreyBase的间隙', value, pair=('single-space','id-gray'))

    def test_quoted_internal_spaces_keep_exact_identity(self):
        value = scene(); value['meshes'][0]['name'] = 'Blue  Part'
        self.assert_pair('检查"Blue  Part"与"GreyBase"的间隙', value)
        self.assert_unresolved('检查"Blue Part"与"GreyBase"的间隙', value)

    def test_english_selector_original_tabs_and_spaces_kept(self):
        value = scene(); value['meshes'][0]['name'] = 'Blue\t  Part'
        self.assert_pair('check\t the  gap between  Blue\t  Part   and  GreyBase', value)
        self.assert_unresolved('check gap between Blue Part and GreyBase', value)


if __name__ == '__main__':
    unittest.main()
