"""Materialize fixed initial whole and forearm views from the original copy."""

from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job


def main():
    started, cpu = time.perf_counter(), time.process_time()
    case = read("SOURCES.json")["cases"][0]
    result = run_job("blender_render.py", dict(current_blend=case["base_blend_path"], object_name=case["object_name"],
        source_original=case["source_original"], output_dir=str(HERE / "private/views/before")), "s01_original_context_views")
    write("BASE_VIEWS.json", dict(status=result["receipt"]["status"], views=result["receipt"]["views"],
        world_to_image_definition="affine projection exported from actual Blender world_to_camera_view at world origin and three unit axes",
        source_blend=result["receipt"]["current_blend"], renderer=identity(HERE / "blender_render.py"), job=result,
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu))
    print("four fixed initial views ready", flush=True)


if __name__ == "__main__":
    main()
