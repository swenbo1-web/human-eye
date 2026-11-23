"""Build and verify one world box wheel from the fixed Git candidate."""

from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'m2_resident_capture_direct_delta_001'
ROOT = Path('D:/he_m1_source_region_world_box_001')
BASE = '4104add44251b03a1eafc5af69502aa2575b632c'
CANDIDATE = 'e956eedc81058c93b0e60a7e901e28395939d7f1'
BASE_BINDING = PREVIOUS/'install/PRODUCT_RUN_BINDING.json'
CHANGES = ('human_eye_plugin/live_service.py', 'human_eye_plugin/live_spatial_mcp.py',
           'human_eye_plugin/query_policy.py', 'human_eye_plugin/source_region.py')


if __name__ == '__main__':
    build = run_path(str(PREVIOUS/'build.py'))['build']
    build.__globals__.update(HERE=HERE, ROOT=ROOT, BASE=BASE, CANDIDATE=CANDIDATE,
                             BASE_BINDING=BASE_BINDING, CHANGES=CHANGES,
                             VERSION='9.7.2+m1.source.region.world.box.001')
    build()
