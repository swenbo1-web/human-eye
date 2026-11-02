"""Freeze the finite static LBS source-correspondence domain before execution."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/fixes/20261102_m4_skin_source'
if __name__=='__main__':
    OUT.mkdir(exist_ok=False);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    spec=dict(domain='one enabled Armature modifier, static rigid FK rig, vertex groups only, linear blend skinning',
        budgets=dict(vertices=128,triangles=256,bones=64,influences_per_vertex=8,scene_objects=32,snapshot_bytes=512*1024,
            report_vertices=16,reads=16,original_window_ns=30_000_000_000),
        limits=dict(local_coordinate_abs=10.,world_translation_abs=100.,position_replay_atol=2e-5,weight_sum_atol=1e-6),
        equation='mesh_world^-1 @ rig_world @ sum(normalized w_i * (pose_i @ rest_i^-1) @ (rig_world^-1 @ mesh_world @ v))',
        unweighted='same-position replay, explicit partial/unweighted; not evidence of correct intended binding',
        rejected=['multiple/other/disabled modifier','DQ preserve volume','envelopes','mask/multi-modifier','shape keys',
            'linked/parented/constrained/driven/animated mesh or rig','nonrigid/reflected matrices or nondefault bones',
            'unknown/nondeforming positive-weight groups','nonunit nonzero weight sum','changed topology/indices','nonfinite/expired/stale source'],
        truth='independent NumPy LBS and authored coordinates/weights; test-only original-index POINT marker observed outside product',
        checks=['neutral, single bone, mixed rotations, bend, rigid-bone LBS collapse, different rest/world/units',
            'no weights/unused groups, renormalization refusal, wrong rig, shape key/DQ/modifier refusal',
            '128/129 vertices, 256/257 triangles and 8/9 influences, strict packet/JSON and rehashed corruption',
            'same count/topology insufficient without per-index replay; no edit mapping permission',
            'double read and outside original/evaluated RNA unchanged; input file unchanged',
            'new isolated fixed read-only entry, full regression/clean export and actual Codex read'],
        interpretation='source and displacement facts only, not damage/skin health/volume Jacobian',formal_model_trials=0)
    (OUT/'PREREGISTERED.json').write_text(json.dumps(spec,indent=2),encoding='utf8')
    before=dict(commit='b0d90796ee2b436bf44dae890990dc669fa767f7',config_sha256=sha(ROOT/'.codex/config.toml'),
        seals={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')})
    (OUT/'BEFORE.json').write_text(json.dumps(before,indent=2),encoding='utf8');print(OUT)
