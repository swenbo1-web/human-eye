"""Build the one sparse-view candidate using the retained verified wheel builder."""

from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parent
BASE = 'e956eedc81058c93b0e60a7e901e28395939d7f1'
CANDIDATE = 'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237'
ROOT = Path('D:/he_m4_source_region_curved_view_sample_001')
BASE_BINDING = V/'m1_source_region_world_box_001/install/PRODUCT_RUN_BINDING.json'
BUILDER = V/'m2_resident_capture_direct_delta_001/build.py'
CHANGES = ('human_eye_plugin/attention_raster.py', 'human_eye_plugin/live_service.py',
           'human_eye_plugin/live_spatial_mcp.py', 'human_eye_plugin/source_region.py')


if __name__ == '__main__':
    build = run_path(str(BUILDER))['build']
    build.__globals__.update(HERE=HERE, ROOT=ROOT, BASE=BASE, CANDIDATE=CANDIDATE,
                             BASE_BINDING=BASE_BINDING, CHANGES=CHANGES,
                             VERSION='9.7.2+m4.source.region.curved.view.sample.001')
    build()
