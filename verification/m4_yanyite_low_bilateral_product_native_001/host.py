"""Reuse the accepted bilateral owned Blender and Codex ingress."""

from pathlib import Path


HERE = Path(__file__).resolve().parent
PRIOR_HOST = HERE.parent/'m4_yanyite_bilateral_region_native_001/host.py'
source = PRIOR_HOST.read_text(encoding='utf8')
for old,new in (
    ('D:/he_m4_yanyite_bilateral_region_native_001', 'D:/he_m4_yanyite_low_bilateral_product_native_001'),
    ('m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json',
     'm4_source_region_curved_view_sample_001/install/PRODUCT_RUN_BINDING.json'),
    ('4104add44251b03a1eafc5af69502aa2575b632c', 'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237'),
    ('5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
     '98b95613011bf66d4b80b382fefbee8f3073c1c25d9891d21f21d698c53981e1'),
    ('40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807',
     '23cce9d9b042770f3d77147b9b0e1c06a6790c9f6dd196bb7da74b7d8322291c'),
    ('f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md',
     'f4a49c75477870b07022cf82c4896cafd279be98:docs/M4_YANYITE_LOW_BILATERAL_PRODUCT_NATIVE_001_PLAN.md'),
    ("    common.add_paths()",
     "    common.PRODUCT_SCHEMA = HERE/'inputs/PRODUCT_SCHEMA.json'\n"
     "    common.CATALOGUE = HERE/'inputs/EVIDENCE_TOOLS_SCHEMA.json'\n"
     "    common.add_paths()"),
    ('M4-YANYITE-BILATERAL-REGION-NATIVE-001-', 'M4-YANYITE-LOW-BILATERAL-PRODUCT-NATIVE-001-'),
):
    if source.count(old) != 1:
        raise RuntimeError(f'unchanged_bilateral_assembly_anchor_required/{old}')
    source = source.replace(old, new)

exec(compile(source, str(PRIOR_HOST), 'exec'), globals())
