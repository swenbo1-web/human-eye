"""Admit only the registered fresh plugin slot using the frozen single-variable preflight."""

from pathlib import Path

from common import EXTERNAL, NS, SLOTS, SOURCE_SHA, asset_identity, read, sha


SCHEMA = 'm4-cross-scale-brief-entry-v1'
LIMITS = {'owned': 1, 'models': 1, 'business_per_slot': 12, 'raster_per_slot': 12,
          'raster_total': 12, 'additional_qualification': 0, 'builder': 0,
          'new_native_slots': 0, 'paid_API': 0, 'replacements': 0, 'task_s': 450, 'owned_s': 600}
OLD = NS.parent / 'm4_cross_scale_live_task_formal_001'
OLD_FREEZE_SHA = '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c'
OLD_ADMISSION_SHA = '9d7996b4f8b955c6ade2aabd7dc37f62f143fe55cbebb4e2a824a11c38eb5707'


def verify_anchors(freeze_path):
    frozen = read(freeze_path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(SLOTS)
            or frozen['limits'] != LIMITS or list(SLOTS) != ['P1']):
        raise ValueError('one_fresh_plugin_slot_and_original_limits_required')
    anchors = {}
    for row in frozen['direct_inputs']:
        path = Path(row['path']).resolve()
        if (path in anchors or not path.is_file() or path.stat().st_size != row['bytes']
                or sha(path) != row['sha256']):
            raise ValueError('frozen_input_changed_or_ambiguous/' + str(path))
        anchors[path] = row
    return anchors


def validate_admission(label, freeze_path, *, before_start=False):
    if label not in SLOTS or freeze_path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_plugin_slot_and_freeze_required')
    if before_start and ((EXTERNAL / 'slots').exists() or (EXTERNAL / 'budget').exists()):
        raise ValueError('original_plugin_slot_or_budget_already_initialized')
    anchors = verify_anchors(freeze_path)
    gate_path = NS / 'ADMISSION.json'
    gate = read(gate_path)
    freeze_sha = sha(freeze_path)
    asset, asset_sha = asset_identity()
    preflight_path = (NS / 'checks/PREFLIGHT.json').resolve()
    if (gate['passed'] is not True or gate['schema'] != SCHEMA
            or gate['freeze_sha256'] != freeze_sha or gate['slots'] != ['P1']
            or gate['asset_sha256'] != asset_sha or gate['product_source_sha256'] != SOURCE_SHA
            or anchors[asset]['sha256'] != asset_sha or gate['evidence'] != anchors[preflight_path]
            or anchors[(OLD / 'FROZEN.json').resolve()]['sha256'] != OLD_FREEZE_SHA
            or anchors[(OLD / 'ADMISSION.json').resolve()]['sha256'] != OLD_ADMISSION_SHA):
        raise ValueError('plugin_slot_not_bound_to_formal_qualification_and_current_preflight')
    evidence = read(preflight_path)
    if evidence['passed'] is not True or any(
            anchors[Path(row['path']).resolve()] != row for row in evidence['source_pins']):
        raise ValueError('original_tool_results_or_prompt_preflight_not_frozen')
    return {'freeze_sha256': freeze_sha, 'admission_sha256': sha(gate_path)}
