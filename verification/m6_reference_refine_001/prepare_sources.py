"""Copy the original full asset and independently read its actual baseline."""

from pathlib import Path
import shutil
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
import numpy as np

SOURCE = Path("D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend")
EXPECTED = "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
OBJECT = "0135bbc4-c6c7-4003-a402-6f2e0283497d"


def main():
    started, cpu = time.perf_counter(), time.process_time()
    before_source = identity(SOURCE)
    if before_source["sha256"] != EXPECTED:
        raise ValueError("original_baseline_identity_changed")
    directory = HERE / "private/cases/s01"
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(SOURCE, directory / "before.blend")
    previous = HERE.parent / "m6_refine_001/private/cases/s01/initial.npz"
    with np.load(previous, allow_pickle=False) as packet:
        names = ("vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids", "poly_offsets", "poly_vertices", "triangle_polygon_ids", "F_source_ids")
        baseline = {key:packet[key] for key in names}
    np.savez_compressed(directory / "seed.npz", **baseline)
    job = run_job("blender_read.py", dict(current_blend=str(directory / "before.blend"), object_name=OBJECT,
        source_original=str(SOURCE), base_npz=str(directory / "seed.npz"), expected_input_sha256=EXPECTED,
        readback_npz=str(directory / "baseline_readback.npz"), scene_signature_json=str(directory / "baseline_scene.json"),
        local_obj=str(directory / "seed_local.obj")), "s01_original_baseline_read")
    with np.load(directory / "baseline_readback.npz", allow_pickle=False) as packet:
        bitwise = {key:packet[key].dtype == baseline[key].dtype and packet[key].shape == baseline[key].shape and packet[key].tobytes() == baseline[key].tobytes()
            for key in baseline if key != "F_source_ids"}
    if not all(bitwise.values()):
        raise AssertionError("fresh_original_readback_differs_from_original_baseline")
    after_source = identity(SOURCE)
    if before_source != after_source:
        raise AssertionError("original_asset_changed")
    reference = Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")
    case = dict(case_id="s01", source_type="Yanyite", object_name=OBJECT, unit="m", source_original=str(SOURCE),
        source_identity=before_source, base_blend_path=str(directory / "before.blend"), initial_seed=str(directory / "seed.npz"),
        baseline_readback=str(directory / "baseline_readback.npz"), baseline_scene=str(directory / "baseline_scene.json"),
        prior_initial=identity(previous), bitwise_baseline_checks=bitwise)
    write("SOURCES.json", dict(cases=[case], reference_image=identity(reference), source_before=before_source,
        source_after=after_source, original_source_changes=0, engineering_bulge_used=False,
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu, background_job=job))
    print("original baseline copied and independently read", bitwise, flush=True)


if __name__ == "__main__":
    main()
