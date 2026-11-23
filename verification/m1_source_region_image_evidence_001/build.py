"""Build the one isolated serializer candidate from its fixed Git source."""

from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parent
BASE = 'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237'
CANDIDATE = 'e800667077a6c390dbc1f49aa46ba9a01b153de5'
ROOT = Path('D:/he_m1_source_region_image_evidence_001')
BASE_BINDING = V/'m4_source_region_curved_view_sample_001/install/PRODUCT_RUN_BINDING.json'
BUILDER = V/'m2_resident_capture_direct_delta_001/build.py'
CHANGES = ('human_eye_plugin/live_spatial_mcp.py',)


if __name__ == '__main__':
    build = run_path(str(BUILDER))['build']
    build.__globals__.update(HERE=HERE, ROOT=ROOT, BASE=BASE, CANDIDATE=CANDIDATE,
                             BASE_BINDING=BASE_BINDING, CHANGES=CHANGES,
                             VERSION='9.7.2+m1.source.region.image.evidence.001')
    build()
