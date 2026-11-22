"""Admit only the single frozen two-arm qualification and consumer sequence."""

from pathlib import Path

from common import ASSET, EXTERNAL, NS, ORDER, SLOTS, binding_for, product_for, read, sha


SCHEMA = 'm1-region-task-witness-image-path-consumption-001-v1'
QUALIFICATION = ('QA','QB')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def registered_product(label):
    binding=read(binding_for(label))
    product={'commit':binding['preparation_git'],'source_sha256':binding['source_sha256'],
             'wheel_sha256':binding['wheel_sha256']}
    require(product==product_for(label) and len(binding['source_manifest'])==143,
            'fixed_witness_path_product_install_required/'+label)
    return product


def verify_freeze(path=None):
    expected=NS/'FROZEN.json'
    actual=expected if path is None else Path(path)
    require(actual.resolve()==expected.resolve(),'fixed_consumption_freeze_required')
    spec=read(actual)
    require(spec['schema']==SCHEMA and spec['slots']==list(ORDER) and sha(ASSET)==spec['asset_sha256']==ASSET_SHA
            and Path(spec['asset_path']).resolve()==ASSET.resolve(strict=True)
            and spec['products']=={label:registered_product(label) for label in ORDER}
            and spec['passed_offline_preflight'] is True,'witness_consumption_freeze_changed')
    sources=set()
    for row in spec['direct_inputs']:
        source=Path(row['path']).resolve(strict=True)
        require(source not in sources and source.stat().st_size==row['bytes'] and sha(source)==row['sha256'],
                'frozen_witness_input_changed/'+str(source))
        sources.add(source)
    required=(ASSET,binding_for('A1'),binding_for('B1'),NS/'inputs/PROMPT.txt',NS/'inputs/TOOLS_SCHEMA.json',
              NS/'inputs/PRODUCT_SCHEMA.json',NS/'fixture/TRUTH.json',NS/'harness/HOST_PREFLIGHT.json',
              NS/'harness/RUNTIME_PREFLIGHT.json',NS/'checks/SCORER_PREFLIGHT.json',NS/'checks/evidence.py')
    require({path.resolve() for path in required}<=sources,'incomplete_witness_path_consumption_inputs')
    return sha(actual)


def publication(label,freeze):
    require(label in SLOTS,'registered_slot_required')
    slot=EXTERNAL/'slots'/label
    source=slot/'SLOT_RESULT.json'
    raw,receipt=read(source),read(slot/'SLOT_PUBLICATION.json')
    require(raw['label']==receipt['label']==label and receipt['result_sha256']==sha(source)
            and (raw['group'],raw['phase'])==SLOTS[label] and raw['asset_sha256']==ASSET_SHA and raw['freeze_sha256']==freeze
            and raw['product_binding_sha256']==sha(binding_for(label))
            and raw['product_source_sha256']==registered_product(label)['source_sha256'],
            'original_slot_publication_binding_changed/'+label)
    return raw,receipt


def safe_to_continue(result,receipt):
    close=result.get('closure_verification') or {}
    owner=result.get('owner_close') or {}
    counts=(result.get('budget') or {}).get('counts') or {}
    source=result.get('independent_before_after') or {}
    consumer=result.get('consumer') or {}
    return (receipt.get('owned_budget_passed') is True and result['status']==receipt['status']=='completed'
            and result['paid_API_calls']==0 and close.get('passed') is True and close.get('status')=='ready_closed'
            and close.get('mcp_closure_required') is True and owner.get('confirmed') is True
            and not owner.get('errors') and not owner.get('transport_errors') and source.get('passed') is True
            and counts.get('Blender_spawned_unknown')==counts.get('pending_raster_reservations')==0
            and (not result.get('actual_model_admitted') or consumer.get('safe_to_continue') is True))


def qualified(label,freeze):
    require(label in QUALIFICATION,'registered_qualification_required')
    result,receipt=publication(label,freeze)
    folder=EXTERNAL/'preflight'
    proof=folder/f'{label}_CLOSED_PROOF.json'
    gate=read(folder/f'{label}_CLOSED_GATE.json')
    require(safe_to_continue(result,receipt) and result['model_consumers']==0 and gate['passed'] is True
            and gate['freeze_sha256']==freeze and gate['result_sha256']==receipt['result_sha256']
            and gate['proof_sha256']==sha(proof) and read(proof)['passed'] is True
            and gate['verified_ns']<result['owned_deadline_ns'],'two_real_closed_qualification_arms_required/'+label)
    paths=gate['original_images']
    require(len(paths)==len({row['ref'] for row in paths})==2,'two_distinct_current_local_paths_required/'+label)
    slot=(EXTERNAL/'slots'/label).resolve()
    for row in paths:
        path=Path(row['path']).resolve(strict=True)
        require(path.is_relative_to(slot) and sha(path)==row['sha256'],'closed_original_image_changed/'+label)
    return gate


def validate_admission(label,path):
    require(label in SLOTS,'registered_slot_required')
    freeze=verify_freeze(path)
    prefix=ORDER[:ORDER.index(label)]
    slots=EXTERNAL/'slots'
    found={path.name for path in slots.iterdir()} if slots.is_dir() else set()
    require(found==set(prefix) and all(safe_to_continue(*publication(name,freeze)) for name in prefix),
            'actual_paired_slot_order_or_prior_closure_changed')
    # QB requires the same just-closed QA gate as both consumer slots.
    for previous in QUALIFICATION:
        if previous in prefix:
            qualified(previous,freeze)
    return {'freeze_sha256':freeze}
