"""Resolve the already-inventoried multi-message TX files as JSONL."""

import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent


def main():
    review_bytes = (HERE / 'M4_TRACE_REVIEW.json').read_bytes()
    assert hashlib.sha256(review_bytes).hexdigest() == '89500134fd02c347bdfa087f83dd433a97d6daaefbb777bea4139eef3539cb2a'
    review = json.loads(review_bytes)
    pins = {row['path']: row['sha256'] for row in review['input_files']}
    records = []
    errors = []
    directory_requests = []
    low_level_directory_tokens = []
    messages = 0
    tool_calls = 0
    for family in review['raw_request_inventory']:
        for failed in family['decode_failures']:
            path = Path(failed['path'])
            blob = path.read_bytes()
            digest = hashlib.sha256(blob).hexdigest()
            assert digest == pins[str(path)]
            lines = []
            for index, raw in enumerate(blob.splitlines(), start=1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                    assert isinstance(value, dict), 'non-object request'
                except (ValueError, AssertionError) as exc:
                    errors.append({'path': str(path), 'line': index, 'error': str(exc)})
                    continue
                messages += 1
                params = value.get('params')
                params = params if isinstance(params, dict) else {}
                arguments = params.get('arguments')
                arguments = arguments if isinstance(arguments, dict) else {}
                query = arguments.get('query')
                query = query if isinstance(query, dict) else {}
                call = value.get('method') == 'tools/call'
                tool_calls += int(call)
                row = {'line': index, 'id': value.get('id'), 'method': value.get('method'),
                       'tool_name': params.get('name'), 'query_mode': query.get('mode'),
                       'message_sha256': hashlib.sha256(raw).hexdigest()}
                lines.append(row)
                if query.get('mode') == 'directory':
                    directory_requests.append({'path': str(path), **row})
                if re.search(rb'\bcapture_directory\b', raw):
                    low_level_directory_tokens.append({'path': str(path), **row})
            records.append({'path': str(path), 'sha256': digest, 'bytes': len(blob), 'family': family['family'],
                            'framing': 'one JSON object per nonempty line', 'messages': lines})
    output = {
        'schema': 'm2-directory-reuse-framed-TX-review-v1',
        'parent_M4_review_sha256': hashlib.sha256(review_bytes).hexdigest(),
        'scope': 'The exact 14 TX files already listed as single-document decode failures. Existing artifacts only; no new workload, asset search or host run.',
        'file_count': len(records), 'message_count': messages, 'tool_call_messages': tool_calls,
        'explicit_directory_requests': directory_requests,
        'capture_directory_text_occurrences': low_level_directory_tokens,
        'errors': errors, 'records': records,
        'additional_qualified_natural_hits': 0 if not directory_requests and not low_level_directory_tokens and not errors else None,
        'host_and_asset_denominators_changed': False,
        'new_Blender_model_raster_calls': 0,
        'limitation': 'Request framing and explicit operation evidence only. Arbitrary Python execution is not semantically evaluated.',
    }
    (HERE / 'FRAMED_TX_REVIEW.json').write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: output[key] for key in ('file_count', 'message_count', 'tool_call_messages', 'additional_qualified_natural_hits', 'errors')}))
    assert len(records) == 14 and output['additional_qualified_natural_hits'] == 0


if __name__ == '__main__':
    main()
