"""Preregister the independent, finite static Copy Rotation product domain."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/fixes/20261102_m4_constraint_product'

if __name__=='__main__':
    OUT.mkdir(exist_ok=False);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    spec=dict(domain='one pose Copy Rotation, external local Empty, WORLD/WORLD, REPLACE, all axes, full influence, enabled, valid, no offset, AUTO Euler order',
        excluded=['animation/drivers on rig/data/target','any other pose/object/target constraint','parents on rig/target','linked IDs',
            'custom spaces/subtargets','nonrigid/reflected transforms','nondefault inheritance/B-bone','nonzero bone channel translation','IK/skin/edit/save'],
        budgets=dict(bones=64,scene_objects=32,snapshot_bytes=512*1024,delivery_bones=16,reads_per_process=16,original_window_ns=30_000_000_000),
        tolerances=dict(rigid_matrix_atol=2e-5,consistency_rotation_atol=6e-5,angle_guard_deg=.001,endpoint_relative_atol=2e-6),
        semantics='input basis is separately reported; constrained world rotation must match target; unconstrained local FK rotations must match basis',
        sources='fixed file/frame/runtime/profile, rig epoch/instance/rest, target identity/channels/matrices, exact constraint settings, before/after audit; double-read and immutable task source',
        checks=['X/Y/Z and composed 3D target, noncommuting parent/world/rest rotations, root and descendant cases, quaternion sign',
            '64/65 bones, full counting/16 delivery, unsupported settings and dependencies, frame and wrong target',
            'strict packets/JSON/booleans, stale target/rig/document/frame/source, rehashed corruption and matrix/endpoint disagreement',
            'original deadline including startup, expired/extended request, 16 lifetime reads, single flight, profile/file/source drift',
            'independent NumPy matrices, external raw/evaluated RNA unchanged, input file unchanged, zero setter/save',
            'unchanged A1 source and behavior, isolated build/install byte equality, actual current-Codex fixed CLI read'],
        rules='orientation facts only in this domain; no role rule policy admitted, no damage classification',
        activation='new isolated fixed read-only CLI only; default MCP/hooks unchanged',formal_model_trials=0)
    (OUT/'PREREGISTERED.json').write_text(json.dumps(spec,indent=2),encoding='utf8')
    before=dict(runtime={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'human_eye_plugin').glob('*.py')},
        seals={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')},
        config_sha256=sha(ROOT/'.codex/config.toml'),commit='a9055239b76a6e7e65c1048ca285d84a9aea74b0')
    (OUT/'BEFORE.json').write_text(json.dumps(before,indent=2),encoding='utf8');print(OUT)
