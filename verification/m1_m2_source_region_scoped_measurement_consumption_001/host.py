"""Use the previously exercised owned Yanyite runner and current installed arms."""

import inspect
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PRIOR_HOST = HERE.parent/'m4_yanyite_bilateral_region_native_001/host.py'

def catalogue_path(label):
    return HERE/'inputs'/f'{label}_TOOLS.json'

def schema_path(label):
    return HERE/'inputs'/f'{label}_SCHEMA.json'

source = PRIOR_HOST.read_text(encoding='utf8')
for old, new in (
    ('D:/he_m4_yanyite_bilateral_region_native_001', 'D:/he_m1_m2_source_region_scoped_measurement_consumption_001'),
    ('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend',
     'D:/he_m4_yanyite_opposite_direction_product_native_001/slots/P1/native/input.blend'),
    ('m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json',
     'm1_m2_source_region_scoped_measurement_001/install/PRODUCT_RUN_BINDING.json'),
    ('4104add44251b03a1eafc5af69502aa2575b632c', 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'),
    ('5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
     '4a51c48524b66895819b69a30d2bd8eb020ce840028f0612f8d6e887c0423f09'),
    ('40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807',
     '7ff84ab1349d93a0810c687c8e3b0cea10d311c512380b5a9077305f35d5685d'),
    ('f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md',
     'b76c86712a13c895ec5845167f8b85ee18d35e92:docs/M1_M2_SOURCE_REGION_SCOPED_MEASUREMENT_CONSUMPTION_001_PLAN.md'),
    ("SLOTS = {'N1': ('N', 'formal'), 'P1': ('P', 'formal')}", "SLOTS = dict.fromkeys(('A1','B1'), ('P','formal'))"),
    ("    common.add_paths()",
     "    common.ASSET, common.ASSET_SHA256, common.asset_identity = ASSET, ASSET_SHA256, asset_identity\n"
     "    common.PRODUCT_SCHEMA = schema_path(label)\n"
     "    common.CATALOGUE = catalogue_path(label)\n"
     "    common.add_paths()"),
    ('M4-YANYITE-BILATERAL-REGION-NATIVE-001-', 'M1-M2-SOURCE-REGION-SCOPED-MEASUREMENT-CONSUMPTION-001-'),
):
    if source.count(old) != 1:
        raise RuntimeError(f'unchanged_yanyite_runtime_anchor_required/{old}')
    source = source.replace(old, new)
exec(compile(source, str(PRIOR_HOST), 'exec'), globals())
del source

METER = V/'m2_source_region_cold_selective_transport_001/meter.py'
TERMINAL = ASSET.parent.parent/'TERMINAL_SOURCE.json'
TERMINAL_SHA256 = 'dd47f22335c8f0fcd3e6e0aa764d5d174be89b49d9e488867813135bb64fd3e6'
_original_consumer = consumer_module
_original_sources = retained_sources

def asset_identity():
    path = ASSET.resolve(strict=True)
    require(path.stat().st_size == 3_415_766 and sha(path) == ASSET_SHA256
            and sha(TERMINAL) == TERMINAL_SHA256, 'fixed_current_yanyite_source_changed')
    return path, ASSET_SHA256

def consumer_module():
    consumer = _original_consumer()
    consumer.LABELS = dict.fromkeys(SLOTS, 'P')
    return consumer

def retained_sources():
    return (*_original_sources(),PRIOR_HOST,METER,METER.parent/'host.py',
            LIVE_M2/'meter.py',TERMINAL,
            *(path for label in SLOTS for path in (catalogue_path(label),schema_path(label))))
