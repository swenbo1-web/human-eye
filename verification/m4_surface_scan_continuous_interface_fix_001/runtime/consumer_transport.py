"""Reuse the FIX1 process loop with one narrow successful-result comparison."""

import hashlib
import importlib.util
from pathlib import Path


BATCH = Path(__file__).resolve().parent.parent
ROOT = BATCH.parents[1]
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('_interface_fix_original_transport', FIX1 / 'runtime/consumer_transport.py')
compatibility = load('_interface_fix_successful_result', BATCH / 'compatibility.py')
read, save, sha, packer = legacy.read, legacy.save, legacy.sha, legacy.packer


def archive_turn(folder, cell, first_attempt, tool_calls):
    """Bind actual per-turn original requests/responses and thin wire archives."""
    audit = Path(cell['audit_dir'])
    tools = read(audit / 'TOOLS.json') if (audit / 'TOOLS.json').exists() else {'tools': []}
    selected = [row for row in tools.get('tools', []) if row['attempt'] >= first_attempt]
    source_records = []
    binding_errors = []
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
            if (packer.encoded(response.get('result')) != packer.encoded(item.get('result'))
                    and not compatibility.successful_result_matches(response, item)):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_result_differs_from_owner'})
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
        'first_owner_attempt': first_attempt, 'recorded_owner_attempts': [row['attempt'] for row in selected],
        'sources': source_records, 'binding_errors': binding_errors,
        'scope': 'Actual owner originals copied unchanged and matched to the CLI completed tool events for this turn.'})
    archive = folder.parent / (folder.name + '.raw.zip')
    sources = packer.capture_cell(folder, archive)
    value = {'archive': str(archive), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
             'original_file_count': len(sources), 'owner_attempts': [row['attempt'] for row in selected],
             'business_binding_errors': binding_errors,
             'scope': 'Raw events, outputs, attachments and owner business originals; derived CONSUMER and timing receipts are published after this archive.'}
    save(folder / 'ARCHIVE.json', value)
    return value


legacy.archive_turn = archive_turn
consume_turn = legacy.consume_turn
