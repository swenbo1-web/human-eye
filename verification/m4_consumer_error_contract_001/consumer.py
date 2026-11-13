"""Candidate result binding on the unchanged original consumer event loop.

Only archive_turn is derived. The inherited consume_turn code receives a
private globals snapshot containing this archive function. Importing this
module starts nothing and leaves the legacy module and source unchanged.
"""

import hashlib
import importlib.util
from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LEGACY_SOURCE = ROOT / 'verification/m4_active_coverage_consumption_001/consumer.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('_error_contract_legacy_consumer', LEGACY_SOURCE)
result_contract = load('_error_contract_result_binding', HERE / 'result_contract.py')
read, save, sha, packer = legacy.read, legacy.save, legacy.sha, legacy.packer
safe_environment = legacy.safe_environment


def archive_turn(folder, cell, first_attempt, tool_calls):
    """Bind original requests and known success/error result representations."""
    audit = Path(cell['audit_dir'])
    tools = read(audit / 'TOOLS.json') if (audit / 'TOOLS.json').exists() else {'tools': []}
    source_records = []
    binding_errors = []
    result_contracts = []
    valid_first = type(first_attempt) is int and first_attempt >= 1
    selected = []
    for index, row in enumerate(tools.get('tools', [])):
        if type(row) is not dict or type(row.get('attempt')) is not int or row['attempt'] < 1:
            binding_errors.append({'reason': 'owner_attempt_identity', 'row_index': index})
        elif row['attempt'] >= (first_attempt if valid_first else 1):
            selected.append(row)
    attempts = [row['attempt'] for row in selected]
    if not valid_first:
        binding_errors.append({'reason': 'owner_attempt_identity', 'first_attempt': first_attempt, 'attempts': attempts})
    elif attempts != list(range(first_attempt, first_attempt + len(selected))):
        binding_errors.append({'reason': 'owner_attempt_order', 'first_attempt': first_attempt, 'attempts': attempts})
    if len(selected) != len(tool_calls):
        binding_errors.append({'reason': 'owner_and_CLI_attempt_count', 'owner': len(selected), 'CLI': len(tool_calls)})
    for owner, public in zip(selected, tool_calls):
        original = audit / ('tool_' + str(owner['attempt']).zfill(2))
        try:
            request = read(original / 'REQUEST.json')
            response_path = original / ('RESPONSE.json' if (original / 'RESPONSE.json').exists() else 'ERROR_RESPONSE.json')
            response = read(response_path)
            item = public['item']
            if request['params']['name'] != item['tool'] or packer.encoded(request['params']['arguments']) != packer.encoded(item['arguments']):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_request_differs_from_owner'})
            request_id, response_id = request.get('id'), response.get('id')
            if (type(request_id) not in (str, int) or type(request_id) is not type(response_id)
                    or request_id != response_id):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'request_response_id_mismatch'})
            binding = result_contract.bind_tool_result(response, item)
            result_contracts.append({'attempt': owner['attempt'], 'tool': item.get('tool'), **binding})
            if not binding['matched']:
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_result_differs_from_owner',
                                       'result_contract': binding})
        except (OSError, ValueError, KeyError, TypeError) as error:
            binding_errors.append({'attempt': owner['attempt'], 'reason': 'owner_original_unreadable', 'error': repr(error)})
    for row in selected:
        original = audit / ('tool_' + str(row['attempt']).zfill(2))
        for source in sorted(original.rglob('*')):
            if not source.is_file():
                continue
            target = folder / 'owner_turn' / original.name / source.relative_to(original)
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = source.read_bytes()
            target.write_bytes(raw)
            source_records.append({'original': str(source), 'copy': target.relative_to(folder).as_posix(),
                                   'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    save(folder / 'BUSINESS_SOURCE_BINDING.json', {
        'first_owner_attempt': first_attempt, 'recorded_owner_attempts': attempts,
        'sources': source_records, 'binding_errors': binding_errors, 'result_contracts': result_contracts,
        'scope': 'Actual owner originals copied unchanged and matched to completed CLI tool events by the candidate unified result contract.'})
    archive = folder.parent / (folder.name + '.raw.zip')
    sources = packer.capture_cell(folder, archive)
    value = {'archive': str(archive), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
             'original_file_count': len(sources), 'owner_attempts': attempts,
             'business_binding_errors': binding_errors, 'result_contracts': result_contracts,
             'scope': 'Raw events, outputs, attachments and original owner requests/responses. Candidate result classifications preserve business tool errors.'}
    save(folder / 'ARCHIVE.json', value)
    return value


_consume_globals = dict(legacy.consume_turn.__globals__)
_consume_globals['archive_turn'] = archive_turn
consume_turn = types.FunctionType(legacy.consume_turn.__code__, _consume_globals,
    legacy.consume_turn.__name__, legacy.consume_turn.__defaults__, legacy.consume_turn.__closure__)
consume_turn.__kwdefaults__ = (None if legacy.consume_turn.__kwdefaults__ is None
                             else dict(legacy.consume_turn.__kwdefaults__))
consume_turn.__module__ = __name__
