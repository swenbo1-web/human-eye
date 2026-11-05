"""Exercise the production PNG encoder with CPU-only independent decoding.

The Blender module cannot be imported without Blender. Extract its actual
PNG declarations, CPU-buffer initialization, and encoding statements from
the AST instead; do not maintain a second implementation of the encoder.
"""

import ast
from io import BytesIO
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
import zlib

import numpy as np
from PIL import Image


RUNTIME = Path(__file__).resolve().parents[1] / "human_eye_fast/raycast_saccade_gpu.py"


def _production_cpu_encoder():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"), filename=str(RUNTIME))
    declarations = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_png_chunk":
            declarations.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in ("PANEL", "_PNG_PREFIX", "_PNG_END")
            for target in node.targets
        ):
            declarations.append(node)
        elif (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
              and node.target.id == "_PNG_PREFIX"):
            declarations.append(node)

    renderer = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == "VGRenderer")
    initializer = next(node for node in renderer.body
                       if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    buffer_start = next(index for index, node in enumerate(initializer.body)
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Attribute) and target.attr == "scanlines"
                            for target in node.targets))
    initialize = ast.parse("def initialize(self):\n    pass").body[0]
    initialize.body = initializer.body[buffer_start:]
    declarations.append(initialize)

    observe = next(node for node in renderer.body
                   if isinstance(node, ast.FunctionDef) and node.name == "observe")
    encode_start = next(index for index, node in enumerate(observe.body)
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == "source"
                            for target in node.targets))
    encode = ast.parse("def encode(self, data, metadata=None, bottom=None):\n    pass").body[0]
    encode.body = observe.body[encode_start:]
    declarations.append(encode)

    namespace = {
        "np": np, "struct": struct, "zlib": zlib,
        "Observation": lambda png, metadata, bottom: SimpleNamespace(
            png=png, metadata=metadata, bottom_rgba=bottom),
    }
    module = ast.fix_missing_locations(ast.Module(body=declarations, type_ignores=[]))
    exec(compile(module, str(RUNTIME), "exec"), namespace)
    buffers = SimpleNamespace()
    namespace["initialize"](buffers)
    return buffers, namespace["encode"]


class ProductionPNGCodec(unittest.TestCase):
    def test_random_opaque_frames_preserve_rows_stripes_and_reuse(self):
        buffers, encode = _production_cpu_encoder()
        allocations = tuple(id(getattr(buffers, name)) for name in
                            ("scanlines", "rgb_deltas", "rgb", "previous_row"))
        self.assertIs(buffers.rgb_deltas.base, buffers.scanlines)
        self.assertEqual(buffers.rgb.shape[0], 64)
        rng = np.random.default_rng(19271)
        for frame in range(3):
            with self.subTest(frame=frame):
                # Input has the same bottom-up layout as the real GPU readback.
                pixels = rng.integers(0, 256, (512, 1024, 4), dtype=np.uint8)
                pixels[:, :, 3] = 255
                # Distinct adjacent rows make resetting Up at a strip boundary
                # observable even if a particular random sample is repetitive.
                for boundary in range(64, 512, 64):
                    pixels[boundary - 1, :, :3] = (17 + frame, 91, boundary % 256)
                    pixels[boundary, :, :3] = (233 - frame, 7, (boundary + 63) % 256)
                encoded = encode(buffers, pixels)
                with Image.open(BytesIO(encoded.png)) as image:
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.size, (1024, 512))
                    restored = np.asarray(image.convert("RGBA"))
                expected = pixels[::-1]
                np.testing.assert_array_equal(restored, expected)
                np.testing.assert_array_equal(restored[[0, -1]], expected[[0, -1]])
                for boundary in range(64, 512, 64):
                    np.testing.assert_array_equal(
                        restored[boundary - 1:boundary + 1], expected[boundary - 1:boundary + 1])
                self.assertEqual(allocations, tuple(id(getattr(buffers, name)) for name in
                                                   ("scanlines", "rgb_deltas", "rgb", "previous_row")))


if __name__ == "__main__":
    unittest.main()
