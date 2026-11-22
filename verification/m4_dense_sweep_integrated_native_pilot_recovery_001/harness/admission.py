"""Admit only the two outstanding formal slots on derived, closed evidence."""

from pathlib import Path
from runpy import run_path

from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, NS, ORDER, PRODUCT,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, SLOTS, read, sha)


SCHEMA = 'm4-dense-sweep-integrated-native-pilot-recovery-001-v1'
PROMPT_SHA = '254f79b43eaf77a305a2372a77f26454a3aac75882591b845533ca6c805ce771'
DERIVED = EXTERNAL/'preflight/DERIVED_ADMISSION.json'
PREFLIGHT = NS/'qualification/RECOVERY_PREFLIGHT.json'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def registered_product():
    installed = read(PRODUCT_BINDING)
    current = {'commit':installed['preparation_git'],'source_sha256':installed['source_sha256'],
               'wheel_sha256':installed['wheel_sha256']}
    require(current == PRODUCT and len(installed['source_manifest']) == 143,'fixed_recovery_install_required')
    return current


def verify_derived(path=DERIVED):
    replay = run_path(str(NS/'qualification/recovery.py'))
    receipt = read(path)
    require(receipt['schema'] == SCHEMA+'-derived-qualification'
            and receipt['purpose'] == 'from-original-closed-evidence-only'
            and receipt['offline_started_ns'] <= receipt['offline_finished_ns']
            and receipt['new_Blender_starts'] == receipt['new_model_starts'] == 0,
            'current_offline_derived_gate_clock_or_scope_changed')
    actual = replay['audit']()
    require(actual['passed'] is True and replay['canonical'](actual) == replay['canonical'](receipt['evidence']),
            'derived_gate_does_not_match_original_closed_evidence')
    return sha(path)


def verify_freeze(path=None):
    expected = NS/'FROZEN.json'
    chosen = expected if path is None else Path(path)
    require(chosen.resolve() == expected.resolve(),'only_current_recovery_freeze_is_admissible')
    spec = read(chosen)
    prompt = NS/'inputs/PROMPT.txt'
    require(spec['schema'] == SCHEMA and spec['slots'] == list(ORDER) == ['N1','P1']
            and spec['qualification_slots'] == [] and spec['max_qualification_starts'] == 0
            and spec['product'] == registered_product() and Path(spec['asset_path']).resolve() == ASSET.resolve()
            and spec['asset_sha256'] == sha(ASSET) == ASSET_SHA256
            and spec['prompt_sha256'] == sha(prompt) == PROMPT_SHA
            and spec['passed_offline_preflight'] is True and spec['derived_admission_sha256'] == sha(DERIVED),
            'fixed_recovery_order_asset_or_derived_gate_changed')
    paths = set()
    for item in spec['direct_inputs']:
        source = Path(item['path']).resolve(strict=True)
        require(source not in paths and source.stat().st_size == item['bytes'] and sha(source) == item['sha256'],
                'frozen_recovery_input_changed/'+str(source))
        paths.add(source)
    needed = (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, ASSET, prompt, DERIVED, PREFLIGHT)
    require({item.resolve() for item in needed} <= paths
            and read(PREFLIGHT)['derived_admission_sha256'] == spec['derived_admission_sha256'],
            'incomplete_frozen_recovery_inputs')
    return sha(chosen)


def publication(label, freeze):
    require(label in SLOTS,'new_formal_slot_required')
    slot = EXTERNAL/'slots'/label
    path = slot/'SLOT_RESULT.json'
    result, receipt = read(path),read(slot/'SLOT_PUBLICATION.json')
    require(result['label'] == receipt['label'] == label and receipt['result_sha256'] == sha(path)
            and (result['group'],result['phase']) == SLOTS[label]
            and result['asset_sha256'] == ASSET_SHA256 and result['freeze_sha256'] == freeze
            and result['product_binding_sha256'] == sha(PRODUCT_BINDING)
            and result['product_source_sha256'] == PRODUCT['source_sha256'],
            'new_formal_owned_publication_binding_changed/'+label)
    return result,receipt


def safe_to_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    owner = result.get('owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    independent = result.get('independent_before_after') or {}
    consumer = result.get('consumer') or {}
    return (receipt.get('owned_budget_passed') is True and result['status'] == receipt['status'] == 'completed'
            and result['paid_API_calls'] == 0 and result['model_consumers'] == 1
            and closure.get('passed') is True and closure.get('status') == 'ready_closed'
            and closure.get('mcp_closure_required') is (result['group']=='P')
            and owner.get('confirmed') is True and not owner.get('errors') and not owner.get('transport_errors')
            and independent.get('passed') is True and consumer.get('safe_to_continue') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0)


def validate_admission(label, path):
    require(label in SLOTS,'new_formal_slot_required')
    token = verify_freeze(path)
    require(verify_derived() == read(path)['derived_admission_sha256'],'frozen_derived_gate_detached')
    prior = ORDER[:ORDER.index(label)]
    folder = EXTERNAL/'slots'
    actual = {item.name for item in folder.iterdir()} if folder.is_dir() else set()
    require(actual == set(prior) and all(safe_to_continue(*publication(name,token)) for name in prior),
            'new_formal_order_or_prior_safe_close_changed')
    return {'freeze_sha256':token}
