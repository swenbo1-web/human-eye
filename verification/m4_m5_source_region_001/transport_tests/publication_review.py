"""Probe source-array versus first-publication-byte binding without real raster."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np
from human_eye_plugin import active_observation_images as images
from human_eye_plugin import source_region as core


def main():
    path = ROOT / 'verification/m4_m5_source_region_001/core_tests/test_source_region_core.py'
    spec = importlib.util.spec_from_file_location('_publication_review_fixture', path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    prepared = core.prepare_region(fixture.captured(), fixture.query())
    original_save, original_read = np.savez_compressed, Path.read_bytes
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        for reuse in (False, True):
            frame = None
            adapter = images.SceneObservationImages(prepared.objects, prepared.cameras,
                Path(directory) / str(reuse), scene_identity=prepared.binding['geometry_identity'],
                candidate_identity=prepared.binding['camera_identity'], _prepared_meshes=prepared.meshes,
                _reuse_published_payload=reuse)
            tampered = False
            def changed_first_read(target):
                nonlocal tampered
                if target.suffix == '.npz' and not tampered:
                    # Original encoder and disk write have completed. Simulate
                    # an external replacement immediately before first hash.
                    with np.load(io.BytesIO(original_read(target)), allow_pickle=False) as archive:
                        changed = {name: archive[name] for name in archive.files}
                    changed['color'][0, 0, 0] ^= 1
                    stream = io.BytesIO()
                    original_save(stream, **changed)
                    target.write_bytes(stream.getvalue())
                    tampered = True
                return original_read(target)
            error = None
            try:
                with patch.object(images, 'rasterize_attention', return_value=fixture.buffers(prepared, 512)), \
                        patch.object(Path, 'read_bytes', new=changed_first_read):
                    frame = adapter.render_view('SCENE')
                adapter.validate_frame(frame)
                accepted = True
            except ValueError as exc:
                accepted, error = False, str(exc)
            if frame is not None:
                with np.load(frame['arrays_path'], allow_pickle=False) as arrays:
                    disk_matches_source = np.array_equal(arrays['color'], frame['buffers']['color'])
            else:
                disk_matches_source = False
            cases.append(dict(reuse_published_payload=reuse, accepted=accepted, error=error,
                              disk_color_matches_source_color=disk_matches_source, disk_tamper_injected=tampered))
    result = dict(schema='source-region-publication-window-review-v1', cases=cases,
        no_weakening=cases[0]['accepted'] == cases[1]['accepted'],
        probe='Original serializer completes. Path.read_bytes interceptor replaces the NPZ before the first persisted-byte SHA.',
        actual_Blender=0, actual_raster=0, synthetic_raster_buffers=2, synthetic_PNG_writes=2,
        product_source_pins=[dict(path=str(Path(module.__file__).resolve()),
            sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()) for module in (images, core)])
    target = Path(__file__).parent / 'PUBLICATION_WINDOW_REVIEW.json'
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
