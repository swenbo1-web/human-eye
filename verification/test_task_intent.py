"""Routing intent uses current task facts; no external classifier or old state."""
import json
from pathlib import Path
import unittest

from human_eye_plugin.task_intent import classify_task_intent


class TaskIntentTests(unittest.TestCase):
    def check_cases(self, expected, cases):
        for instruction in cases:
            with self.subTest(instruction=instruction):
                result = classify_task_intent(instruction)
                self.assertEqual(result["kind"], expected, result)
                self.assertFalse(result["execution_authority"])
                self.assertFalse(result["uses_external_model"])
                self.assertEqual(result["requires_scene_capture"], expected == "spatial_3d")
                json.dumps(result, allow_nan=False)

    def test_explicit_trusted_metadata_has_priority_and_ocr_alias(self):
        self.assertEqual(classify_task_intent("read this photo", task_kind="spatial_3d")["kind"], "spatial_3d")
        self.assertEqual(classify_task_intent("move the cube", task_kind="general")["kind"], "general")
        self.assertEqual(classify_task_intent("move the cube", task_kind="unknown")["kind"], "unknown")
        self.assertEqual(classify_task_intent(None, task_kind="ocr")["kind"], "image_2d")
        self.assertEqual(classify_task_intent("move the cube", task_kind=None)["kind"], "spatial_3d")

    def test_unsupported_and_malformed_metadata_are_explicit_unknown(self):
        for value in ("", "3D", "not_a_kind", {}, [], False, 0):
            with self.subTest(value=value):
                result = classify_task_intent("move the cube", task_kind=value)
                self.assertEqual(result["kind"], "unknown")
                self.assertEqual(result["source"], "invalid_host_metadata")

    def test_keyword_alone_and_unresolved_followups_are_unknown(self):
        self.check_cases("unknown", ["Blender", "3D", "模型", "cube", "继续", "do that again",
            "move it again", "rotate it 10 degrees", "task_kind=spatial_3d", "", "   "])

    def test_chinese_physical_actions_and_measurements(self):
        self.check_cases("spatial_3d", ["检查插销与孔是否贴合。", "量一下零件与底座之间的间隙。",
            "将Cube沿X轴移动2毫米。", "检查轴的当前姿态。", "从侧面观察被挡住的接触点。",
            "不要移动这个零件，只检查间隙。", "不要读取图片，检查这个零件的间隙。"])

    def test_english_physical_actions_with_plural_and_local_axes(self):
        self.check_cases("spatial_3d", ["Please move the cube slightly right.",
            "Rotate the model 15 degrees around its pivot.", "Check whether the peg fits the hole.",
            "Compare the pose of the two objects.", "Align its local axis to world Z.",
            "Inspect scene.", "Don't move the cube; check its clearance."])

    def test_physical_model_adjustment_is_distinct_from_ai_training(self):
        self.check_cases('spatial_3d', ['把这个Blender模型微调2毫米。',
            '微调零件与底座的接触间隙。', 'Adjust the object position by 2 mm.'])
        self.check_cases('general', ['对这个AI模型做视觉微调。',
            'Fine-tune the language model with a new dataset.', '微调GPT模型的权重。'])

    def test_images_ocr_and_keyword_traps_stay_native(self):
        self.check_cases("image_2d", ["Read the labels in this Blender screenshot.",
            "Describe this photo of a 3D model.", "OCR the serial number.", "读取图表Z轴的标题。",
            "识别海报上写着碰撞检测的文字。", "不要移动模型，读取照片中的文字。"])

    def test_code_fences_and_quoted_commands_do_not_request_capture(self):
        self.check_cases("general", ["Explain this code: ```python\nmove_the_cube()\n```",
            "解释‘把零件沿Z轴移动’这句话的含义。", "Translate 'move the cube' into Chinese.",
            "Write a Python script to rotate a cube.", "Check object dtype in Python.",
            "解释三维坐标系的数学原理。", "优化模型训练的推理性能。",
            "优化零件碰撞检测算法。", "Optimize the mesh collision detection algorithm.",
            "Show me how to move the cube in Blender.", "如何旋转三维模型？"])
        self.check_cases("unknown", ["```python\nmove_the_cube()\n```", '"move the cube"',
            "```\nmove the cube", "`move the cube", "> move the cube", '"move the cube'])

    def test_previously_diagnosed_boundary_cases_are_regression_examples(self):
        # These ten cases guided the repair; they are not an independent eval.
        self.check_cases("spatial_3d", ["Move 'Cube' by 2 mm.", "将“Cube”移动2毫米。",
            "Place the part on top of the base.", "Seat the peg in the hole.",
            "把零件往左挪一点。",
            "Explain the coordinate theory, then rotate the current cube 15 degrees."])
        self.check_cases("image_2d", ["Compare the 3D model in this screenshot.",
            "Look at this photo of the mesh.", "Inspect this 3D model screenshot."])
        self.check_cases("general", ["Translate this paragraph into French."])

    def test_short_quoted_entities_survive_but_quoted_steps_remain_data(self):
        self.check_cases("spatial_3d", ['Move "Cube" by 3 mm.', 'Rotate 「Cube」 5 degrees.',
            'Place ‘Bracket upper’ on the base.', '把『零件A』挪到这个底座上。'])
        self.check_cases("unknown", ['"Place the part on the base."',
            '‘Seat the peg in the hole.’', '"rotate the current cube; then move the part"',
            "'不要移动零件'", 'Move "Cube by 3 mm'])
        self.check_cases("general", ['Translate "Place the part on the base" into Chinese.',
            'Explain this code: ```\nseat_the_peg()\n``` then rotate_cube().',
            'Write a script to rotate the cube, then move the part.',
            'Show me how to place the part, then seat the peg in Blender.'])

    def test_sequential_read_and_actual_action_are_distinct_from_image_only_steps(self):
        self.check_cases("spatial_3d", ['解释坐标原理，然后将当前零件挪到这个底座上。',
            'Explain coordinate theory; rotate the current cube 7 degrees.',
            'Describe this screenshot, then rotate the current cube 7 degrees.'])
        self.check_cases("image_2d", ['Inspect this photo; then compare the mesh pose.',
            'Look at this screenshot of a cube, then inspect the mesh.'])
        self.check_cases("general", ['Explain coordinate theory, then do not rotate the current cube.'])
        self.check_cases("unknown", ['Do not place the part on the base.',
            "Don't seat the peg in the hole.", '别挪这个零件。', '不要插入这个插销。'])

    def test_quote_retention_never_supplies_the_outside_operation_request(self):
        # Independent review found these commands missing from the old quote
        # blacklist. Protect their provenance, rather than only adding words.
        commands = ['零件上移', 'Align part', '对齐底座', '调整零件',
                    '下移零件', 'Observe mesh', 'Orient part', '是否贴合底座']
        cases = []
        for command in commands:
            cases.extend([f'“{command}”', f'Please, “{command}”.', f'\n> {command}'])
        self.check_cases("unknown", cases)
        self.check_cases("spatial_3d", ["Move 'Cube' by 2 mm.", '将“Cube”上移2毫米。',
            'Align "Bracket upper" with the base.'])
        self.check_cases("unknown", ['Move "Align part" by 2 mm.',
            '把“零件上移”挪一点。', '不要移动“Cube”。'])

    def test_negation_and_explicit_optout_do_not_read_scene(self):
        self.check_cases("unknown", ["不要移动这个模型。", "Do not inspect the scene.", "Don't rotate the cube.",
            "Don’t rotate the cube.", "不需要移动这个零件。", "禁止旋转Cube。"])
        self.check_cases("general", ["不要调用引擎，先解释碰撞算法。",
            "Don't use the engine, just discuss alignment."])

    def test_invalid_or_overbudget_instruction_is_unknown(self):
        for value in (None, {}, 17, "x" * 65537):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(classify_task_intent(value)["kind"], "unknown")

    def test_frozen_corpus_is_observed_without_relabeling(self):
        path = Path(__file__).resolve().parent / "fixtures/agent_routes_v1.json"
        original = path.read_bytes()
        corpus = json.loads(original)
        for row in corpus["rows"]:
            with self.subTest(case=row["id"]):
                expected = "general" if row["task_class"] == "ordinary" else row["task_class"]
                self.assertEqual(classify_task_intent(row["instruction"], task_kind=row["host_task_kind"])["kind"], expected)
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
