"""Freeze operator-clearance checks before changing runtime code."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification/fixes/20261102_m3_clearance_operator_task'

if __name__=='__main__':
    OUT.mkdir(exist_ok=False)
    value=dict(scope='new owned static clearance copies only; no shared GUI, user assets or file save',
        authorization='explicit operator local launch, distinct from reference-vertex authority or human MCP form',
        original_window='at most 30s from operator intake including initialization; not renewed at registration',
        maximum_steps=8,maximum_segments=3,maximum_step_m=.001,maximum_total_m=.008,
        checks=['reuse TrustedTaskEntry and OwnedGoalScheduler without another solver or ledger',
            'pin runtime, executable, original scene and connector config; exact typed task/spec/source',
            'one exclusive durable task root; same root cannot restart even after incomplete publication',
            'different task domain, JSON, changed source/spec/limits/config, expired and revoked task cannot approve',
            'independent full-scene native readback; only focal world Z may change; zero save',
            'physical count and unknown/failed completion persistence retain original semantics',
            'real interruption before execution and after first actual setter cannot reopen budget',
            'second task root cannot bypass unknown original connector ledger',
            'manual MCP and reference task paths unchanged; tests do not claim human UI or model benefit'],
        formal_model_trials=0)
    with (OUT/'PREREGISTERED.json').open('x',encoding='utf8') as f:json.dump(value,f,indent=2)
    seals={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'verification/fixes').glob('*/SEALED_MANIFEST.json')}
    with (OUT/'BEFORE.json').open('x',encoding='utf8') as f:json.dump(dict(seals=seals,
        engine_config_sha256=hashlib.sha256((ROOT/'.codex/config.toml').read_bytes()).hexdigest()),f,indent=2)
    (OUT/'CONFIG_BEFORE.toml').write_bytes((ROOT/'.codex/config.toml').read_bytes())
    print(str(OUT))
