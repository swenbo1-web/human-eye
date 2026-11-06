"""A released surface index must not depend on cyclic GC to free its arrays."""
import gc
import unittest
import weakref

import numpy as np

from human_eye_fast.fast_bvh_clearance import SurfaceIndex


def released_index_references(face_count):
    vertices = np.arange(face_count * 9, dtype=np.float64).reshape(-1, 3) * .01
    faces = np.arange(face_count * 3).reshape(-1, 3)
    index = SurfaceIndex(vertices, faces)
    index.update(vertices + .125)
    return {
        "index": weakref.ref(index),
        "topology": weakref.ref(index._topology),
        "packed_vertices": weakref.ref(index._packed.vertices),
        "packed_edges": weakref.ref(index._packed.edges),
    }


class SurfaceIndexLifecycleTests(unittest.TestCase):
    def test_releases_index_and_owned_arrays_without_cycle_collection(self):
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            for face_count in (0, 1, 4, 5, 33, 512):
                with self.subTest(face_count=face_count):
                    references = released_index_references(face_count)
                    alive = [name for name, reference in references.items() if reference() is not None]
                    self.assertEqual(alive, [])
        finally:
            if was_enabled:
                gc.enable()
            # Test-only cleanup of a failing old implementation, never runtime policy.
            gc.collect()


if __name__ == "__main__":
    unittest.main()
