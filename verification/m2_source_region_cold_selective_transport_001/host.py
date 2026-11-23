"""Bind the retained owned Blender runtime to the four selective-transport slots."""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
PREVIOUS = V/'m2_source_region_shared_normalization_live_001'
RUN = Path('D:/he_m2_source_region_cold_selective_transport_001').resolve()
BASE = 'e800667077a6c390dbc1f49aa46ba9a01b153de5'
LABELS = {'AA': ('assembly','A'), 'AB': ('assembly','B'), 'YA': ('yanyite','A'), 'YB': ('yanyite','B')}
SLOTS = dict.fromkeys(LABELS, ('P','formal'))
ASSETS = {
    'assembly': (Path('D:/he_m4_assembly_cross_asset_product_native_001/slots/P1/native/input.blend'),
                 '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'),
    'yanyite': (Path('D:/he_m4_yanyite_opposite_direction_product_native_001/slots/P1/native/input.blend'),
                '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'),
}
BINDINGS = {
    'A': V/'m1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json',
    'B': HERE/'install/PRODUCT_RUN_BINDING.json',
}
LIMITS = {'Blender_start_attempts':4,'all_rasters':0,'consumer_tasks':0,
          'tools_per_slot':3,'rasters_by_slot':dict.fromkeys(SLOTS,0)}
PRIVATE_TOOL = 'm2_private_source_region_measure'

retained = SimpleNamespace(**run_path(str(PREVIOUS/'host.py')))
read, sha, require, load = (retained.read, retained.sha, retained.require, retained.load)
WORKER, BLENDER = retained.WORKER, retained.BLENDER
CATALOGUE = V/'m4_assembly_cross_asset_product_native_001/inputs/EVIDENCE_TOOLS_SCHEMA.json'
PRODUCT_SCHEMA = CATALOGUE.with_name('PRODUCT_SCHEMA.json')
Slot = retained.Slot
_assemble = retained.assemble
owned_root = retained.owned_root
_retained = _assemble.__globals__
_retained.update(HERE=HERE,RUN=RUN,SLOTS=SLOTS,BINDINGS=BINDINGS,LIMITS=LIMITS,CATALOGUE=CATALOGUE,
                 PRODUCT_SCHEMA=PRODUCT_SCHEMA)


def binding_identity(label, path):
    arm = LABELS[label][1]
    require(Path(path).resolve(strict=True) == BINDINGS[arm].resolve(strict=True),
            'selective_owned_slot_binding_path')
    known = read(BINDINGS['A'])
    binding = known if arm == 'A' else read(path)
    require(known['preparation_git'] == BASE and len(binding['source_manifest']) == 143
            and sha(binding['wheel_path']) == binding['wheel_sha256'], 'fixed_selective_arm_identity')
    if arm == 'B':
        require(binding['historical_preparation_git'] == BASE
                and binding['historical_source_sha256'] == known['source_sha256']
                and binding['dependency_root'] == known['dependency_root']
                and Path(binding['install_root']).resolve(strict=True) == RUN/'candidate_install/product',
                'fixed_selective_candidate_install')
    return binding


def assemble(root,label,path):
    asset,digest = ASSETS[LABELS[label][0]]

    def asset_identity():
        resolved = asset.resolve(strict=True)
        require(sha(resolved) == digest, 'fixed_selective_asset_changed')
        return resolved,digest

    _retained.update(ASSET=asset,ASSET_SHA256=digest,asset_identity=asset_identity,binding_identity=binding_identity)
    return _assemble(root,label,path)


_retained['assemble'] = assemble


def retained_sources():
    return {*retained.retained_sources(), HERE/'host.py', HERE/'mcp_entry.py', HERE/'meter.py',
            PREVIOUS/'host.py', PREVIOUS/'mcp_entry.py', PREVIOUS/'meter.py',
            *(row[0] for row in ASSETS.values())}
