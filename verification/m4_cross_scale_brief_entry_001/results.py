"""Seal one original slot and publish independently reviewable public evidence."""

import argparse
import base64
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import OLD, validate_admission
from common import EXTERNAL, ROOT, load, read, save, sha


BASE = '9f743878d3a868575c5be43f00a9ba4e011b5161'
SLOT = EXTERNAL / 'slots/P1'
PREVIOUS_SLOT = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1')
TASK = 'M4-CROSS-SCALE-BRIEF-ENTRY-001'
TOOL = 'human_eye_scene_observe'


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    return {'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def export(path, name):
    return write_bytes(NS / name, path.read_bytes())


def publication():
    seal = validate_admission('P1', NS / 'FROZEN.json')
    if list((EXTERNAL / 'slots').iterdir()) != [SLOT]:
        raise ValueError('registered_single_slot_required')
    result = SLOT / 'SLOT_RESULT.json'
    record = read(result)
    receipt = read(SLOT / 'SLOT_PUBLICATION.json')
    if (receipt['result_sha256'] != sha(result) or receipt['label'] != 'P1' or record['label'] != 'P1'
            or record['model_consumers'] not in (0, 1) or any(record[k] != value for k, value in seal.items())):
        raise ValueError('one_original_result_bound_to_admission_required')
    return record, receipt


def answers():
    row, receipt = publication()
    original = SLOT / 'consumer/PUBLIC_FINAL.txt'
    saved = {'path': None, 'bytes': None, 'sha256': None}
    if row.get('answer') is not None:
        if sha(original) != row['answer']['sha256'] or original.stat().st_size != row['answer']['bytes']:
            raise ValueError('original_public_answer_bytes_changed')
        saved = export(original, 'answers/P1.txt')
        saved['path'] = str(NS / saved['path'])
    save(NS / 'ANSWERS_SEALED.json', {'answers': [
        {**saved, 'slot': 'P1', 'status': receipt['status'], 'published_ns': receipt['published_ns'],
         'original_path': str(original) if saved['path'] else None,
         'slot_result_sha256': receipt['result_sha256']}],
        'sealed_ns': time.perf_counter_ns(), 'replacement_consumers': 0})


def configuration():
    current = SLOT / 'consumer/ACTUAL_CONFIGURATION.json'
    if not current.is_file():
        return None
    before_path = PREVIOUS_SLOT / 'consumer/ACTUAL_CONFIGURATION.json'
    before, after = read(before_path), read(current)
    keys = ('requested_model', 'requested_effort', 'requested_service_tier')
    argv = 'requested_cli_overrides_and_argv'
    substitutions = ((str(PREVIOUS_SLOT.resolve()), str(SLOT.resolve())), (str(OLD), str(NS)))
    expected = list(before[argv])
    for prior, new in substitutions:
        expected = [part.replace(prior, new).replace(prior.replace('\\', '\\\\'), new.replace('\\', '\\\\'))
                    for part in expected]
    return {'exact_requested_settings_after_isolated_path_substitution':
                expected == after[argv] and all(before[key] == after[key] for key in keys),
            'historic_configuration_sha256': sha(before_path),
            'actual_configuration_sha256': sha(current), 'requested': {key: after[key] for key in keys},
            'historical_local_fallback': before['fallback_state'], 'actual_local_fallback': after['fallback_state'],
            'provider_identity_measured': False, 'cash_fees': None}


def first_packet():
    folder = SLOT / 'owner'
    first_folders = [p for p in sorted(folder.glob('tool_*')) if (p / 'REQUEST.json').is_file()]
    first = None
    if first_folders:
        path = first_folders[0] / 'REQUEST.json'
        first = {'attempt': int(path.parent.name.rsplit('_', 1)[-1]),
                 'tool': read(path)['params']['name'], 'request': export(path, 'first/FIRST_BUSINESS_REQUEST.json')}
    first_product = None
    for entry in first_folders:
        req, rx = entry / 'PRODUCT_REQUEST.json', entry / 'PRODUCT_RESPONSE.json'
        if not req.is_file():
            continue
        attempt = int(entry.name.rsplit('_', 1)[-1])
        request = read(req)
        owner_request = read(entry / 'REQUEST.json')
        args = request['params']['arguments']
        if (owner_request['params']['name'] != TOOL or request['params']['name'] != TOOL
                or args != owner_request['params']['arguments']):
            raise ValueError('first_actual_product_argument_transparency_failed')
        first_product = {'attempt': attempt, 'request': export(req, 'first/PRODUCT_REQUEST.json'),
                         'requested_detail': args.get('response_detail'),
                         'matches_brief_template': args == read(NS / 'inputs/REQUEST.json'),
                         'response': None, 'original_PNGs': [], 'text_UTF8_bytes': None,
                         'exact_CLI_delivery': False}
        if rx.is_file():
            response = read(rx)
            if response['id'] != request['id']:
                raise ValueError('first_product_request_response_id_mismatch')
            first_product['response'] = export(rx, 'first/PRODUCT_RESPONSE.json')
            content = response.get('result', {}).get('content', [])
            first_product['text_UTF8_bytes'] = sum(len(x['text'].encode()) for x in content if x['type'] == 'text')
            first_product['product_success'] = bool(content) and response['result'].get('isError') is False
            for idx, item in enumerate(content, start=1):
                if item['type'] == 'image':
                    png = base64.b64decode(item['data'], validate=True)
                    if item['mimeType'] != 'image/png' or not png.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise ValueError('first_product_image_must_be_original_png')
                    first_product['original_PNGs'].append(
                        {'content_index_1_based': idx, **write_bytes(NS / f'first/content_{idx:02d}.png', png)})
            public = entry / 'RESPONSE.json'
            binding = SLOT / 'consumer/BUSINESS_SOURCE_BINDING.json'
            if public.is_file() and binding.is_file():
                matched = [contract for contract in read(binding)['result_contracts']
                           if contract['attempt'] == attempt]
                if len(matched) == 1:
                    contract = matched[0]
                    first_product['exact_CLI_delivery'] = bool(
                        contract['matched'] and contract['tool'] == TOOL
                        and read(public).get('result') == response.get('result')
                        and contract['CLI_text_UTF8_bytes'] == first_product['text_UTF8_bytes']
                        and contract['CLI_images'] == len(first_product['original_PNGs']))
                    first_product['delivery'] = contract
        break
    treatment = bool(first_product and first_product['attempt'] == 1
                     and first_product['requested_detail'] == 'brief'
                     and first_product.get('product_success') and first_product['exact_CLI_delivery'])
    save(NS / 'FIRST_PACKET.json', {'first_business_attempt': first, 'first_installed_product': first_product,
         'first_call_brief_treatment_delivered': treatment,
         'treatment_note': 'Explicit brief request, installed tool first, successful and exact consumer delivery.',
         'isolation': configuration()})


def costs():
    publication()
    prior = load('_brief_retained_costs', OLD / 'costs.py')
    prior.NS, prior.EXTERNAL = NS, EXTERNAL
    historical = OLD / 'RUNTIME_REVIEW.json'
    old = next(row for row in read(historical)['slots'] if row['label'] == 'P1')
    new = prior.slot_summary('P1')
    save(NS / 'RUNTIME_REVIEW.json', {'slots': [new], 'historical_only': old,
         'historical_runtime_sha256': sha(historical), 'new_asset_builds': 0,
         'additional_qualification_owned': 0, 'new_native_slots': 0, 'cash_fees': None,
         'actual_internal_provider_input': None})


def archive():
    publication()
    prior = load('_brief_retained_archive', OLD / 'publish.py')
    prior.NS, prior.EXTERNAL = NS, EXTERNAL
    prior.archive()


def finalize():
    row, receipt = publication()
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(namespace) for path in changed):
        raise ValueError('project_outside_brief_entry_evidence_changed')
    packet = read(NS / 'FIRST_PACKET.json')
    runtime = read(NS / 'RUNTIME_REVIEW.json')
    quality = NS / 'scoring/QUALITY.json'
    required = ['REPORT.md', 'FIRST_PACKET.json', 'RUNTIME_REVIEW.json', 'RUNTIME_INDEX.json', 'ANSWERS_SEALED.json']
    if quality.is_file():
        required.append('scoring/QUALITY.json')
    if row['status'] == 'completed' and not quality.is_file():
        raise ValueError('completed_result_requires_formal_scoring')
    save(NS / 'DECISION.json', {'task': TASK, 'status': receipt['status'], 'slots': ['P1'],
         'formal_models': row['model_consumers'], 'new_native_slots': 0, 'additional_qualification_owned': 0,
         'builder': 0, 'replacements': 0, 'product_diff_files': 0, 'paid_API_calls': row['paid_API_calls'],
         'raster_upper': (runtime['slots'][0]['budget_slot'] or {}).get('raster_upper'),
         'first_call_brief_treatment_delivered': packet['first_call_brief_treatment_delivered'],
         'freeze_sha256': row['freeze_sha256'], 'admission_sha256': row['admission_sha256'],
         'evidence_sha256': {name: sha(NS / name) for name in required}})
    path = NS / 'CONTENT_MANIFEST.json'
    files = [p for p in sorted(NS.rglob('*')) if p.is_file() and p != path]
    if any(p.suffix == '.pyc' for p in files):
        raise ValueError('unexpected_generated_bytecode_in_evidence_folder')
    rows = [{'path': p.relative_to(NS).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    save(path, {'files': rows, 'count': len(rows), 'self_excluded': True})
    print(len(rows) + 1, sha(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('answers', 'first_packet', 'costs', 'archive', 'finalize'))
    globals()[parser.parse_args().action]()
