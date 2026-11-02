"""Freeze this batch's checks and preserve actual Codex history without replay."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification/fixes/20261102_m3_operator_task'


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


if __name__=='__main__':
    OUT.mkdir(exist_ok=False)
    save(OUT/'PREREGISTERED.json',dict(schema='owned-reference-operator-task-checks-v1',
        scope='new owned original-triangle fixtures only; fixed intended reference; no shared GUI or save',
        authorization='explicit operator launch, never a fabricated MCP form response',
        task_window_ns=30_000_000_000,maximum_selected=8,maximum_displacement_m=.001,maximum_setters='2N including recovery',
        checks=['original launch window includes initialization, reads, admission and execution',
            'exact frozen indices/source/reference/config; no model authority fields',
            'one batch and one live capability; duplicate receives receipt; new id cannot renew',
            'exclusive task directory claim refuses restart, unfinished or completed',
            'cancel/expiry/config/source change denies admission; unknown never retried',
            'persistence failure before approval zero dispatch; after possible dispatch count stays unknown',
            'manual default still strict bool true/current form id; no destructive annotation weakening',
            'multi-vertex real RNA result, protected vertices, full mesh/frame readback, unchanged blend hash',
            'never-mode stdio task does not request elicitation; scripted client is not actual Codex UI proof'],
        performance='describe full IO only; no speed gate or model benefit claimed',formal_model_trials=0))
    history=OUT/'actual_codex_history';history.mkdir()
    source=ROOT/'.human-eye/m3-reference-handoff-20261102/journal'
    rows=[]
    for ordinal in range(3):
        path=source/('slot-%02d'%ordinal)/'RECORD.json';blob=path.read_bytes()
        (history/('SLOT_%02d.json'%ordinal)).write_bytes(blob)
        record=json.loads(blob);payload=record['payload']
        canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        assert hashlib.sha256(canonical).hexdigest()==record['sha256']
        rows.append(dict(slot=ordinal,event_id=payload['event_id'],result=payload['result'],file_sha256=hashlib.sha256(blob).hexdigest()))
    assert [r['result']['setter_attempts'] for r in rows]==[0,0,1]
    assert [r['result']['status'] for r in rows]==['refused_before_dispatch','refused_before_dispatch','completed']
    save(history/'SUMMARY.json',dict(rows=rows,raw_elicitation_responses_archived=False,
        exact_prior_refusal_payload_unknown=True,actual_success_from_persistent_worker_journal=True,
        prior_same_worker_readback='observed in preceding actual tool replies; not recreated by this script',
        current_reloaded_unsaved_fixture_is_not_prior_worker_readback=True))
    print(OUT)
