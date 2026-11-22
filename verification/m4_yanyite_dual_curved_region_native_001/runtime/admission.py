"""Require frozen inputs, actual qualification receipts, and one ordered pair."""

from pathlib import Path

from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, NS, ORDER, PLAN, PRODUCT,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, QUALIFICATION, SLOTS, read, sha, asset_identity)


_source = NS.parent/'m4_dense_sweep_integrated_native_pilot_001/harness/admission.py'
_scope = {'__file__':str(_source),'__name__':'_yanyite_original_admission'}
exec(compile(_source.read_bytes(),str(_source),'exec'),_scope)
require, registered_product, publication, safe_to_continue = (
    _scope[name] for name in ('require','registered_product','publication','safe_to_continue')
)


def verify_freeze(path):
    expected = NS/'FROZEN.json'
    require(Path(path).resolve()==expected.resolve(),'only_this_batch_freeze_allowed')
    frozen = read(path)
    prompt = NS/'inputs/PROMPT.txt'
    require(frozen['plan_reference']==PLAN and frozen['plan']==PLAN.split(':',1)[0]
            and frozen['slots']==list(ORDER) and frozen['product']==registered_product()
            and frozen['passed_offline_preflight'] is True and Path(frozen['asset_path']).resolve()==asset_identity()[0]
            and frozen['asset_sha256']==ASSET_SHA256 and frozen['prompt_sha256']==sha(prompt),
            'frozen_Yanyite_product_order_source_or_prompt_changed')
    pins = {}
    for row in frozen['direct_inputs']:
        source = Path(row['path']).resolve(strict=True)
        require(source not in pins and source.stat().st_size==row['bytes'] and sha(source)==row['sha256'],
                'frozen_live_source_changed/'+str(source))
        pins[source] = row
    required = (PRODUCT_BINDING,PRODUCT_SCHEMA,CATALOGUE,ASSET,prompt,
                EXTERNAL/'preflight/RUNTIME_PREFLIGHT.json')
    require({p.resolve() for p in required}<=pins.keys(),'runtime_input_missing_from_freeze')
    return sha(path)


def qualified(freeze):
    gate = read(EXTERNAL/'QUALIFICATION_GATE.json')
    require(gate['passed'] is True and gate['freeze_sha256']==freeze
            and set(gate['arms'])==set(QUALIFICATION),'two_independent_closed_qualifications_required')
    for label,arm in gate['arms'].items():
        slot = EXTERNAL/'slots'/label
        result, receipt = publication(label,freeze)
        score = arm['score']
        path = Path(score['path']).resolve(strict=True)
        require(safe_to_continue(result,receipt) and result['model_consumers']==0
                and arm['result_sha256']==receipt['result_sha256']
                and arm['publication_sha256']==sha(slot/'SLOT_PUBLICATION.json')
                and any(path.is_relative_to(folder.resolve()) for folder in (EXTERNAL/'score',slot))
                and path.stat().st_size==score['bytes'] and sha(path)==score['sha256'] and read(path)['passed'] is True,
                'independent_qualification_not_bound_to_actual_slot/'+label)
    return gate


def validate_admission(label, path):
    require(label in SLOTS,'registered_Yanyite_slot_required')
    freeze = verify_freeze(path)
    prior = ORDER[:ORDER.index(label)]
    slots = EXTERNAL/'slots'
    require((set(p.name for p in slots.iterdir()) if slots.is_dir() else set())==set(prior),'wrong_slot_order')
    for p in prior:
        previous, receipt = publication(p,freeze)
        if label=='QP' and p=='QN' and previous['status']=='failed':
            closure = previous.get('closure_verification') or {}
            require(closure.get('passed') is True and receipt['status']=='failed'
                    and previous['model_consumers']==0,'native_qualification_failure_did_not_confirm_cleanup')
        else:
            require(safe_to_continue(previous,receipt),'unconfirmed_predecessor/'+p)
    result = {'freeze_sha256':freeze}
    if SLOTS[label][1]=='formal':
        qualified(freeze)
        result['qualification_gate_sha256'] = sha(EXTERNAL/'QUALIFICATION_GATE.json')
    return result
