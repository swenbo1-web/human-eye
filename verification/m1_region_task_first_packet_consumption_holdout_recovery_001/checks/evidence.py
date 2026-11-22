"""Reuse the frozen verifier with a single, bound witness lookup replacement."""

from hashlib import sha256
from pathlib import Path
from runpy import run_path


RECOVERY_NS = Path(__file__).resolve().parents[1]
OLD_NS = RECOVERY_NS.parent / 'm1_region_task_first_packet_consumption_holdout_001'
OLD_EVIDENCE = OLD_NS / 'checks/evidence.py'
OLD_EVIDENCE_SHA = 'fef32a58492e7f7376999f82fbc24769f2a0ddaf401035c47aec7dc6768c48ce'


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def scoped_witness_pixel(producer, witness, roi_id):
    """Read one source-owned witness using scope, frame, original image and ROI."""
    scope_id = witness['scope_id']
    _need(type(scope_id) is str and bool(scope_id), 'witness_scope_identity_invalid')
    scopes = [scope for scope in producer['scopes'] if scope['scope_id'] == scope_id]
    _need(len(scopes) == 1, 'witness_scope_missing_or_ambiguous')
    scope = scopes[0]
    binding, root = scope['binding'], producer['binding']
    current = ('capture_state', 'document_epoch', 'scene_revision')
    _need(binding['capture_state'] is not None and all(binding[key] == root[key] for key in current),
          'witness_scope_capture_generation_mismatch')
    if scope_id == 'global':
        _need(binding['capture_scope'] == 'complete_scene_meshes'
              and binding['binding_sha256'] == root['binding_sha256']
              and binding['source_binding_sha256'] == root['source_binding_sha256'],
              'witness_global_parent_binding_mismatch')
    else:
        _need(binding['capture_scope'] == 'same_capture_region_view'
              and binding['parent_binding_sha256'] == root['binding_sha256']
              and binding['parent_source_binding_sha256'] == root['source_binding_sha256'],
              'witness_local_parent_binding_mismatch')
    identity = witness['frame_identity']
    _need(scope['frame_refs'].count(identity) == 1, 'witness_frame_not_uniquely_registered_in_scope')
    frames = [frame for frame in producer['frames'] if frame['frame_identity'] == identity]
    _need(len(frames) == 1, 'witness_producer_frame_missing_or_ambiguous')
    frame = frames[0]
    _need(all(frame[key] == witness[key] for key in ('scope_id', 'frame_identity', 'image_ref', 'view_name'))
          and frame['host_binding_sha256'] == binding['binding_sha256']
          and frame['candidate_identity'] == binding['camera_identity']
          and frame['source_revision'] == binding['scene_revision'],
          'witness_frame_ref_view_or_binding_mismatch')
    observations = [item for item in scope['facts']['observations'] if item['frame_identity'] == identity]
    _need(len(observations) == 1, 'witness_scoped_observation_missing_or_ambiguous')
    observation = observations[0]
    _need(all(observation[key] == frame[key] for key in
              ('scope_id', 'frame_identity', 'image_ref', 'view_name', 'image_sha256', 'image_path')),
          'witness_scoped_observation_ref_view_or_png_mismatch')
    rows = observation['pixel_rows']
    pixel_index = witness['pixel_row_index']
    _need(type(pixel_index) is int and 0 <= pixel_index < len(rows), 'witness_pixel_row_index_invalid')
    pixel = rows[pixel_index]
    _need(pixel['roi_id'] == roi_id and pixel['view'] == witness['view_name']
          and pixel['readable'] is True and roi_id in observation['readable_roi_ids'],
          'witness_pixel_row_roi_view_or_readability_mismatch')
    return pixel


def _compile_frozen_checker():
    original = OLD_EVIDENCE.read_bytes()
    _need(sha256(original).hexdigest() == OLD_EVIDENCE_SHA, 'frozen_original_evidence_checker_changed')
    old = ("        observation, = [item for item in producer['facts']['observations']\n"
           "                        if item['frame_identity']==witness['frame_identity']]\n"
           "        pixel = observation['pixel_rows'][witness['pixel_row_index']]")
    new = "        pixel = scoped_witness_pixel(producer,witness,regions[name]['roi_id'])"
    text = original.decode('utf8').replace('\r\n', '\n')
    _need(text.count(old) == 1, 'one_exact_frozen_lookup_block_required')
    module = {'__file__': str(OLD_EVIDENCE), '__name__': 'frozen_region_task_with_scoped_recovery',
              'scoped_witness_pixel': scoped_witness_pixel}
    exec(compile(text.replace(old, new), str(OLD_EVIDENCE), 'exec'), module)
    return module


def verify_qualification(slot, result):
    """Run the same five archived qualification checks and unchanged close guards."""
    verify = run_path(str(OLD_NS / 'qualification/closed.py'))['verify']

    def recovery_only(path):
        if Path(path).resolve() == OLD_EVIDENCE.resolve():
            return _RECOVERY
        return run_path(path)

    verify.__globals__['run_path'] = recovery_only
    return verify(slot, result)


_RECOVERY = _compile_frozen_checker()
for _name in ('require', 'read', 'digest', 'pin', 'normalize_truth', 'verify_source', 'verify_discovery',
              'verify_readback', 'verify_measurement', 'fixed_cli', 'verify_closed', 'load_slot'):
    globals()[_name] = _RECOVERY[_name]
