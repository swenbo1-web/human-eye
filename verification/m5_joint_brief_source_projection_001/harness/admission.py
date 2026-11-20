"""Admit the one joint qualification and require the direct installed source delta."""

from common import GLOBAL, PRODUCT_BINDING, PRODUCT_GIT, RASTER, SOURCE_SHA, WHEEL_SHA, load_retained, read


SCHEMA = 'm5-joint-brief-source-projection-v1'
_previous = load_retained('_m5_projection_admission_source', GLOBAL / 'harness/admission.py')
_previous.SCHEMA = SCHEMA
verify_freeze, publication, can_continue, admit = (
    _previous.verify_freeze, _previous.publication, _previous.can_continue, _previous.admit,
)


def registered_product():
    product = read(PRODUCT_BINDING)
    baseline = read(RASTER / 'install/PRODUCT_RUN_BINDING.json')
    changed = ['human_eye_plugin/live_spatial_mcp.py']
    old, new = ({row['path']: row['sha256'] for row in item['source_manifest']}
                for item in (baseline, product))
    if (len(old) != 143 or new.keys() != old.keys()
            or [name for name in old if old[name] != new[name]] != changed
            or product['historical_preparation_git'] != baseline['preparation_git']
            or product['historical_source_sha256'] != baseline['source_sha256']
            or product['changed_product_sources'] != changed
            or (product['preparation_git'], product['source_sha256'], product['wheel_sha256'])
            != (PRODUCT_GIT, SOURCE_SHA, WHEEL_SHA)):
        raise ValueError('fixed_direct_projection_install_required')
    return {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}


_previous.registered_product = registered_product
