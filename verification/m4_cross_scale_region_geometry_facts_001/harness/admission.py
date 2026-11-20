"""Verify the frozen installation and admit only the registered candidate slot."""

from pathlib import Path

from common import EXTERNAL, NS, PRODUCT_BINDING, SLOTS, SOURCE_SHA, asset_identity, read, sha


SCHEMA = 'm4-cross-scale-region-geometry-facts-v1'
OLD = NS.parent / 'm4_cross_scale_brief_entry_001'
OLD_FREEZE_SHA = '0282e5377cef7673dc59d71d8bcf9e3c22da9b359ae1bff4ed822217c6c08338'
OLD_ADMISSION_SHA = '3821bfb7ef8a571ebc5af7428c24f807fde897ae265c22859a0567c2727d2853'
CANDIDATE = '1a4a96c3c890ab0ec3bce4d81ff090dd00f9b33e'
LIMITS = {'owned': 1, 'models': 1, 'business_per_slot': 12, 'raster_per_slot': 12,
          'raster_total': 12, 'additional_qualification': 0, 'builder': 0,
          'new_native_slots': 0, 'paid_API': 0, 'replacements': 0, 'task_s': 450, 'owned_s': 600}
GATE_INPUTS = ('checks/GEOMETRY_ORACLE.json', 'checks/PROJECTION_REPLAY.json',
               'checks/GEOMETRY_COST.json', 'install/BUILD_INSTALL.json')


def validate_admission(label, freeze_path, *, before_start=False):
    if label not in SLOTS or freeze_path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_candidate_and_freeze_required')
    if before_start and any((EXTERNAL / name).exists() for name in ('slots', 'budget')):
        raise ValueError('original_candidate_slot_or_budget_already_initialized')
    frozen = read(freeze_path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != ['P1'] or frozen['limits'] != LIMITS
            or frozen['candidate_commit'] != CANDIDATE):
        raise ValueError('original_candidate_or_limits_changed')
    pins = {}
    for row in frozen['direct_inputs']:
        path = Path(row['path']).resolve()
        if (path in pins or not path.is_file() or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']):
            raise ValueError('frozen_input_changed_or_ambiguous/' + str(path))
        pins[path] = row['sha256']
    gate_path = NS / 'ADMISSION.json'
    gate = read(gate_path)
    asset, asset_sha = asset_identity()
    freeze_sha = sha(freeze_path)
    expected = {name: pins[(NS / name).resolve()] for name in GATE_INPUTS}
    if (gate['passed'] is not True or gate['schema'] != SCHEMA or gate['slots'] != ['P1']
            or gate['freeze_sha256'] != freeze_sha or gate['asset_sha256'] != asset_sha
            or gate['product_source_sha256'] != SOURCE_SHA or pins[asset] != asset_sha
            or gate['gate_evidence_sha256'] != expected
            or gate['product_binding_sha256'] != pins[PRODUCT_BINDING.resolve()]
            or pins[(OLD / 'FROZEN.json').resolve()] != OLD_FREEZE_SHA
            or pins[(OLD / 'ADMISSION.json').resolve()] != OLD_ADMISSION_SHA):
        raise ValueError('candidate_not_bound_to_the_installed_offline_checks_and_historical_admission')
    return {'freeze_sha256': freeze_sha, 'admission_sha256': sha(gate_path)}
