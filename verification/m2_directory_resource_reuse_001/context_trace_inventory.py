"""Read the bounded M1/M5/residency archive set for actual directory evidence."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAMESPACES = (
    'm1_task_entry_001', 'm1_task_entry_001_eval', 'm1_task_entry_001_optimize',
    'm1_name_id_entry_001', 'm1_name_nearest_001', 'm1_nearest_evidence_001',
    'm5_local_loop_001', 'm5_local_loop_opt_001', 'arch_resident_001',
    'arch_resident_opt_001', 'nearest_contract_m2_001',
)


def visit(value, location, hits, depth=0):
    if depth > 80:
        raise ValueError('unexpected JSON nesting at ' + location)
    if isinstance(value, dict):
        if value.get('method') == 'tools/list':
            hits['tool_catalogue_occurrences'].append(location)
        if value.get('result_kind') == 'scene_directory':
            hits['scene_directory_result_occurrences'].append(location)
        if value.get('mode') == 'directory':
            hits['directory_mode_occurrences'].append(location)
        if value.get('method') == 'tools/call':
            params = value.get('params', {})
            arguments = params.get('arguments') if isinstance(params, dict) else None
            if isinstance(arguments, dict):
                query = arguments.get('query', {})
                if isinstance(query, dict) and query.get('mode') == 'directory':
                    hits['scene_directory_request_occurrences'].append(location)
            else:
                hits['malformed_tool_call_occurrences'].append(location)
        for key, item in value.items():
            visit(item, location + '/' + str(key), hits, depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            visit(item, location + '/' + str(index), hits, depth + 1)
    elif isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            return
        visit(decoded, location + '/decoded_JSON_string', hits, depth + 1)


def main():
    started = time.monotonic_ns()
    records = []
    summaries = []
    errors = []
    for namespace in NAMESPACES:
        folder = ROOT / 'verification' / namespace
        counts = dict(json_files=0, jsonl_files=0, bytes=0)
        hits = {name: [] for name in (
            'tool_catalogue_occurrences', 'scene_directory_result_occurrences',
            'directory_mode_occurrences', 'scene_directory_request_occurrences',
            'malformed_tool_call_occurrences',
        )}
        paths = sorted(path for path in folder.rglob('*') if path.is_file() and path.suffix in {'.json', '.jsonl'})
        for path in paths:
            blob = path.read_bytes()
            counts['jsonl_files' if path.suffix == '.jsonl' else 'json_files'] += 1
            counts['bytes'] += len(blob)
            relative = path.relative_to(ROOT).as_posix()
            records.append({'path': relative, 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)})
            try:
                if path.suffix == '.jsonl':
                    for line, row in enumerate(blob.splitlines(), start=1):
                        if row.strip():
                            visit(json.loads(row), relative + '/line_' + str(line), hits)
                else:
                    visit(json.loads(blob), relative, hits)
            except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                errors.append({'path': relative, 'type': type(exc).__name__, 'reason': str(exc)})
        summaries.append({'namespace': namespace, **counts, **hits})
    output = {
        'schema': 'm2-directory-reuse-context-trace-inventory-v1',
        'source_baseline_git': '8f2a739e789b777358d84a168154bc7c50b929e5',
        'scope': 'Bounded existing M1 entry, M5 loop and residency supporting archives. File/JSON occurrence counts include duplicates and are not independent real task denominators.',
        'namespace_count': len(NAMESPACES),
        'file_count': len(records),
        'files': records,
        'namespaces': summaries,
        'parse_errors': errors,
        'qualified_natural_hits': 0,
        'qualification': 'No scene_directory request/result or mode-directory evidence was found in this supporting archive set. tools/list denotes the tool catalogue.',
        'actual_Blender_model_raster_calls': 0,
        'started_ns': started,
        'closed_ns': time.monotonic_ns(),
    }
    # The conclusion is guarded by the scan results, not inferred from filenames.
    assert not errors, errors
    assert all(not summary[name] for summary in summaries for name in (
        'scene_directory_result_occurrences', 'directory_mode_occurrences',
        'scene_directory_request_occurrences',
    )), 'Unexpected directory evidence requires individual review'
    (HERE / 'CONTEXT_TRACE_INVENTORY.json').write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'namespaces': len(NAMESPACES), 'files': len(records), 'scene_directory_hits': 0,
                      'tool_catalogue_occurrences': sum(len(row['tool_catalogue_occurrences']) for row in summaries),
                      'parse_errors': len(errors)}))


if __name__ == '__main__':
    main()
