"""Preregister the finite M4 pose domain; no scene access or authorization."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/fixes/20261102_m4_rig_pose'

if __name__=='__main__':
    OUT.mkdir(exist_ok=False)
    spec=dict(domain='current saved frame, finite static FK armature, original rest plus evaluated pose; read-only',
        max_bones=64,max_source_bytes=512*1024,max_reported_bones=16,original_window_ns=30_000_000_000,
        rotation_matrix_atol=2e-5,angular_guard_deg=.001,
        metric='effective parent/rest-relative visual rotation; Y-axis swing/twist; no winding inference',
        unsupported=['constraints_or_IK','drivers_or_animation','nondefault_inheritance','bone_scale_or_shear','B_bone_segments'],
        policy='operator-authored rest/layout fingerprint and explicit local limits; absent policy is unassessed',
        checks=['known rotation, parent motion cancellation, rolled bones and FK chains',
            'same head/tail axial twist detected; quaternion signs and full-turn representation equivalent',
            'unit and object transform invariance including reflection; current frame bound without frame_set',
            '180-degree swing singularity and twist branch boundary remain unknown, not zero',
            'boundary guard, missing rules, wrong rig/reference, stale frame/instance and corrupt packet',
            '64/65 bone boundary, bytes/deadline, duplicate names and parent cycles',
            'independent fixture angle truth, actual RNA input/UI state before/after, zero save',
            'compact real Codex consumption separate from full evidence and formal model value'],
        shared_GUI=False,formal_model_trials=0)
    with (OUT/'PREREGISTERED.json').open('x',encoding='utf8') as f:json.dump(spec,f,indent=2)
    before=dict(seals={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')})
    with (OUT/'BEFORE.json').open('x',encoding='utf8') as f:json.dump(before,f,indent=2)
    (OUT/'CONFIG_BEFORE.toml').write_bytes((ROOT/'.codex/config.toml').read_bytes());print(OUT)
