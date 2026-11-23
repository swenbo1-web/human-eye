"""Bind the accepted owned Blender and Codex runtime to the opposite-direction comparison."""

from pathlib import Path


HERE = Path(__file__).resolve().parent
PRIOR_HOST = HERE.parent/'m4_yanyite_bilateral_region_native_001/host.py'


def catalogue_path(label):
    if label != 'P1':
        raise ValueError('native_slot_has_no_product_catalogue')
    return HERE/'inputs/EVIDENCE_TOOLS_SCHEMA.json'


source = PRIOR_HOST.read_text(encoding='utf8')
for old,new in (
    ('D:/he_m4_yanyite_bilateral_region_native_001', 'D:/he_m4_yanyite_opposite_direction_product_native_001'),
    ('m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json',
     'm1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json'),
    ('4104add44251b03a1eafc5af69502aa2575b632c', 'e800667077a6c390dbc1f49aa46ba9a01b153de5'),
    ('5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
     'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e'),
    ('40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807',
     'a866444b62bd03d4588800d930436bd0aa88509aabadf54bc9a16f9777a987c8'),
    ('f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md',
     'f555c10cd9a85dbeeeb9d635e2f29f5f26639863:docs/M4_YANYITE_OPPOSITE_DIRECTION_PRODUCT_NATIVE_001_PLAN.md'),
    ("    common.add_paths()",
     "    common.PRODUCT_SCHEMA = HERE/'inputs/PRODUCT_SCHEMA.json'\n"
     "    common.CATALOGUE = catalogue_path('P1')\n"
     "    common.add_paths()"),
    ('M4-YANYITE-BILATERAL-REGION-NATIVE-001-', 'M4-YANYITE-OPPOSITE-DIRECTION-PRODUCT-NATIVE-001-'),
):
    if source.count(old) != 1:
        raise RuntimeError(f'unchanged_bilateral_assembly_anchor_required/{old}')
    source = source.replace(old, new)

exec(compile(source, str(PRIOR_HOST), 'exec'), globals())
