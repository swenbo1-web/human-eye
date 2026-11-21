"""Exercise recovery publication, ownership closure, and admission using retained receipts."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from runpy import run_path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
OLD = V/'perf050_source_scope_rank_transfer_001'
DENSE = V/'perf050_dense_pair_transfer_001'
FIXTURE = V/'m4_m5_source_region_001'
OLD_INDEX = '62e84fdede963ebdb001d1af8e1b8836f5896b5794232e3943c495efa82f0b96'
DENSE_INDEX = 'c441f0e473e43d83b15fd0b4b96183d556a9b165ed1f29e7c24066002e169cb9'
FIXTURE_INDEX = 'af86c962b5c845b5654a2af375ef7cef3b3167dd3449e9abdb581da0e25058ab'
OLD_FREEZE = '573d66fd20866f82d27f89fed648c8713d8f2c1013b35d31144b9a7476656323'
LABELS = ('QN', 'QP', 'N1', 'P1')


def require(predicate, detail):
    if not predicate:
        raise ValueError(detail)


def sha(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'path':str(path.resolve()), 'bytes':len(raw), 'sha256':sha(raw)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8', newline='\n')


def guarded_raw(path, expected):
    receipt = pin(path)
    require(receipt['sha256'] == expected, 'sealed_source_hash_changed/' + str(path))
    return path.read_bytes(), receipt


def fixtures():
    cases = {}
    pins = []
    for name, source, digest, label in (('N', OLD, OLD_INDEX, 'QN'), ('P', DENSE, DENSE_INDEX, 'P1')):
        raw_index, index_proof = guarded_raw(source/'RUNTIME_INDEX.json', digest)
        index = json.loads(raw_index)
        zip_path = Path(index['archive']['path'])
        _, zip_proof = guarded_raw(zip_path, index['archive']['sha256'])
        require(zip_proof['bytes'] == index['archive']['bytes'], 'sealed_runtime_archive_length_changed')
        pins.extend((index_proof, zip_proof))
        rows = {row['path']:row for row in index['files']}
        with ZipFile(zip_path) as bundle:
            group = {}
            for file in ('SLOT_RESULT.json','SLOT_PUBLICATION.json','RUNTIME_CLOSE.json','NATIVE_RUNTIME_PROOF.json'):
                key = f'slots/{label}/{file}'
                wire = bundle.read(key)
                require(len(wire) == rows[key]['bytes'] and sha(wire) == rows[key]['sha256'], 'archive_member_changed/' + key)
                group[file] = wire
            cases[name] = group

    image_index, image_index_pin = guarded_raw(FIXTURE/'RUNTIME_ARCHIVE.json', FIXTURE_INDEX)
    pins.append(image_index_pin)
    image_rows = {row['relative']:row for row in json.loads(image_index)['files']}
    images = {}
    for kind, key in (('common','sessions/state/product_calls/call_001/delivered/image_01.png'),
                      ('product','sessions/state/product_calls/call_003/delivered/image_01.png')):
        record = image_rows[key]
        image, image_pin = guarded_raw(FIXTURE/record['copy'], record['sha256'])
        require(len(image) == record['bytes'], 'archived_PNG_length_changed/' + kind)
        pins.append(image_pin)
        images[kind] = image
    require(images['common'] != images['product'], 'distinct_reopen_fixture_images_required')
    return cases, images, pins


@contextmanager
def detached(experiment, local):
    namespace, external = local/'frozen_inputs', local/'virtual_runtime'
    admission = experiment['admission']
    with patch.object(admission, 'NS', namespace), patch.object(admission, 'EXTERNAL', external):
        yield namespace, external


def freeze_fixture(admission, namespace):
    replay_mark = {'passed':True, 'provenance':'local publication/admission control only'}
    placeholders = ('harness/HOST_PREFLIGHT.json', 'consumer/PREFLIGHT.json', 'qualification/REPLAY_PREFLIGHT.json')
    for item in placeholders:
        write(namespace/item, replay_mark)
    truth = namespace/'checks/TRUTH.json'
    truth.parent.mkdir(parents=True, exist_ok=True)
    truth.write_bytes((OLD/'checks/TRUTH.json').read_bytes())
    paths = [admission.PRODUCT_BINDING,admission.PRODUCT_SCHEMA,admission.CATALOGUE,truth]
    paths.extend(namespace/item for item in placeholders)
    path = namespace/'FROZEN.json'
    value = {'schema':admission.SCHEMA, 'slots':list(admission.ORDER), 'product':admission.registered_product(),
             'asset_sha256':admission.ASSET_SHA256, 'passed_offline_preflight':True,
             'preflights':{item:pin(namespace/item)['sha256'] for item in (*placeholders,'checks/TRUTH.json')},
             'direct_inputs':[pin(item) for item in paths], 'local_replay_only':True}
    write(path, value)
    return path, value


def rejected(action, expected=None):
    try:
        action()
    except (ValueError, FileNotFoundError) as exc:
        failure = str(exc)
        require(expected is None or expected in failure, 'different_rejection/' + failure)
        return {'type':type(exc).__name__, 'message':failure}
    raise ValueError('malformed_receipt_or_wrong_sequence_was_accepted')


def raw_close(closure, cases):
    evidence = {}
    for group, originals in cases.items():
        payload = json.loads(originals['RUNTIME_CLOSE.json'])
        proof = json.loads(originals['NATIVE_RUNTIME_PROOF.json'])
        check = closure.ready_closure(payload,group,proof,require_mcp=group == 'P')
        require(check == json.loads(originals['SLOT_RESULT.json'])['closure_verification'], 'real_closure_replay_diverged/' + group)
        broken = deepcopy(payload)
        removed = ('Blender_exit','confirmed') if group == 'N' else ('public_MCP_close','confirmed')
        broken[removed[0]].pop(removed[1])
        expected = 'generic_owned_ready_closure_or_original_asset_identity_failed' if group == 'N' else 'installed_public_MCP_close_failed'
        evidence[group] = {'input_hash':sha(originals['RUNTIME_CLOSE.json']), 'proof_hash':sha(originals['NATIVE_RUNTIME_PROOF.json']),
                           'actual_closure':check, 'missing_field':list(removed),
                           'missing_field_rejected':rejected(lambda: closure.ready_closure(broken,group,proof,require_mcp=group == 'P'),expected)}
    clean = closure.startup_closure(spawn=None,failure=None,launch_cleanup=None,settlement=None,
                                    asset_matches=True,copy_matches=None,ready=None,startup_entered=False)
    incomplete = closure.startup_closure(spawn=None,failure=None,launch_cleanup=None,settlement=None,
                                         asset_matches=True,copy_matches=None,ready=None,startup_entered=True)
    require(clean['passed'] is True and clean['status'] == 'startup_failed_clean'
            and incomplete['passed'] is None, 'startup_close_must_not_treat_missing_evidence_as_success')
    evidence.update(clean_startup_fixture=clean, unknown_startup_fixture=incomplete)
    return evidence


def old_failure(experiment, local, originals):
    admission = experiment['admission']
    freeze_sha = pin(OLD/'FROZEN.json')['sha256']
    require(freeze_sha == OLD_FREEZE, 'original_freeze_changed')
    with detached(experiment,local) as (_,external):
        slot = external/'slots/QN'
        slot.mkdir(parents=True)
        for file in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'):
            (slot/file).write_bytes(originals[file])
        result, receipt = admission.publication('QN',freeze_sha)
        require(result['status'] == receipt['status'] == 'failed' and result['model_consumers'] == 0
                and result['diagnostic_calls'] == [] and 'qualification' not in result and 'diagnostic_close' not in result
                and admission.can_continue(result,receipt) is True, 'archived_zero_call_ready_closed_failure_did_not_replay')
        bad_closes = {'absent':None,'empty':{},'malformed_list':[True], 'passed_without_status':{'passed':True},
                      'ready_without_mcp_scope':{'status':'ready_closed','passed':True}}
        observed = {}
        for label, bad in bad_closes.items():
            mutated = {**result,'closure_verification':bad}
            observed[label] = admission.can_continue(mutated,receipt)
            require(observed[label] is False,'malformed_closure_did_not_fail_closed/' + label)
        wrong_freeze = rejected(lambda: admission.publication('QN','f'*64),'original_slot_receipt_identity_mismatch')
        return {'exact_result':pin(slot/'SLOT_RESULT.json'),'exact_publication':pin(slot/'SLOT_PUBLICATION.json'),
                'original_freeze':freeze_sha,'close_safe':True,'qualification_passed':False,
                'malformed_closures_accepted':observed,'original_wrong_freeze_rejection':wrong_freeze}


def save_slot(admission, external, label, token, record, pictures, *, fail):
    group, phase = admission.SLOTS[label]
    originals = {f:json.loads(b) for f,b in record.items()}
    result = {**originals['SLOT_RESULT.json'], 'freeze_sha256':token, 'label':label, 'slot':label, 'group':group,
              'phase':phase, 'asset_sha256':admission.ASSET_SHA256,
              'product_binding_sha256':pin(admission.PRODUCT_BINDING)['sha256'],
              'model_consumers':0, 'actual_model_admitted':False, 'diagnostic_calls':[], 'local_replay_only':True}
    receipt = {**originals['SLOT_PUBLICATION.json'], 'label':label, 'slot':label, 'local_replay_only':True}
    folder = external/'slots'/label
    folder.mkdir(parents=True)
    if not fail:
        result.update(status='completed',errors=[])
        receipt.update(status='completed')
        if phase == 'qualification':
            proof = {'passed':True,'qualification_only':True,'local_replay_only':True}
            for kind in ('common','product') if group == 'P' else ('common',):
                image_path = (folder/f'{kind}.png').resolve()
                image_path.write_bytes(pictures[kind])
                proof[f'{kind}_image'] = pin(image_path)
            result['qualification'] = proof
            write(folder/'QUALIFICATION.json',proof)
    write(folder/'SLOT_RESULT.json',result)
    receipt['result_sha256'] = pin(folder/'SLOT_RESULT.json')['sha256']
    write(folder/'SLOT_PUBLICATION.json',receipt)
    return result, receipt


def run_sequence(experiment, roots, originals, pictures, fail):
    admission = experiment['admission']
    sequence = experiment['sequence']
    with detached(experiment,roots) as (namespace,external):
        freeze_path, descriptor = freeze_fixture(admission,namespace)
        token = admission.verify_freeze(freeze_path)
        require(token == pin(freeze_path)['sha256'], 'actual_freeze_verifier_did_not_bind_its_exact_bytes')
        before_start = rejected(lambda: admission.validate_admission('QP',freeze_path),'unexpected_pilot_slot_order')
        namespaces = []
        misbound_image_rejected = None

        def prepare_subprocess(command, *, cwd):
            nonlocal misbound_image_rejected
            label = command[-1]
            require(Path(command[-2]) == NS/'harness/run_slot.py' and Path(cwd) == V.parent,
                    'actual_sequence_changed_its_slot_entry_or_workdir')
            if label == 'N1':
                qp_path = external/'preflight/QP_CLOSED_IMAGES.json'
                original_bytes = qp_path.read_bytes()
                wrong = json.loads(original_bytes)
                wrong['reopened']['product'] = wrong['reopened']['common']
                write(qp_path,wrong)
                try:
                    misbound_image_rejected = rejected(lambda: admission.validate_admission('N1',freeze_path),
                                                       'current_source_scope_qualification_required/QP')
                finally:
                    qp_path.write_bytes(original_bytes)
            gate = admission.validate_admission(label,freeze_path)
            require(gate['freeze_sha256'] == token, 'actual_prior_gate_token_diverged')
            namespaces.append(label)
            save_slot(admission,external,label,token,originals[admission.SLOTS[label][0]],pictures,fail=fail)
            return SimpleNamespace(returncode=int(fail))

        original_path = sys.path[:]
        live_process_boundary = SimpleNamespace(run=prepare_subprocess)
        try:
            # Scope changes are just paths and the owned subprocess boundary.
            with patch.dict(sequence.__globals__, RUN=external, subprocess=live_process_boundary):
                code = sequence()
        finally:
            sys.path[:] = original_path
        expect = ['QN'] if fail else list(LABELS)
        require(code == int(fail) and namespaces == expect, 'actual_sequence_advanced_the_wrong_slots')
        path = external/'preflight/FORMAL_SEQUENCE.jsonl'
        events = [json.loads(line) for line in path.read_bytes().splitlines()]
        published = [row for row in events if row['event'] == 'publication']
        require([row['label'] for row in published] == expect
                and all(row['safe_to_continue'] is (not fail) and row['model_consumers'] == 0 for row in published),
                'actual_sequence_publication_or_halt_state_diverged')
        reopens = {p.name:read(p) for p in (external/'preflight').glob('*_CLOSED_IMAGES.json')}
        if fail:
            require(not reopens,'replay_failed_qualification_made_reopen_grant')
        else:
            require(set(reopens) == {'QN_CLOSED_IMAGES.json','QP_CLOSED_IMAGES.json'}
                    and len(reopens['QN_CLOSED_IMAGES.json']['reopened']) == 1
                    and len(reopens['QP_CLOSED_IMAGES.json']['reopened']) == 2
                    and misbound_image_rejected is not None,
                    'actual_sequence_did_not_require_all_closed_pngs')
        return {'exit_code':code,'direct_input_count':len(descriptor['direct_inputs']),'owned_processes_started':0,
                'verified_freeze':token,'blocked_out_of_order':before_start,'virtual_entry_order':expect,
                'publication_events':published,'closed_reopens':reopens,'misbound_product_reopen_rejected':misbound_image_rejected}


def failed_formal_gate(experiment, roots, originals, pictures):
    admission = experiment['admission']
    with detached(experiment, roots) as (namespace,external):
        frozen, _ = freeze_fixture(admission,namespace)
        token = admission.verify_freeze()
        save_slot(admission,external,'QN',token,originals['N'],pictures,fail=True)
        save_slot(admission,external,'QP',token,originals['P'],pictures,fail=False)
        no_qualified_QN = rejected(lambda: admission.validate_admission('N1',frozen),'current_source_scope_qualification_required/QN')
    with detached(experiment, roots/'missing_closed_images') as (namespace,external):
        frozen, _ = freeze_fixture(admission,namespace)
        token = admission.verify_freeze()
        save_slot(admission,external,'QN',token,originals['N'],pictures,fail=False)
        save_slot(admission,external,'QP',token,originals['P'],pictures,fail=False)
        no_images = rejected(lambda: admission.validate_admission('N1',frozen))
        return {'failed_qualification_cannot_gate_formal':no_qualified_QN,'missing_closed_images_cannot_gate_formal':no_images}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_fixed_interpreter_with_I_and_B')
    experiment = run_path(str(NS/'experiment.py'))
    closure_path = NS/'harness/closure.py'
    spec = importlib.util.spec_from_file_location('_scope_admission_replay_closure',closure_path)
    closure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closure)
    originals, pictures, pins = fixtures()
    with TemporaryDirectory(prefix='perf050_scope_admission_replay_') as local:
        t = Path(local).resolve()
        result = {'passed':True,'provenance':'offline publication and admission replay only',
                  'formal_or_qualification_processes_started':0,'Blender_starts':0,'model_starts':0,
                  'pins':[*pins,pin(Path(__file__)),pin(closure_path),pin(NS/'harness/admission.py'),pin(NS/'experiment.py')],
                  'real_owned_close_replays':raw_close(closure,originals),
                  'exact_original_failure':old_failure(experiment,t/'original',originals['N']),
                  'original_failure_sequence':run_sequence(experiment,t/'stopped',originals,pictures,fail=True),
                  'positive_virtual_sequence':run_sequence(experiment,t/'accepted',originals,pictures,fail=False),
                  'formal_negative_controls':failed_formal_gate(experiment,t/'formal_negative',originals,pictures)}
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print('Actual close/publication/admission replay passed',pin(args.output)['sha256'],flush=True)


if __name__ == '__main__':
    main()
