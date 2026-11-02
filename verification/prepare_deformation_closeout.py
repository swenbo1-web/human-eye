"""Freeze the user's five-step closeout before the new diagnostic is tested."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/fixes/20261102_m4_deformation_closeout'
if __name__=='__main__':
    OUT.mkdir(exist_ok=False);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    spec=dict(order=['B1 closeout and five legacy gaps','B2 read-only local metrics','independent finite comparison','fixed-candidate Codex consumption','then choose expansion'],
        legacy=['queued/registering cancellation','cancel versus approval submission boundary and committed readback','two filtered witnesses required',
            'discrete affected-triangle direction/degeneracy before every forward/recovery setter','full result row/id/input binding before scoring'],
        B1=['original deadline after analysis, report fsync/publish/encoding and before success; pending/expired report not current',
            'each negative exact expected reason','adjacent gradient weights, rest roll, noncommuting parent/world combinations'],
        B2=dict(input='complete validated skin-source-snapshot-v1, never the 16-vertex summary',
            metrics='two singular stretches of 3x2 surface map, engineering strains and unsigned area ratio; no volume/health inference',
            guards=dict(shape_quality_floor=2**-20,source_unit_roundoff=2**-24,source_subnormal_step=2**-149,
                coordinate_margin=8,resolution_margin=16,error_margin=32,max_stretch_error=.01,max_area_error=.02),
            unknown='original zero area, reference ill conditioning/resolution, current near degeneration, unweighted triangle or excessive error estimate',
            collapse='exact current zero area separated from original zero area; no damage claim',
            uncertainty='conservative numerical guard model, not certified physical error bounds',report_triangles=16),
        oracle='independent NumPy SVD/analytic affine/hinge facts and exact zero checks; no producer self-answer',
        evaluation='fixed finite fact questions and actual Codex consumption only; fair paid A/B not admitted by old cost gate',
        excluded=['new edit domains','IK/DQ/general modifiers','large rigs','animation','training'])
    (OUT/'PREREGISTERED.json').write_text(json.dumps(spec,indent=2),encoding='utf8')
    before=dict(commit='ff588b937b2b1b339079fdebe90b07b0ab33062d',config_sha256=sha(ROOT/'.codex/config.toml'),
        seals={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')})
    (OUT/'BEFORE.json').write_text(json.dumps(before,indent=2),encoding='utf8');print(OUT)
