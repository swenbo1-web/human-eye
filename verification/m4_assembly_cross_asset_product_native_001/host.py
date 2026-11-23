"""Bind the retained owned runtime to the fixed cross-asset assembly."""

from pathlib import Path


HERE = Path(__file__).resolve().parent
PRIOR_HOST = HERE.parent/'m4_yanyite_bilateral_region_native_001/host.py'
ASSET_BYTES = 106_640


def catalogue_path(label):
    if label != 'P1':
        raise ValueError('native_slot_has_no_product_catalogue')
    return HERE/'inputs/EVIDENCE_TOOLS_SCHEMA.json'


def asset_identity():
    path = ASSET.resolve(strict=True)
    require(path.stat().st_size == ASSET_BYTES and sha(path) == ASSET_SHA256, 'fixed_assembly_asset_changed')
    return path, ASSET_SHA256


source = PRIOR_HOST.read_text(encoding='utf8')
for old,new in (
    ('D:/he_m4_yanyite_bilateral_region_native_001', 'D:/he_m4_assembly_cross_asset_product_native_001'),
    ('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend',
     'D:/he_m4_cross_scale_assembly_transfer_001/slots/P1/native/input.blend'),
    ('614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d',
     '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'),
    ('m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json',
     'm1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json'),
    ('4104add44251b03a1eafc5af69502aa2575b632c', 'e800667077a6c390dbc1f49aa46ba9a01b153de5'),
    ('5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
     'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e'),
    ('40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807',
     'a866444b62bd03d4588800d930436bd0aa88509aabadf54bc9a16f9777a987c8'),
    ('f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md',
     '18b864a64597f690172215f4045bb59bc9ec36ae:docs/M4_ASSEMBLY_CROSS_ASSET_PRODUCT_NATIVE_001_PLAN.md'),
    ("    common.add_paths()",
     "    common.ASSET, common.ASSET_SHA256, common.asset_identity = ASSET, ASSET_SHA256, asset_identity\n"
     "    common.PRODUCT_SCHEMA = HERE/'inputs/PRODUCT_SCHEMA.json'\n"
     "    common.CATALOGUE = catalogue_path('P1')\n"
     "    common.add_paths()"),
    ('M4-YANYITE-BILATERAL-REGION-NATIVE-001-', 'M4-ASSEMBLY-CROSS-ASSET-PRODUCT-NATIVE-001-'),
):
    if source.count(old) != 1:
        raise RuntimeError(f'unchanged_assembly_anchor_required/{old}')
    source = source.replace(old,new)

exec(compile(source,str(PRIOR_HOST),'exec'),globals())
