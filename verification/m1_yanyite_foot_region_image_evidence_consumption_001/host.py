"""Reuse the bilateral runtime for two installed evidence endpoints."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
V = HERE.parent
PRIOR_HOST = V/'m4_yanyite_bilateral_region_native_001/host.py'
PRODUCT_BINDINGS = {
    'A1': V/'m4_source_region_curved_view_sample_001/install/PRODUCT_RUN_BINDING.json',
    'B1': V/'m1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json',
}
PRODUCTS = {
    'A1': {'commit':'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237',
           'source_sha256':'98b95613011bf66d4b80b382fefbee8f3073c1c25d9891d21f21d698c53981e1',
           'wheel_sha256':'23cce9d9b042770f3d77147b9b0e1c06a6790c9f6dd196bb7da74b7d8322291c'},
    'B1': {'commit':'e800667077a6c390dbc1f49aa46ba9a01b153de5',
           'source_sha256':'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e',
           'wheel_sha256':'a866444b62bd03d4588800d930436bd0aa88509aabadf54bc9a16f9777a987c8'},
}


def catalogue_path(label):
    return HERE/'inputs'/f'{label}_EVIDENCE_TOOLS_SCHEMA.json'


source, bottom = PRIOR_HOST.read_text(encoding='utf8').rsplit("\nif __name__ == '__main__':", 1)
for old,new in (
    ('D:/he_m4_yanyite_bilateral_region_native_001', 'D:/he_m1_yanyite_foot_region_image_evidence_consumption_001'),
    ("PRODUCT_BINDING = V/'m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json'",
     "PRODUCT_BINDING = PRODUCT_BINDINGS['A1']"),
    ("SLOTS = {'N1': ('N', 'formal'), 'P1': ('P', 'formal')}",
     "SLOTS = dict.fromkeys(PRODUCT_BINDINGS, ('P','formal'))"),
    ('f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md',
     '8cf6015bc5dd7594298a30cb1687bea849760de6:docs/M1_YANYITE_FOOT_REGION_IMAGE_EVIDENCE_CONSUMPTION_001_PLAN.md'),
    ('def assemble(root, label, binding_path=PRODUCT_BINDING):', 'def assemble(root, label, binding_path=None):'),
    ('    bind = fixed_binding(binding_path)', '    bind = fixed_binding(label, binding_path)'),
    ("    common.PRODUCT_BINDING, common.PRODUCT_GIT = PRODUCT_BINDING, PRODUCT['commit']\n"
     "    common.SOURCE_SHA, common.WHEEL_SHA = PRODUCT['source_sha256'], PRODUCT['wheel_sha256']\n"
     "    common.PRODUCT = PRODUCT\n",
     "    product = PRODUCTS[label]\n"
     "    common.PRODUCT_BINDING, common.PRODUCT_GIT = PRODUCT_BINDINGS[label], product['commit']\n"
     "    common.SOURCE_SHA, common.WHEEL_SHA = product['source_sha256'], product['wheel_sha256']\n"
     "    common.PRODUCT = product\n"
     "    common.PRODUCT_SCHEMA = HERE/'inputs/PRODUCT_SCHEMA.json'\n"
     "    common.CATALOGUE = catalogue_path(label)\n"),
    ("        return load('consumer', CONSUMER_DRIVER, source)",
     "        consumer = load('consumer', CONSUMER_DRIVER, source)\n"
     "        consumer.LABELS = dict.fromkeys(SLOTS, 'P')\n"
     "        return consumer"),
    ('M4-YANYITE-BILATERAL-REGION-NATIVE-001-', 'M1-YANYITE-FOOT-REGION-IMAGE-EVIDENCE-CONSUMPTION-001-'),
    ('worker._start_public_mcp(PRODUCT_BINDING, bind)', 'worker._start_public_mcp(PRODUCT_BINDINGS[label], bind)'),
    ("    require([tool for tool in reports['P1']['tools'] if tool['name'] != 'human_eye_scene_observe'] ==\n"
     "            reports['N1']['tools'], 'ordinary_catalogue_not_equivalent_across_fresh_processes')",
     "    require(catalogues_equivalent(reports['A1']['tools'], reports['B1']['tools']),\n"
     "            'tool_catalogue_changed_outside_evidence_guide')"),
):
    if source.count(old) != 1:
        raise RuntimeError(f'unchanged_bilateral_assembly_anchor_required/{old}')
    source = source.replace(old, new)
exec(compile(source, str(PRIOR_HOST), 'exec'), globals())


def fixed_binding(label, path=None):
    actual_path = PRODUCT_BINDINGS[label]
    require(path is None or Path(path).resolve(strict=True) == actual_path.resolve(strict=True),
            'only_the_fixed_slot_install_is_admitted')
    bind = read(actual_path)
    product = PRODUCTS[label]
    require((bind['preparation_git'],bind['source_sha256'],bind['wheel_sha256']) == tuple(product.values())
            and len(bind['source_manifest']) == 143 and sha(bind['wheel_path']) == product['wheel_sha256'],
            'fixed_candidate_or_wheel_changed/'+label)
    return bind


def catalogues_equivalent(a,b):
    from copy import deepcopy

    left,right = deepcopy(a),deepcopy(b)
    one,two = (next(row for row in tools if row['name']=='human_eye_scene_observe') for tools in (left,right))
    old,new = (t.pop('description') for t in (one,two))
    previous = 'with include_image=false also returns the same evidence packet for all response_detail values. '
    updated = ('returns a brief when include_image=false or when a single sampled image has a verified '
               'source pixel and local path, including for explicit full. ')
    return left==right and old.count(previous)==1 and old.replace(previous,updated)==new


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv)==4 and
            sys.argv[1]=='--preflight-arm', 'only_fresh_isolated_arm_preflight_entry')
    sys.path.insert(0,str(HERE))
    _preflight_arm(Path(sys.argv[3]),sys.argv[2])
