"""Freeze the prepared six-slot receipt without starting any consumer."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert not (BATCH/'STARTED.json').exists() and not (BATCH/'FREEZE.json').exists()
    plan = read(BATCH/'PLAN.json')
    driver = load('_surface_scan_prepare_driver',HERE/'driver.py')
    transport = load('_surface_scan_prepare_transport',HERE/'consumer_transport.py')
    driver.verify_frozen_inputs(plan)
    prepared = driver.preflight_inputs()
    save(HERE/'PREPARED_INPUT.json',prepared)
    snapshot = read(BATCH/'scoring/ACTUAL_SNAPSHOT.json')
    owner_shape = dict(unit_scale_m=snapshot['unit_scale_m'],objects=[
        {key:row[key] for key in ('name','vertices_local','matrix_world','faces')}
        for row in snapshot['objects']])
    driver.snapshot_binding(owner_shape,snapshot)
    argv_by_group = {}
    for group in ('N','P'):
        folder = BATCH/'preflight/argv_inputs'/group
        folder.mkdir(parents=True,exist_ok=False)
        cell = folder/'cell.json'
        save(cell,dict(group=group,endpoint=str(folder/'ENDPOINT.json'),audit_dir=str(folder/'owner')))
        argv = transport.argv_for(plan['installation_ready']['dependency_python'],cell,
            folder/'empty_work',folder/'final.txt',group)
        assert '--image' not in argv
        argv_by_group[group] = argv
    save(BATCH/'preflight/CLI_ARGV.json',dict(scope='Pure argv generation using synthetic endpoints.',
        argv_by_group=argv_by_group,processes_started=0))
    save(BATCH/'preflight/CONSUMER_CONFIGURATION.json',dict(settings=transport.settings(),
        tools_by_group={name:sorted(value) for name,value in transport.TOOLS_BY_GROUP.items()},
        same_common_native_declaration=True,ordinary_observe_full_declaration=True,
        initial_images=0,new_images=0,model_consumers=0,actual_snapshot_normalization_verified=True))
    for relative in ('runtime/PREPARED_INPUT.json','runtime/freeze_plan.py',
        'preflight/CLI_ARGV.json','preflight/CONSUMER_CONFIGURATION.json',
        'preflight/argv_inputs/N/cell.json','preflight/argv_inputs/P/cell.json'):
        plan['dispatch_input_sha256'][relative] = sha(BATCH/relative)
    with (BATCH/'PLAN.json').open('w',encoding='utf8',newline='\n') as stream:
        json.dump(plan,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    digest = sha(BATCH/'PLAN.json')
    receipt = dict(task=plan['cycle_id'],authorized=True,max_consumers=6,plan_sha256=digest,
        authorization_source='Administrator direct preparation-plus-six delegation and ROOT_PLAN.md')
    driver.go_contract(receipt,plan,digest)
    driver.verify_frozen_inputs(plan)
    save(BATCH/'FREEZE.json',dict(cycle_id=plan['cycle_id'],plan_sha256=digest,
        frozen_utc=datetime.now(timezone.utc).isoformat(),authorized_consumers=6,
        quality_before_cost=True,initial_images=0,new_images=0,
        product_source_count=138,product_source_sha256=plan['candidate_source_sha256']))
    save(BATCH/'GO.json',receipt)
    bootstrap = read(BATCH/'preflight/BOOTSTRAP_RECEIPT.json')
    ready = read(BATCH/'installations/P_READY.json')
    save(BATCH/'PREPARATION_COST.json',dict(
        bootstrap_recorded_utc=bootstrap['recorded_utc'],bootstrap_elapsed_ns=bootstrap['elapsed_ns'],
        freeze_utc=read(BATCH/'FREEZE.json')['frozen_utc'],
        scope='Local bootstrap has a measured span; preceding coordinator work and total preparation wall are unmeasured.',
        reused_install_elapsed_ns=ready['elapsed_ns'],installation_rebuilds=0,
        model_consumers=0,Blender_sessions=0,live_product_processes=0,smoke_sessions=0,
        coordinator_model_cost=None))
    print(json.dumps(dict(prepared_slots=6,plan_sha256=digest,model_consumers=0,
        Blender_sessions=0,product_pretests=0)))


if __name__ == '__main__':
    main()
