"""Freeze M4-A2 feasibility checks before collecting evaluated rig evidence."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification/fixes/20261102_m4_rig_evaluation'

if __name__=='__main__':
    OUT.mkdir(exist_ok=False)
    spec=dict(stage='M4-A2 feasibility, not production support',
        domain='owned factory scenes; original rest/control inputs, external dependencies and evaluated pose kept separate',
        budgets=dict(objects=8,bones=8,constraints=8,curves=8,keyframes_per_curve=16,driver_variables=4,
            snapshot_bytes=512*1024,case_timeout_seconds=30,angle_atol_deg=.001,position_atol=2e-4),
        candidate='one active full-influence all-axis WORLD/WORLD REPLACE Copy Rotation from a static unparented local Empty; rigid rig transform, default inheritance',
        oracle='authored rotations with independently computed NumPy FK/rotation matrices; IK endpoint and segment distances from analytic two-link reach only',
        checks=['zero input basis with nonzero evaluated orientation; never label solved output as authored channel',
            'target rotation change, unchanged names with different file/instance, parent/rig world rotation, unchanged and changed frames',
            'constraint influence/mute/spaces/order, missing target, target animation/driver/parent, nonrigid matrix and external bone target excluded from candidate',
            'IK reachable targets, opposite poles, unreachable/fully extended/zero-distance/pole-collinear targets, stretch and alternate chain length',
            'explicit dependency source changes even if output unchanged; stale packet, omitted target, missing/changed settings refused',
            'original/evaluated channels/rest and context before/after identical; blend SHA unchanged; whole-process timeout and output bound',
            'A1 unchanged and still unsupported for constraints/IK/animation/drivers; no product admission by deleting a flag'],
        limitations=['IK endpoint truth is not full 3D joint orientation or branch truth',
            'single-frame identity cannot prove animation history or continuous stability',
            'all-scene dependency capture is a finite conservative probe, not general arbitrary-rig closure',
            'no skinning, repair, product activation, paid model trial or learning'],
        shared_GUI=False,formal_model_trials=0)
    (OUT/'PREREGISTERED.json').write_text(json.dumps(spec,indent=2),encoding='utf8')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before=dict(commit='17a8c480ea980942016b0e5f27ce1608a629937d',
        runtime={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'human_eye_plugin').rglob('*.py'))},
        seals={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')},
        config_sha256=sha(ROOT/'.codex/config.toml'))
    (OUT/'BEFORE.json').write_text(json.dumps(before,indent=2),encoding='utf8')
    print(OUT)
